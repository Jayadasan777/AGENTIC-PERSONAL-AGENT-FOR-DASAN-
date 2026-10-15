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
