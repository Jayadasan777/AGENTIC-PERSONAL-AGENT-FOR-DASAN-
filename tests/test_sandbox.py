"""Comprehensive test suite for Phase 4.5: Sandboxed Execution Laboratory.

Covers:
- Sandboxed Python execution and stdout capture
- Execution deadline and timeout enforcement
- Network egress defense (blocking socket creation)
- Integration with CodeExecutionTool and PolicyEngine
"""

from __future__ import annotations

import uuid

import pytest

from backend.app.agent.policy import PolicyDecision, PolicyEngine
from backend.app.agent.tools.base import RiskTier, ToolContext
from backend.app.agent.tools.sandbox import CodeExecutionTool
from backend.app.sandbox.config import SandboxLimits
from backend.app.sandbox.runner import CodeSandbox


@pytest.mark.asyncio
async def test_sandbox_clean_execution():
    """Verify standard computation runs cleanly in sandbox and returns stdout."""
    box = CodeSandbox(limits=SandboxLimits(timeout_seconds=5))
    code = (
        "import math\n"
        "vals = [math.sqrt(i) for i in range(10)]\n"
        "print(f'Computed {len(vals)} values')\n"
    )
    result = await box.execute_python(code)
    assert result.exit_code == 0
    assert "Computed 10 values" in result.stdout
    assert not result.timed_out


@pytest.mark.asyncio
async def test_sandbox_timeout_enforcement():
    """Verify runaway loops are killed within the configured timeout limit."""
    box = CodeSandbox(limits=SandboxLimits(timeout_seconds=2))
    infinite_loop_code = "import time\nwhile True:\n    time.sleep(0.1)\n"
    result = await box.execute_python(infinite_loop_code)
    assert result.timed_out is True
    assert result.exit_code == -1
    assert "timed out" in result.stderr.lower()


@pytest.mark.asyncio
async def test_sandbox_network_egress_defense():
    """Verify unauthorized outbound network connections are blocked."""
    box = CodeSandbox(limits=SandboxLimits(allow_network=False, timeout_seconds=5))
    network_code = (
        "import socket\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "s.connect(('1.1.1.1', 80))\n"
    )
    result = await box.execute_python(network_code)
    assert result.exit_code != 0
    assert "PermissionError" in result.stderr or "Network access is prohibited" in result.stderr


@pytest.mark.asyncio
async def test_code_execution_tool_policy_gating():
    """Verify CodeExecutionTool is classified as DANGEROUS and gated by PolicyEngine."""
    tool = CodeExecutionTool()
    assert tool.risk_tier == RiskTier.DANGEROUS

    policy = PolicyEngine()
    user_id = uuid.uuid4()
    args = {"code": "print('sensitive task')"}

    # Must require approval by default
    verdict = policy.evaluate(user_id, tool.name, args)
    assert verdict.decision == PolicyDecision.REQUIRE_APPROVAL
    assert verdict.approval_token is not None

    # Resumed with valid token evaluates to ALLOW
    resumed = policy.evaluate(user_id, tool.name, args, approval_token=verdict.approval_token)
    assert resumed.decision == PolicyDecision.ALLOW

    # Tool executes successfully
    ctx = ToolContext(user_id=user_id, session=None)  # type: ignore[arg-type]
    tool_res = await tool.execute(ctx, **args)
    assert tool_res.success is True
    assert "sensitive task" in tool_res.data["stdout"]
