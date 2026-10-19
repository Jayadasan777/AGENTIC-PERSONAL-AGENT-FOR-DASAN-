"""Hardened resource constraints and security configuration for code sandboxing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxLimits:
    """Rigid resource bounds to prevent denial of service and escape attempts."""

    memory_limit_mb: int = 128  # 128 MB RAM max
    cpu_quota_cores: float = 0.5  # 50% single-core CPU max
    timeout_seconds: int = 5  # Strict 5s execution deadline
    allow_network: bool = False  # Zero outbound/inbound network (no egress)
    read_only_rootfs: bool = True  # Immutable filesystem
    max_output_bytes: int = 32768  # 32 KB stdout/stderr buffer max
