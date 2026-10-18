"""System command execution tool strictly gated behind human approval."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from backend.app.agent.tools.base import AgentTool, RiskTier, ToolContext, ToolResult


class SystemCommandArgs(BaseModel):
    """Input parameters for running a system command."""

    command: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Shell command to execute in sandbox (strictly requires user approval).",
    )
    timeout_seconds: int = Field(
        default=10,
        ge=1,
        le=60,
        description="Timeout limit in seconds.",
    )


class SystemCommandTool(AgentTool):
    """Execute bounded system shell command. Classified as DANGEROUS."""

    name = "system_command"
    description = (
        "Run an operating system shell command. "
        "DANGEROUS: Always requires explicit signed human approval before invocation."
    )
    risk_tier = RiskTier.DANGEROUS
    args_schema = SystemCommandArgs

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        timeout = kwargs.get("timeout_seconds", 10)

        # Prohibit destructive root commands as defense-in-depth
        prohibited = ["rm -rf /", ":(){ :|:& };:", "mkfs", "dd if=/dev/zero"]
        if any(p in command for p in prohibited):
            return ToolResult(
                success=False,
                error="Prohibited dangerous pattern detected in command.",
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except TimeoutError:
                proc.kill()
                return ToolResult(
                    success=False,
                    error=f"Command timed out after {timeout} seconds.",
                )

            stdout_str = stdout_data.decode("utf-8", errors="replace")[:4000]
            stderr_str = stderr_data.decode("utf-8", errors="replace")[:4000]

            return ToolResult(
                success=proc.returncode == 0,
                data={
                    "command": command,
                    "exit_code": proc.returncode,
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                },
                error=stderr_str if proc.returncode != 0 else None,
            )
        except Exception as err:
            return ToolResult(
                success=False,
                error=f"Failed to execute command: {err}",
            )
