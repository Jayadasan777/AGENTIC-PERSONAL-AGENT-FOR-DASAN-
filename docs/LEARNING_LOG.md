# AURA Engineering Learning Log

A running three-line journal documenting lessons, trade-offs, and insights learned at each implementation step.

---

### [2026-10-15] Phase 0 - Step 1: Repository Audit and Governance Initialization
1. **Audited environment:** Verified empty working tree, initialized git branch `main`, verified remote access to GitHub repo without committing secrets.
2. **Defensive foundations:** Established `.gitignore` and `.env.example` first to eliminate the risk of committing credentials, cache files, or large model binaries.
3. **Architectural grounding:** Formulated the phase checklist, engineering glossary, and ADR-0001 to anchor future implementation strictly in verified requirements.

### [2026-10-15] Phase 0 - Step 2: System Dependencies, Hardware Calibration, and Risk Register
1. **Dependency sequencing:** Mapped architectural prerequisites; verified why tenant-isolated auth (Phase 1) must precede memory (Phase 2) and RAG (Phase 3).
2. **Hardware reality check:** Calibrated local model selection against 4 GB VRAM (RTX 2050) using <=3B 4-bit quantized open-weight models and mock providers.
3. **Proactive risk management:** Established a living risk register addressing small-model tool calling, durable workflow engines, and cloud hosting portability.

### [2026-10-15] Phase 1 - Step 1: Environment Verification and Project Configuration
1. **WSL2 environment audit:** Discovered Ubuntu 24.04 runtime with Python 3.12.3, `python3-venv`, and Docker 29.1.3 verified operational.
2. **Standardized packaging:** Adopted PEP 621 `pyproject.toml` consolidating dependencies, Ruff linter, mypy strict type checker, and pytest options.
3. **Security-first tooling:** Integrated `bandit` and `flake8-bandit` rules directly into the linter configuration to catch hardcoded secrets and insecure calls early.

### [2026-10-15] Phase 1 - Step 2: Typed Application Settings and Secret Masking
1. **Pydantic Settings:** Implemented strongly-typed configuration with validation for environment, server ports, and storage limits.
2. **SecretStr defense:** Wrapped `SECRET_KEY` and `POSTGRES_PASSWORD` in `SecretStr` to prevent credentials leaking into logs, stack traces, or prints.
3. **Cryptographic validation:** Added a custom field validator enforcing a minimum 32-character key length to prevent weak cryptographic signing.

### [2026-10-15] Phase 1 - Step 3: Toolchain Verification and Test Automation
1. **Isolated virtualenv:** Provisioned Python 3.12 `.venv` in WSL2 Ubuntu and installed all development and runtime dependencies.
2. **Automated quality gates:** Configured Ruff (`per-file-ignores` for test fixtures) and mypy strict mode (`explicit_package_bases = true`).
3. **Test verification:** Executed 4 automated unit tests in `tests/test_config.py` with pytest, confirming 100% pass rate with zero type or lint defects.

### [2026-10-15] Phase 1 - Step 4: Structured JSON Logging and Correlation IDs
1. **Machine-parseable logs:** Built `JSONFormatter` to render standard library log records as single-line JSON with timestamps and environment context.
2. **ContextVar correlation:** Used Python's async-safe `contextvars.ContextVar` to propagate `request_id` across asynchronous coroutines without parameter drilling.
3. **Traceability verified:** Implemented unit tests proving request IDs and exception stack traces format cleanly into JSON log objects.

### [2026-10-15] Phase 1 - Step 5: FastAPI Skeleton, Middleware, and Health Endpoints
1. **Application factory:** Implemented `create_application()` with modern `lifespan` context manager, automated logging initialization, and versioned routing.
2. **Correlation ID middleware:** Built HTTP middleware tracking `X-Request-ID` across ingress, setting task context, recording latency, and appending headers.
3. **Defensive exception handling:** Registered global unhandled exception handler returning sanitized JSON error envelopes with zero stack-trace leakage.

### [2026-10-15] Phase 1 - Step 6: Docker Compose with PostgreSQL 16 and pgvector
1. **Unified relational & vector store:** Provisioned `pgvector/pgvector:pg16` through Docker Compose with automated initialization scripts for `vector` and `uuid-ossp`.
2. **Network isolation:** Bound port `5432` strictly to loopback interface `127.0.0.1` to prevent public or LAN database exposure.
3. **Live verification:** Confirmed container health checks and queried `pg_extension` directly, verifying `vector 0.8.7` active in `aura_db`.

### [2026-10-15] Phase 1 - Step 7: SQLAlchemy 2.0 Async Session & Alembic Harness
1. **Async database core:** Configured `create_async_engine` and `async_sessionmaker` with `pool_pre_ping=True` and FastAPI `get_db` dependency injection.
2. **Dynamic migration harness:** Configured `alembic/env.py` to bind directly to `Base.metadata` and dynamically read `Settings().async_database_uri`.
3. **Event loop isolation lesson:** Resolved `asyncpg` cross-loop connection pooling in pytest by using `NullPool` fixtures in `conftest.py` for test isolation.
