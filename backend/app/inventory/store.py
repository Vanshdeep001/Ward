from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class Snapshot:
    """One inventory sweep: every resource Ward saw, grouped by Custodian resource type."""
    taken_at: datetime
    resources: dict[str, list[dict]] = field(default_factory=dict)

    def of_type(self, resource_type: str) -> list[dict]:
        return self.resources.get(resource_type, [])


class InventoryStore(Protocol):
    def latest(self) -> Snapshot: ...
    def history(self, days: int) -> list[Snapshot]: ...


class SnapshotHistory:
    """Keeps recent sweeps in memory. SRS §16.5 moves this to a partitioned Postgres table with 90-day retention."""

    def __init__(self, max_snapshots: int = 90 * 96):
        self._snapshots: deque[Snapshot] = deque(maxlen=max_snapshots)

    def append(self, snapshot: Snapshot) -> None:
        self._snapshots.append(snapshot)

    def latest(self) -> Snapshot | None:
        return self._snapshots[-1] if self._snapshots else None

    def since(self, cutoff: datetime) -> list[Snapshot]:
        return [s for s in self._snapshots if s.taken_at >= cutoff]
