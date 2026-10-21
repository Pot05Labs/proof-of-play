"""Seeded synthetic match simulator: fictional clubs, football-realistic event streams."""

from .io import write_match
from .match import generate
from .stream import astream, stream

__all__ = ["astream", "generate", "stream", "write_match"]
