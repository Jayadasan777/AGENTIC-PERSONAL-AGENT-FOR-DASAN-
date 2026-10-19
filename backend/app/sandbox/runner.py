"""Hardened code execution runner enforcing resource limits and sandbox isolation."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

from backend.app.sandbox.config import SandboxLimits

logger = logging.getLogger("aura.sandbox")


@dataclass
class ExecutionResult:
    """Outcome of sandboxed code execution."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    memory_exceeded: bool = False
    killed_by_security: bool = False


class CodeSandbox:
    """Manages secure sandboxed code execution using container or process isolation."""

    def __init__(self, limits: SandboxLimits | None = None) -> None:
        self.limits = limits or SandboxLimits()

    def is_docker_available(self, image: str = "python:3.12-slim") -> bool:
        """Check if Docker is operational and image is locally cached."""
        if not shutil.which("docker"):
            return False
        try:
            # Check if docker daemon responds and image exists
            res = subprocess.run(  # noqa: S603
                ["docker", "image", "inspect", image],  # noqa: S607
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
            return res.returncode == 0
        except Exception:
            return False

    async def execute_python(self, code: str) -> ExecutionResult:
        """Execute Python code within hardened sandbox boundaries."""
        if self.is_docker_available("python:3.12-slim"):
            return await self._execute_docker(code)
        return await self._execute_restricted_process(code)

    async def _execute_docker(self, code: str) -> ExecutionResult:
        """Run inside disposable Docker container with dropped capabilities and zero egress."""
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network=none",  # Strict no egress
            f"--memory={self.limits.memory_limit_mb}m",
            f"--cpus={self.limits.cpu_quota_cores}",
            "--read-only",  # Immutable root filesystem
            "--tmpfs=/tmp:rw,noexec,nosuid,size=16m",  # Ephemeral non-executable /tmp
            "--cap-drop=ALL",  # Drop all Linux capabilities
            "--security-opt=no-new-privileges",
            "--user=10001:10001",  # Unprivileged non-root user
            "python:3.12-slim",
            "python3",
            "-",
        ]
        start_time = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(input=code.encode("utf-8")),
                    timeout=self.limits.timeout_seconds,
                )
                duration_ms = int((time.monotonic() - start_time) * 1000)
                limit = self.limits.max_output_bytes
                stdout_str = stdout_data.decode("utf-8", errors="replace")[:limit]
                stderr_str = stderr_data.decode("utf-8", errors="replace")[:limit]

                # Check if OOM killed (exit code 137)
                memory_exceeded = proc.returncode == 137

                return ExecutionResult(
                    exit_code=proc.returncode or 0,
                    stdout=stdout_str,
                    stderr=stderr_str,
                    duration_ms=duration_ms,
                    memory_exceeded=memory_exceeded,
                )
            except TimeoutError:
                proc.kill()
                duration_ms = int((time.monotonic() - start_time) * 1000)
                return ExecutionResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"Execution timed out after {self.limits.timeout_seconds} seconds.",
                    duration_ms=duration_ms,
                    timed_out=True,
                )
        except Exception as err:
            logger.exception("Docker sandbox execution failure: %s", err)
            # Fallback to restricted process if Docker daemon fails
            return await self._execute_restricted_process(code)

    async def _execute_restricted_process(self, code: str) -> ExecutionResult:
        """Fallback process execution with safety wrappers and timeout enforcement."""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            # Wrap code with egress defense if network is disallowed
            wrapper = ""
            if not self.limits.allow_network:
                wrapper = (
                    "import socket\n"
                    "def _blocked(*args, **kwargs):\n"
                    "    raise PermissionError('Network access is prohibited in this sandbox.')\n"
                    "socket.socket = _blocked\n"
                    "socket.create_connection = _blocked\n"
                )
            f.write(wrapper + code)
            tmp_path = f.name

        start_time = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.limits.timeout_seconds,
                )
                duration_ms = int((time.monotonic() - start_time) * 1000)
                limit = self.limits.max_output_bytes
                stdout_str = stdout_data.decode("utf-8", errors="replace")[:limit]
                stderr_str = stderr_data.decode("utf-8", errors="replace")[:limit]

                return ExecutionResult(
                    exit_code=proc.returncode or 0,
                    stdout=stdout_str,
                    stderr=stderr_str,
                    duration_ms=duration_ms,
                )
            except TimeoutError:
                proc.kill()
                duration_ms = int((time.monotonic() - start_time) * 1000)
                return ExecutionResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"Execution timed out after {self.limits.timeout_seconds} seconds.",
                    duration_ms=duration_ms,
                    timed_out=True,
                )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


sandbox = CodeSandbox()
