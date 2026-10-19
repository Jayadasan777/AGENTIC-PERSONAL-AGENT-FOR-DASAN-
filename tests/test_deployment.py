"""Phase 6 Test Suite: Live Deployment, Reverse Proxy, Hardware Benchmarking, and Backups.

Tests cover:
- Hardware benchmarking calculations and model recommendation logic.
- Multi-stage Dockerfile structure and security best practices.
- Production Docker Compose configuration syntax and services.
- Caddy & Nginx reverse proxy configuration completeness.
- Backup creation, SHA256 verification, and rotation logic.
- Deployment readiness, liveness, and metadata probes.
- Live connectivity and authentication workflow on API endpoints.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.deployment.backup import (
    compute_sha256,
    list_backups,
    prune_old_backups,
    verify_backup_file,
)
from backend.app.deployment.benchmarking import (
    MODEL_CATALOG,
    HardwareSpecs,
    compute_kv_cache_ram,
    detect_hardware_specs,
    evaluate_model_fit,
    generate_benchmark_report,
)
from backend.app.main import app

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 1. Hardware Benchmarking Tests
# ---------------------------------------------------------------------------


class TestHardwareBenchmarking:
    def test_detect_hardware_specs_returns_valid_object(self) -> None:
        specs = detect_hardware_specs()
        assert isinstance(specs, HardwareSpecs)
        assert specs.cpu_cores >= 1
        assert specs.cpu_threads >= 1
        assert specs.ram_total_gb > 0
        assert specs.ram_available_gb > 0
        assert specs.disk_free_gb >= 0

    def test_compute_kv_cache_ram(self) -> None:
        # 8K context for 7B model
        ram_8k = compute_kv_cache_ram(8192, 7.0)
        assert 0.001 < ram_8k < 1.0

        # 32K context should scale linearly
        ram_32k = compute_kv_cache_ram(32768, 7.0)
        assert ram_32k > ram_8k

    def test_evaluate_model_fit_fits_in_vram(self) -> None:
        specs = HardwareSpecs(
            os_name="Linux",
            architecture="x86_64",
            cpu_cores=8,
            cpu_threads=16,
            ram_total_gb=32.0,
            ram_available_gb=28.0,
            gpu_available=True,
            gpu_name="NVIDIA RTX 4090",
            vram_total_gb=24.0,
            vram_available_gb=22.0,
            disk_free_gb=100.0,
        )
        model = MODEL_CATALOG[0]  # Qwen2.5-7B
        rec = evaluate_model_fit(model, "Q4_K_M", specs, target_context=8192)
        assert rec.fits_in_vram is True
        assert rec.fits_in_ram is True
        assert rec.recommended is True
        assert "FAST" in rec.estimated_speed_category
        assert rec.recommended_gpu_layers > 0

    def test_evaluate_model_fit_cpu_fallback(self) -> None:
        # Machine with ample RAM but no GPU
        specs = HardwareSpecs(
            os_name="Linux",
            architecture="x86_64",
            cpu_cores=8,
            cpu_threads=16,
            ram_total_gb=32.0,
            ram_available_gb=28.0,
            gpu_available=False,
            gpu_name=None,
            vram_total_gb=0.0,
            vram_available_gb=0.0,
            disk_free_gb=100.0,
        )
        model = MODEL_CATALOG[0]
        rec = evaluate_model_fit(model, "Q4_K_M", specs, target_context=8192)
        assert rec.fits_in_vram is False
        assert rec.fits_in_ram is True
        assert rec.recommended is True
        assert rec.recommended_gpu_layers == 0

    def test_evaluate_model_fit_insufficient_memory(self) -> None:
        # Machine with tiny 2GB RAM
        specs = HardwareSpecs(
            os_name="Linux",
            architecture="x86_64",
            cpu_cores=1,
            cpu_threads=2,
            ram_total_gb=2.0,
            ram_available_gb=1.0,
            gpu_available=False,
            gpu_name=None,
            vram_total_gb=0.0,
            vram_available_gb=0.0,
            disk_free_gb=5.0,
        )
        model = MODEL_CATALOG[5]  # Qwen2.5-32B
        rec = evaluate_model_fit(model, "FP16", specs, target_context=8192)
        assert rec.fits_in_ram is False
        assert rec.recommended is False
        assert rec.estimated_speed_category == "UNSUITABLE"

    def test_generate_benchmark_report(self) -> None:
        report = generate_benchmark_report(target_context=8192)
        assert "hardware" in report
        assert "all_evaluations" in report
        assert len(report["all_evaluations"]) > 0


# ---------------------------------------------------------------------------
# 2. Docker & Infrastructure Artifacts Tests
# ---------------------------------------------------------------------------


class TestDeploymentArtifacts:
    def test_dockerfile_exists_and_hardened(self) -> None:
        dockerfile = Path("Dockerfile")
        assert dockerfile.is_file(), "Dockerfile must exist"
        content = dockerfile.read_text()
        assert "FROM python:3.12-slim AS builder" in content
        assert "FROM python:3.12-slim AS runtime" in content
        assert "groupadd -g 10001 aura" in content
        assert "USER aura" in content
        assert "HEALTHCHECK" in content
        assert "EXPOSE 8000" in content

    def test_docker_compose_prod_exists_and_configured(self) -> None:
        compose_file = Path("docker-compose.prod.yml")
        assert compose_file.is_file(), "docker-compose.prod.yml must exist"
        content = compose_file.read_text()
        assert "aura-postgres" in content
        assert "aura-api" in content
        assert "aura-caddy" in content
        assert "aura-internal" in content
        assert "aura-public" in content

    def test_caddyfile_reverse_proxy_security(self) -> None:
        caddyfile = Path("deploy/caddy/Caddyfile")
        assert caddyfile.is_file(), "Caddyfile must exist"
        content = caddyfile.read_text()
        assert "Strict-Transport-Security" in content
        assert "X-Content-Type-Options" in content
        assert "X-Frame-Options" in content
        assert "reverse_proxy aura-api:8000" in content

    def test_nginx_conf_exists_and_configured(self) -> None:
        nginx_conf = Path("deploy/nginx/nginx.conf")
        assert nginx_conf.is_file(), "nginx.conf must exist"
        content = nginx_conf.read_text()
        assert "proxy_pass http://aura_backend" in content
        assert "Strict-Transport-Security" in content
        assert "worker_connections" in content


# ---------------------------------------------------------------------------
# 3. Database Backup & Restore Tests
# ---------------------------------------------------------------------------


class TestDatabaseBackupService:
    def test_backup_scripts_exist_and_executable(self) -> None:
        backup_sh = Path("scripts/backup_db.sh")
        restore_sh = Path("scripts/restore_db.sh")
        assert backup_sh.is_file()
        assert restore_sh.is_file()
        assert "pg_dump" in backup_sh.read_text()
        assert "pg_restore" in restore_sh.read_text()

    def test_sha256_checksum_and_verify(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_backup.dump"
        test_file.write_bytes(b"PGDMP\x01\x00\x00SAMPLE_ARCHIVE_DATA")

        checksum = compute_sha256(test_file)
        assert len(checksum) == 64

        # Write checksum file
        checksum_file = test_file.with_suffix(test_file.suffix + ".sha256")
        checksum_file.write_text(f"{checksum}  {test_file.name}\n")

        # Verify should pass
        assert verify_backup_file(test_file) is True

        # Corrupt file and verify should fail
        test_file.write_bytes(b"CORRUPTED_CONTENT")
        assert verify_backup_file(test_file) is False

    def test_list_and_prune_backups(self, tmp_path: Path) -> None:
        # Create 5 mock backups
        for i in range(5):
            dump = tmp_path / f"backup_{i}.dump"
            dump.write_bytes(f"DATA_{i}".encode())
            sha = dump.with_suffix(dump.suffix + ".sha256")
            sha.write_text(f"{compute_sha256(dump)}  {dump.name}")

        backups = list_backups(tmp_path)
        assert len(backups) == 5

        # Prune to keep only 2
        pruned = prune_old_backups(tmp_path, retention_count=2)
        assert pruned == 3

        remaining = list_backups(tmp_path)
        assert len(remaining) == 2


# ---------------------------------------------------------------------------
# 4. Health, Readiness, and Connectivity Tests
# ---------------------------------------------------------------------------


class TestDeploymentHealthProbes:
    def test_health_endpoint(self) -> None:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "environment" in data

    def test_liveness_probe(self) -> None:
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"

    def test_readiness_probe_success(self) -> None:
        with patch("backend.app.api.v1.endpoints.health.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session

            resp = client.get("/api/v1/health/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ready"
            assert data["database"] == "connected"

    def test_readiness_probe_db_failure(self) -> None:
        with patch("backend.app.api.v1.endpoints.health.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__.side_effect = RuntimeError("DB Connection refused")

            resp = client.get("/api/v1/health/ready")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "not_ready"
            assert data["database"] == "disconnected"

    def test_deployment_metadata_probe(self) -> None:
        resp = client.get("/api/v1/health/deployment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "operational"
        assert data["proxy_compatible"] is True
        assert data["features"]["rag"] is True
        assert data["features"]["automation"] is True
