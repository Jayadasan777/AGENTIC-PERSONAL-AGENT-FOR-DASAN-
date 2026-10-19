"""Sandboxed Python code execution tool for AURA Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.agent.tools.base import AgentTool, RiskTier, ToolContext, ToolResult
from backend.app.sandbox.runner import sandbox


class CodeExecutionArgs(BaseModel):
    """Input parameters for sandboxed Python code execution."""

    code: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Python code to run in an isolated, unprivileged, non-networked container.",
    )


class CodeExecutionTool(AgentTool):
    """Execute Python code in a hardened, non-networked sandbox. Classified as DANGEROUS."""

    name = "execute_code"
    description = (
        "Execute Python code in an isolated sandbox with zero network access and memory limits. "
        "DANGEROUS: Always requires signed human approval before invocation."
    )
    risk_tier = RiskTier.DANGEROUS
    args_schema = CodeExecutionArgs

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        code = kwargs.get("code", "")
        res = await sandbox.execute_python(code)
        if res.timed_out:
            return ToolResult(
                success=False,
                error="Execution timed out.",
                data={"stderr": res.stderr, "duration_ms": res.duration_ms},
            )
        if res.memory_exceeded:
            return ToolResult(
                success=False,
                error="Execution exceeded memory limits (OOM).",
                data={"duration_ms": res.duration_ms},
            )
        if res.exit_code != 0:
            return ToolResult(
                success=False,
                error=res.stderr or f"Execution failed with exit code {res.exit_code}",
                data={
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "exit_code": res.exit_code,
                    "duration_ms": res.duration_ms,
                },
            )
        return ToolResult(
            success=True,
            data={
                "stdout": res.stdout,
                "exit_code": res.exit_code,
                "duration_ms": res.duration_ms,
            },
        )
