from datetime import datetime, timedelta, timezone

from api.clock import SimulatedClock, SystemClock, clock_from_config


class FakeWall:
    def __init__(self):
        self.now = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def test_system_clock_sim_equals_wall():
    wall = FakeWall()
    d = SystemClock(wall).to_dict()
    assert set(d) == {"mode", "now_sim", "now_wall", "speed"}
    assert d["mode"] == "system" and d["now_sim"] == d["now_wall"]


def test_speed_multiplies_elapsed_time():
    wall = FakeWall()
    clock = SimulatedClock("2026-10-16T03:00:00-05:00", speed=60, wall_now=wall)
    wall.advance(10)
    assert clock.now_sim() == datetime.fromisoformat("2026-10-16T03:10:00-05:00")


def test_set_to_and_jump():
    wall = FakeWall()
    clock = SimulatedClock(wall_now=wall)
    clock.set_to("2026-10-16T03:00:00-05:00")
    clock.jump(30)
    assert clock.now_sim() == datetime.fromisoformat("2026-10-16T03:30:00-05:00")


def test_set_speed_does_not_jump():
    wall = FakeWall()
    clock = SimulatedClock("2026-10-16T03:00:00-05:00", speed=2, wall_now=wall)
    wall.advance(60)
    before = clock.now_sim()
    clock.set_speed(10)
    assert clock.now_sim() == before


def test_stamp_has_wall_and_sim():
    wall = FakeWall()
    clock = SimulatedClock("2026-10-16T03:00:00-05:00", wall_now=wall)
    s = clock.stamp("status_at")
    assert set(s) == {"status_at_wall", "status_at_sim"}
    assert s["status_at_wall"] != s["status_at_sim"]


def test_clock_from_store_config_roundtrip():
    wall = FakeWall()
    clock = SimulatedClock("2026-10-16T03:00:00-05:00", speed=5, wall_now=wall)
    again = clock_from_config(clock.to_config(), wall)
    assert again.now_sim() == clock.now_sim() and again.speed == 5
    assert isinstance(clock_from_config(None, wall), SystemClock)
