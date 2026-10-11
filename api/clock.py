"""Clocks for ClosureIQ.

SystemClock: sim time equals wall time.
SimulatedClock: sim time = base_sim + (wall elapsed since base_wall) * speed.
Supports set_to and jump so the demo can fast-forward escalation timers.

Evidence freshness always uses wall time. Only notification and escalation
timers use sim time. Every record carries both (see stamp()).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str | datetime) -> datetime:
    """Parse an ISO 8601 string (or pass a datetime through). Naive means UTC."""
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class SystemClock:
    mode = "system"
    speed = 1.0

    def __init__(self, wall_now: Callable[[], datetime] = utc_now):
        self._wall_now = wall_now

    def now_wall(self) -> datetime:
        return self._wall_now()

    def now_sim(self) -> datetime:
        return self._wall_now()

    def to_dict(self) -> dict:
        wall = self.now_wall()
        return {"mode": self.mode, "now_sim": wall.isoformat(),
                "now_wall": wall.isoformat(), "speed": self.speed}

    def stamp(self, prefix: str) -> dict:
        return stamp(self, prefix)


class SimulatedClock:
    mode = "simulated"

    def __init__(self, base_sim: str | datetime | None = None,
                 base_wall: str | datetime | None = None, speed: float = 1.0,
                 wall_now: Callable[[], datetime] = utc_now):
        self._wall_now = wall_now
        now = wall_now()
        self.base_wall = parse_iso(base_wall) if base_wall else now
        self.base_sim = parse_iso(base_sim) if base_sim else self.base_wall
        self.speed = max(0.0, float(speed))

    def now_wall(self) -> datetime:
        return self._wall_now()

    def now_sim(self) -> datetime:
        elapsed = max(0.0, (self.now_wall() - self.base_wall).total_seconds())
        return self.base_sim + timedelta(seconds=elapsed * self.speed)

    def _rebase(self, new_sim: datetime) -> None:
        self.base_wall = self.now_wall()
        self.base_sim = new_sim

    def set_speed(self, speed: float) -> None:
        """Change speed without jumping: sim time continues from where it is."""
        self._rebase(self.now_sim())
        self.speed = max(0.0, float(speed))

    def set_to(self, value: str | datetime) -> None:
        self._rebase(parse_iso(value))

    def jump(self, minutes: float) -> datetime:
        """Move sim time ahead by N minutes. Returns the new sim time."""
        self._rebase(self.now_sim() + timedelta(minutes=minutes))
        return self.base_sim

    def to_dict(self) -> dict:
        return {"mode": self.mode, "now_sim": self.now_sim().isoformat(),
                "now_wall": self.now_wall().isoformat(), "speed": self.speed}

    def to_config(self) -> dict:
        """Same shape Badri's store keeps under the 'clock' setting."""
        return {"mode": self.mode, "speed": self.speed,
                "base_sim": self.base_sim.isoformat(), "base_wall": self.base_wall.isoformat()}

    def stamp(self, prefix: str) -> dict:
        return stamp(self, prefix)


def stamp(clock: SystemClock | SimulatedClock, prefix: str) -> dict:
    """{prefix_wall, prefix_sim} for any record row."""
    return {f"{prefix}_wall": clock.now_wall().isoformat(),
            f"{prefix}_sim": clock.now_sim().isoformat()}


def clock_from_config(cfg: dict | None,
                      wall_now: Callable[[], datetime] = utc_now) -> SystemClock | SimulatedClock:
    """Build a clock from the stored config {mode, speed, base_sim, base_wall}."""
    cfg = cfg or {}
    if cfg.get("mode") != "simulated":
        return SystemClock(wall_now)
    return SimulatedClock(cfg.get("base_sim"), cfg.get("base_wall"),
                          cfg.get("speed", 1.0), wall_now)
