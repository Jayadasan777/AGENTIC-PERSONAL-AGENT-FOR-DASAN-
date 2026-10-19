"""Programmatic Database Backup, Checksum Verification, and Restore Service.

Provides type-safe, auditable backup management for the AURA system.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("aura.deployment.backup")


@dataclass(frozen=True)
class BackupMetadata:
    """Metadata recorded for a generated database backup."""

    filename: str
    filepath: str
    size_bytes: int
    sha256_checksum: str
    created_at_utc: str
    verified: bool


def compute_sha256(filepath: Path | str) -> str:
    """Compute cryptographic SHA256 hex digest for a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_backup_file(filepath: Path | str) -> bool:
    """Verify that a backup archive exists, is non-empty, and matches its checksum."""
    path = Path(filepath)
    if not path.is_file() or path.stat().st_size == 0:
        return False

    checksum_path = path.with_suffix(path.suffix + ".sha256")
    if checksum_path.is_file():
        expected_line = checksum_path.read_text().strip()
        expected_checksum = expected_line.split()[0]
        actual_checksum = compute_sha256(path)
        if actual_checksum.lower() != expected_checksum.lower():
            logger.error(
                "Backup checksum mismatch for %s: expected %s, got %s",
                path.name,
                expected_checksum,
                actual_checksum,
            )
            return False

    # Check archive TOC with pg_restore if available
    pg_restore = shutil.which("pg_restore")
    if pg_restore:
        try:
            res = subprocess.run(  # noqa: S603
                [pg_restore, "--list", str(path)],
                capture_output=True,
                check=False,
                timeout=15,
            )
            if res.returncode != 0:
                logger.error("pg_restore --list returned error code %d", res.returncode)
                return False
        except Exception as e:
            logger.warning("Could not execute pg_restore validation: %s", e)

    return True


def list_backups(backup_dir: Path | str) -> list[BackupMetadata]:
    """Discover all database backups in backup_dir and return their verified metadata."""
    dir_path = Path(backup_dir)
    if not dir_path.is_dir():
        return []

    backups: list[BackupMetadata] = []
    for file in sorted(dir_path.glob("*.dump"), reverse=True):
        checksum_file = file.with_suffix(file.suffix + ".sha256")
        checksum = ""
        if checksum_file.is_file():
            checksum = checksum_file.read_text().strip().split()[0]
        else:
            checksum = compute_sha256(file)

        stat = file.stat()
        created_dt = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        verified = verify_backup_file(file)

        backups.append(
            BackupMetadata(
                filename=file.name,
                filepath=str(file.resolve()),
                size_bytes=stat.st_size,
                sha256_checksum=checksum,
                created_at_utc=created_dt.isoformat(),
                verified=verified,
            )
        )
    return backups


def prune_old_backups(backup_dir: Path | str, retention_count: int = 14) -> int:
    """Keep only the most recent `retention_count` backups, removing older ones."""
    dir_path = Path(backup_dir)
    if not dir_path.is_dir():
        return 0

    all_dumps = sorted(dir_path.glob("*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
    to_delete = all_dumps[retention_count:]
    deleted_count = 0

    for dump_file in to_delete:
        try:
            dump_file.unlink(missing_ok=True)
            checksum_file = dump_file.with_suffix(dump_file.suffix + ".sha256")
            checksum_file.unlink(missing_ok=True)
            deleted_count += 1
            logger.info("Pruned old backup: %s", dump_file.name)
        except OSError as e:
            logger.warning("Failed to prune %s: %s", dump_file.name, e)

    return deleted_count
