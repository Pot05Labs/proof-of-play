"""Append-only registries of Facts and Moments with retraction tracking."""

from __future__ import annotations

from collections.abc import Iterator

from pop.schema import Fact, Moment


class Registry[T: (Fact, Moment)]:
    """Ordered, append-only store. Items are never mutated; retraction is a separate set."""

    def __init__(self) -> None:
        self._items: dict[str, T] = {}
        self._retracted: dict[str, None] = {}  # ordered set

    @staticmethod
    def _id(item: T) -> str:
        return item.fact_id if isinstance(item, Fact) else item.moment_id

    def add(self, item: T) -> None:
        key = self._id(item)
        if key in self._items:
            raise ValueError(f"duplicate id {key}")
        self._items[key] = item

    def retract(self, key: str) -> None:
        if key not in self._items:
            raise KeyError(key)
        self._retracted[key] = None

    def is_retracted(self, key: str) -> bool:
        return key in self._retracted

    @property
    def retracted_ids(self) -> list[str]:
        return list(self._retracted)

    def active(self) -> list[T]:
        return [v for k, v in self._items.items() if k not in self._retracted]

    def get(self, key: str) -> T | None:
        return self._items.get(key)

    def __getitem__(self, key: str) -> T:
        return self._items[key]

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __iter__(self) -> Iterator[T]:
        return iter(list(self._items.values()))

    def __len__(self) -> int:
        return len(self._items)
