"""
Tests for FixVerifier stability monitoring.

Regression coverage for issue #55: every positive monitoring duration must pace
its observations with a delay strictly greater than zero, so their count is
governed by the requested time window rather than by event-loop throughput.
"""

import types

import pytest

from tools import fix_verifier
from tools.fix_verifier import FixVerifier


# Observations after which the harness forces its clock past the deadline, so
# that an unpaced loop fails an assertion instead of spinning forever.
RUNAWAY_ITERATION_GUARD = 50


class StabilityLoopHarness:
    """Drives _monitor_stability with a controlled clock and a sleep recorder."""

    def __init__(self, duration):
        self.duration = duration
        self.start = 1_000_000.0
        self.now = self.start
        self.sleeps = []
        self.checks = 0

    def time(self):
        """Replacement for tools.fix_verifier.time.time."""
        return self.now

    async def sleep(self, delay):
        """Replacement for tools.fix_verifier.asyncio.sleep; records the delay."""
        self.sleeps.append(delay)
        self.now += max(delay, 0)
        if len(self.sleeps) >= RUNAWAY_ITERATION_GUARD:
            self.now = self.start + self.duration + 1

    async def run_immediate_checks(self, incident_type, expected_state):
        """Stub for FixVerifier._run_immediate_checks; always passes."""
        self.checks += 1
        return {"check_type": "immediate", "passed": True, "details": {}}


async def drive_monitoring(monkeypatch, duration):
    """Run one _monitor_stability window and return the recording harness."""
    harness = StabilityLoopHarness(duration)
    monkeypatch.setattr(fix_verifier.time, "time", harness.time)
    monkeypatch.setattr(
        fix_verifier, "asyncio", types.SimpleNamespace(sleep=harness.sleep)
    )

    verifier = FixVerifier()
    verifier._run_immediate_checks = harness.run_immediate_checks

    result = await verifier._monitor_stability(
        "k8s", {"pod_status": "Running"}, duration
    )
    return harness, result


class TestStabilityMonitoringPacing:
    """Every positive monitoring duration must be paced by a positive delay."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("duration", [1, 2, 3, 4, 5, 6, 7, 8, 9])
    async def test_short_positive_durations_are_paced_by_a_positive_delay(
        self, monkeypatch, duration
    ):
        harness, result = await drive_monitoring(monkeypatch, duration)

        assert harness.sleeps, (
            f"duration={duration} performed no paced observation at all"
        )
        assert all(delay > 0 for delay in harness.sleeps), (
            f"duration={duration} awaited non-positive pacing delays: "
            f"{harness.sleeps}"
        )
        assert len(harness.sleeps) < RUNAWAY_ITERATION_GUARD, (
            f"duration={duration} performed {len(harness.sleeps)} observations; "
            "observation count must be bounded by the monitoring window"
        )
        assert result["checks_performed"] == len(harness.sleeps)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("duration", [300, 600, 900])
    async def test_long_durations_keep_the_thirty_second_maximum(
        self, monkeypatch, duration
    ):
        harness, _ = await drive_monitoring(monkeypatch, duration)

        assert harness.sleeps, f"duration={duration} performed no observation"
        assert set(harness.sleeps) == {30}, (
            f"duration={duration} must keep the 30 second maximum interval, "
            f"got {sorted(set(harness.sleeps))}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "duration, expected_interval", [(10, 1), (100, 10), (250, 25)]
    )
    async def test_medium_durations_keep_the_proportional_interval(
        self, monkeypatch, duration, expected_interval
    ):
        harness, _ = await drive_monitoring(monkeypatch, duration)

        assert set(harness.sleeps) == {expected_interval}, (
            f"duration={duration} must keep its duration // 10 interval of "
            f"{expected_interval}, got {sorted(set(harness.sleeps))}"
        )
