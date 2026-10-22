"""Multi-agent orchestrator for one moment, built on Microsoft Agent Framework.

Five roles, each with one narrow job, wired as an Agent Framework workflow:

  Interpreter  deterministic   picks the facts that lead and the angle for this viewer; builds the grounded draft
  Writer       model agent     rewrites the draft for the viewer, using only the facts
  Verifier     deterministic   the existing verify(): every number, player and team must trace to a cited fact
  Editor       model agent     only runs when the Verifier rejects; gets the reasons and tries ONE repair
  Fallback     deterministic   publishes the grounded draft when the repair also fails (or the model is down)

    Interpreter -> Writer -> Verifier --publish--> Publisher
                     |          |  ^
                     |          | edit (once)
                     |          v  |
                     |        Editor
                     |          |
                     +--------> Fallback --> Publisher   (writer silent, or second rejection)

The deterministic engine is the only source of numbers. Models only phrase facts they are handed, and nothing a
model writes reaches a viewer without passing the Verifier. Shared state is one immutable MomentState that each
step copies forward and the trace records. Model failure, an exception inside the workflow, or Agent Framework
itself failing all end at the grounded draft: run_moment never raises.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Literal, Never

from agent_framework import (
    Agent,
    BaseChatClient,
    ChatResponse,
    Executor,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from pydantic import BaseModel, ConfigDict

from pop.agents.explainer import SYSTEM, Viewer, _names, fact_rows, template_draft
from pop.agents.llm import LLM, StubLLM
from pop.agents.verifier import verify
from pop.schema import Fact, Insight, MatchInfo, Moment

log = logging.getLogger("pop.orchestrator")


class _QuietNoTools(logging.Filter):
    """Our agents are tool-less by design; drop AF's per-construction warning about it, keep everything else."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "does not support function invoking" not in record.getMessage()


logging.getLogger("agent_framework").addFilter(_QuietNoTools())

Route = Literal["", "verify", "edit", "fallback", "publish"]


class TraceStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent: str
    action: str
    input_summary: str
    output_summary: str
    ms: float
    ok: bool


class MomentState(BaseModel):
    """The shared state passed along every workflow edge. Frozen: each step returns an updated copy.

    Agent Framework delivers messages by reference and evaluates edge conditions later, so a mutable object
    shared between steps can be routed on a value a later step wrote. Copy-forward makes every edge see
    exactly the state its source produced.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    moment: Moment
    facts: tuple[Fact, ...]
    info: MatchInfo
    viewer: Viewer
    minute: int | None = None
    draft: str = ""
    lead_fact_ids: tuple[str, ...] = ()
    angle: str = ""
    candidate: str = ""           # the text currently under review
    candidate_by: str = ""        # "Writer" or "Editor"
    reasons: tuple[str, ...] = ()  # the Verifier's latest rejection reasons
    rejections: tuple[str, ...] = ()  # human-readable history of every rejection, for verifier_notes
    editor_attempts: int = 0
    route: Route = ""
    final_text: str = ""
    final_verified: bool = False
    path: str = ""
    trace: tuple[TraceStep, ...] = ()

    def step(self, agent: str, action: str, inp: str, out: str, t0: float, ok: bool, **update: Any) -> MomentState:
        s = TraceStep(agent=agent, action=action, input_summary=_clip(inp), output_summary=_clip(out),
                      ms=round((time.perf_counter() - t0) * 1000, 1), ok=ok)
        return self.model_copy(update={**update, "trace": (*self.trace, s)})


def _clip(s: str, n: int = 160) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _minutes(minute: int | None) -> set[int]:
    return {minute} if minute is not None else set()


def _insight(state: MomentState, text: str) -> Insight:
    m, v = state.moment, state.viewer
    return Insight(
        insight_id=f"{m.moment_id}:{v.audience}:{v.language}:{v.club_id or '-'}:{v.player_id or '-'}",
        moment_id=m.moment_id, audience=v.audience, language=v.language, text=text,
        fact_ids=[f.fact_id for f in state.facts], confidence=m.importance,
        personalised_for={k: val for k, val in {"club": v.club_id, "player": v.player_id}.items() if val},
    )


def _payload(state: MomentState) -> dict:
    """The Writer's user turn: explain()'s payload plus the Interpreter's angle. SYSTEM is untouched (cache key)."""
    names = _names(state.info)
    v = state.viewer
    return {
        "draft": state.draft,
        "facts": fact_rows(list(state.facts), state.info),
        "audience": v.audience,
        "language": v.language,
        "favourite_club": names.get(v.club_id) if v.club_id else None,
        "favourite_player": names.get(v.player_id) if v.player_id else None,
        "minute": state.minute,
        "lead_facts": list(state.lead_fact_ids),
        "angle": state.angle,
    }


# --- Agent Framework bridge -------------------------------------------------------------------------------


class PopChatClient(BaseChatClient):
    """Agent Framework chat client over the project's LLM (stub, Foundry gpt, Claude on Foundry, chaos, fakes).

    The Writer and Editor are real Agent Framework agents; this adapter keeps every backend's auth (Entra ID),
    prompt caching and usage meter in one place. Any failure becomes "", never an exception.
    """

    def __init__(self, llm: LLM) -> None:
        super().__init__()
        self._llm = llm

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        system = options.get("instructions") or ""
        if not isinstance(system, str):
            system = "\n".join(system)
        system = system or "\n".join(m.text for m in messages if m.role == "system")
        user = next((m.text for m in reversed(messages) if m.role == "user"), "")
        try:
            text = await asyncio.to_thread(self._llm.complete, system, user) or ""
        except Exception as e:  # noqa: BLE001 - a model failure is a recoverable state, not an error
            log.warning("model call failed in agent: %s", type(e).__name__)
            text = ""
        return ChatResponse(messages=[Message(role="assistant", contents=[text])])


async def _ask(agent: Agent, user: str) -> str:
    try:
        r = await agent.run(user)
        return (r.text or "").strip()
    except Exception as e:  # noqa: BLE001
        log.warning("agent %s failed: %s", agent.name, type(e).__name__)
        return ""


# --- Roles ------------------------------------------------------------------------------------------------


class Interpreter(Executor):
    """Deterministic. Chooses the lead facts and the angle; builds the grounded draft. No model."""

    def __init__(self) -> None:
        super().__init__(id="Interpreter")

    @handler
    async def run(self, state: MomentState, ctx: WorkflowContext[MomentState]) -> None:
        t0 = time.perf_counter()
        facts, v, info = list(state.facts), state.viewer, state.info
        lead = facts[:2]  # the draft voices the first two facts; every fact stays cited
        subjects = {f.subject_id for f in facts}
        squad_of = {p.player_id: t.team_id for t in (info.home, info.away) for p in t.squad}
        involved_teams = subjects | {squad_of[s] for s in subjects if s in squad_of}
        names = _names(info)
        if v.player_id and v.player_id in subjects:
            hook = f"about the viewer's player {names.get(v.player_id, v.player_id)}"
        elif v.club_id and v.club_id in involved_teams:
            hook = f"about the viewer's club {names.get(v.club_id, v.club_id)}"
        else:
            hook = "neutral"
        tone = ("lead with the number, then the reason in plain terms" if v.audience == "analyst"
                else "tell the story in everyday words, one number at most")
        angle = f"{state.moment.kind}; {tone}; {hook}"
        draft = template_draft(facts, info, state.moment.kind)
        new = state.step("Interpreter", "frame_moment",
                         f"{state.moment.kind}, {len(facts)} facts, viewer={v.audience}/{v.language}",
                         f"lead={[f.fact_id for f in lead]} angle={angle} draft={draft!r}", t0, True,
                         draft=draft, lead_fact_ids=tuple(f.fact_id for f in lead), angle=angle)
        await ctx.send_message(new)


class Writer(Executor):
    """Model agent. Rewrites the grounded draft for one viewer."""

    def __init__(self, agent: Agent) -> None:
        super().__init__(id="Writer")
        self.agent = agent

    @handler
    async def run(self, state: MomentState, ctx: WorkflowContext[MomentState]) -> None:
        t0 = time.perf_counter()
        text = await _ask(self.agent, json.dumps(_payload(state), ensure_ascii=False))
        if not text:
            new = state.step("Writer", "rewrite", f"draft={state.draft!r}", "no text (model unavailable)", t0,
                             False, route="fallback", rejections=(*state.rejections, "writer returned no text"))
        else:
            new = state.step("Writer", "rewrite", f"draft={state.draft!r} angle={state.angle}", text, t0, True,
                             candidate=text, candidate_by="Writer", route="verify")
        await ctx.send_message(new)


class VerifierAgent(Executor):
    """Deterministic. Runs verify() on the current candidate and decides the route."""

    def __init__(self) -> None:
        super().__init__(id="Verifier")

    @handler
    async def run(self, state: MomentState, ctx: WorkflowContext[MomentState]) -> None:
        t0 = time.perf_counter()
        v = verify(_insight(state, state.candidate), list(state.facts), state.info, _minutes(state.minute))
        who = state.candidate_by
        if v.ok:
            path = "verified first time" if who == "Writer" else \
                "repaired by Editor after: " + "; ".join(state.rejections)
            new = state.step("Verifier", f"check_{who.lower()}", state.candidate, "pass", t0, True,
                             route="publish", final_text=state.candidate, final_verified=True, path=path,
                             reasons=())
        else:
            rejection = f"{who.lower()} rewrite rejected ({'; '.join(v.reasons)})"
            route: Route = "edit" if state.editor_attempts < 1 else "fallback"
            new = state.step("Verifier", f"check_{who.lower()}", state.candidate,
                             "reject: " + "; ".join(v.reasons), t0, False,
                             route=route, reasons=v.reasons, rejections=(*state.rejections, rejection))
        await ctx.send_message(new)


class Editor(Executor):
    """Model agent. Invoked only after a rejection: repairs the rejected text once, using the reasons."""

    def __init__(self, agent: Agent) -> None:
        super().__init__(id="Editor")
        self.agent = agent

    @handler
    async def run(self, state: MomentState, ctx: WorkflowContext[MomentState]) -> None:
        t0 = time.perf_counter()
        payload = {**_payload(state), "task": "repair", "rejected_text": state.candidate,
                   "reasons": list(state.reasons),
                   "instruction": ("The REJECTED_TEXT broke the grounding rules for the REASONS given. Rewrite it "
                                   "so every number, player and team traces to FACTS. Remove anything you cannot "
                                   "ground. Return only the corrected sentence.")}
        text = await _ask(self.agent, json.dumps(payload, ensure_ascii=False))
        attempts = state.editor_attempts + 1
        if not text:
            new = state.step("Editor", "repair", "reasons=" + "; ".join(state.reasons),
                             "no text (model unavailable)", t0, False, editor_attempts=attempts,
                             route="fallback", rejections=(*state.rejections, "editor returned no text"))
        else:
            new = state.step("Editor", "repair", "reasons=" + "; ".join(state.reasons), text, t0, True,
                             editor_attempts=attempts, candidate=text, candidate_by="Editor", route="verify")
        await ctx.send_message(new)


def _fallback(state: MomentState, t0: float) -> MomentState:
    v2 = verify(_insight(state, state.draft), list(state.facts), state.info, _minutes(state.minute))
    path = "fell back to grounded draft after: " + "; ".join(state.rejections or ("no usable rewrite",))
    out = "published draft, verified" if v2.ok else "draft also failed: " + "; ".join(v2.reasons)
    return state.step("Fallback", "publish_draft", state.draft, out, t0, v2.ok, route="publish",
                      final_text=state.draft, final_verified=v2.ok, path=path)


class Fallback(Executor):
    """Deterministic. Publishes the grounded draft (re-verified) when no model text survived."""

    def __init__(self) -> None:
        super().__init__(id="Fallback")

    @handler
    async def run(self, state: MomentState, ctx: WorkflowContext[MomentState]) -> None:
        await ctx.send_message(_fallback(state, time.perf_counter()))


class Publisher(Executor):
    """Terminal node: yields the final state as the workflow output."""

    def __init__(self) -> None:
        super().__init__(id="Publisher")

    @handler
    async def run(self, state: MomentState, ctx: WorkflowContext[Never, MomentState]) -> None:
        await ctx.yield_output(state)


def _on(route: str):
    return lambda s: isinstance(s, MomentState) and s.route == route


def build_workflow(llm: LLM):
    """A fresh workflow per moment: worker threads run moments concurrently and a Workflow is single-run."""
    client = PopChatClient(llm)
    writer = Writer(Agent(client, instructions=SYSTEM, name="Writer",
                          description="Rewrites a grounded draft for one viewer, using only the facts."))
    editor = Editor(Agent(client, instructions=SYSTEM, name="Editor",
                          description="Repairs a rejected rewrite once, given the Verifier's reasons."))
    interpreter, verifier, fallback, publisher = Interpreter(), VerifierAgent(), Fallback(), Publisher()
    return (WorkflowBuilder(start_executor=interpreter, max_iterations=12, name="proof-of-play-moment")
            .add_edge(interpreter, writer)
            .add_edge(writer, verifier, condition=_on("verify"))
            .add_edge(writer, fallback, condition=_on("fallback"))
            .add_edge(verifier, publisher, condition=_on("publish"))
            .add_edge(verifier, editor, condition=_on("edit"))
            .add_edge(verifier, fallback, condition=_on("fallback"))
            .add_edge(editor, verifier, condition=_on("verify"))
            .add_edge(editor, fallback, condition=_on("fallback"))
            .add_edge(fallback, publisher)
            .build())


async def _run_workflow(state: MomentState, llm: LLM) -> MomentState:
    result = await build_workflow(llm).run(state)
    outputs = [o for o in result.get_outputs() if isinstance(o, MomentState)]
    if len(outputs) != 1:
        raise RuntimeError(f"workflow produced {len(outputs)} outputs")
    return outputs[0]


def _run_sync(coro_fn, *args):
    """Run a coroutine to completion from sync code, whether or not this thread already has a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_fn(*args))
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["v"] = asyncio.run(coro_fn(*args))
        except BaseException as e:  # noqa: BLE001 - re-raised in the caller's thread
            box["e"] = e

    t = threading.Thread(target=target, name="pop-orchestrator", daemon=True)
    t.start()
    t.join()
    if "e" in box:
        raise box["e"]
    return box["v"]


def run_moment(moment: Moment, facts: list[Fact], info: MatchInfo, viewer: Viewer | None = None,
               llm: LLM | None = None, minute: int | None = None) -> tuple[Insight, list[TraceStep]]:
    """Write one verified insight for one viewer through the agent team. Never raises.

    Semantics match explain(): verified only if the published text passes verify(), every fact cited,
    and verifier_notes says which path produced the text.
    """
    llm = llm or StubLLM()
    state = MomentState(moment=moment, facts=tuple(facts), info=info, viewer=viewer or Viewer(), minute=minute)
    t0 = time.perf_counter()
    try:
        final = _run_sync(_run_workflow, state, llm)
    except Exception as e:  # noqa: BLE001 - orchestration failure still publishes the grounded draft
        log.warning("orchestrator workflow failed: %s", type(e).__name__)
        broken = state.step("Orchestrator", "workflow_error", "agent workflow", f"{type(e).__name__}: {e}", t0, False,
                            rejections=(f"orchestrator error ({type(e).__name__})",))
        try:
            final = _fallback(broken.model_copy(update={"draft": template_draft(list(facts), info, moment.kind)}),
                              time.perf_counter())
        except Exception as e2:  # noqa: BLE001 - last resort: nothing verifiable, publish nothing usable
            log.error("fallback failed: %s", type(e2).__name__)
            ins = _insight(state, "").model_copy(update={
                "verified": False, "status": "rejected",
                "verifier_notes": f"rejected: orchestrator and fallback failed ({type(e2).__name__})"})
            return ins, list(broken.trace)
    ins = _insight(final, final.final_text).model_copy(update={
        "verified": final.final_verified, "verifier_notes": final.path,
        "status": "draft" if final.final_verified else "rejected"})
    return ins, list(final.trace)
