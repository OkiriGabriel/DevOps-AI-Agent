"""Tests for FixVerifier stability monitoring."""
import pytest

from tools.fix_verifier import FixVerifier


class TestFixVerifierStability:
    @pytest.mark.asyncio
    async def test_zero_monitoring_duration_is_not_verified(self):
        """Issue #52: zero-duration monitoring must not report verified success."""
        result = await FixVerifier().verify_fix(
            incident_type="cicd",
            fix_applied="rerun pipeline",
            expected_state={"pipeline": "ok"},
            monitoring_duration=0,
        )

        assert result["status"] != "success"
        assert result["verified"] is False
        stability = result["checks_performed"][1]
        assert stability["checks_performed"] == 0
        assert stability["stable"] is False
