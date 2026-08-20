from __future__ import annotations

from dataclasses import dataclass
from time import monotonic


@dataclass(slots=True)
class BeamSearchDeadline:
    expires_at: float
    check_interval: int = 16
    transition_count: int = 0
    hit: bool = False

    @classmethod
    def start(cls, seconds: float, *, check_interval: int) -> BeamSearchDeadline:
        return cls(
            expires_at=monotonic() + max(0.0, seconds),
            check_interval=max(1, check_interval),
        )

    def expired(self, *, force: bool = False) -> bool:
        if self.hit:
            return True
        if not force:
            self.transition_count += 1
            if self.transition_count % self.check_interval:
                return False
        self.hit = monotonic() >= self.expires_at
        return self.hit
