"""Comprehensive test suite for Phase 4: Agent Harness, Tools, and Approvals.

Covers:
- Safe AST calculator tool (without eval)
- Bounded system command tool and dangerous command blocking
- Three-tier policy engine (ALLOW, REQUIRE_APPROVAL, DENY)
- Cryptographic HMAC approval tokens, expiration, and replay prevention
- Human-in-the-loop approval workflow and resumption
- Independent outcome verification
- Global emergency kill switch
- SKILL.md parsing and permission validation
- MCP client SSRF allowlisting
- Agent execution API endpoints
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.agent.kill_switch import KillSwitchActiveError, kill_switch
from backend.app.agent.mcp import MCPClient
from backend.app.agent.policy import PolicyDecision, PolicyEngine
from backend.app.agent.skills import SkillParser, SkillValidationError
from backend.app.agent.tools.base import RiskTier, ToolContext, ToolResult
from backend.app.agent.tools.calculator import CalculatorTool, safe_eval_expression
from backend.app.agent.tools.registry import create_default_registry
from backend.app.agent.tools.system import SystemCommandTool
from backend.app.agent.verifier import outcome_verifier
from backend.app.db.base import Base
from backend.app.db.session import get_async_session
from backend.app.main import create_application

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def app_client():
    """Create isolated FastAPI app with fresh SQLite DB for each test."""
    # Ensure kill switch is disengaged before test
    kill_switch.disengage()

    engine = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_async_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_application()
    app.dependency_overrides[get_async_session] = override_get_async_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    await engine.dispose()
    kill_switch.disengage()


async def _register_and_get_token(
    client: AsyncClient, email: str, password: str = "securepass123"
) -> str:
    """Helper to register user and obtain valid access token."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert reg.status_code == 201
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


# ==============================================================================
# 1. Tool Unit Tests
# ==============================================================================


def test_safe_eval_expression():
    """Verify safe calculator handles arithmetic operations without eval()."""
    assert safe_eval_expression("2 + 2") == 4
    assert safe_eval_expression("10 * (5 - 2) / 2") == 15.0
    assert safe_eval_expression("2 ** 8") == 256

    with pytest.raises(ZeroDivisionError):
        safe_eval_expression("10 / 0")

    with pytest.raises(ValueError, match="Unsupported syntax"):
        safe_eval_expression("__import__('os').system('ls')")


@pytest.mark.asyncio
async def test_calculator_tool_execute():
    """Verify CalculatorTool returns structured ToolResult."""
    calc = CalculatorTool()
    ctx = ToolContext(user_id=uuid.uuid4(), session=None)  # type: ignore[arg-type]
    res = await calc.execute(ctx, expression="100 / 4")
    assert res.success is True
    assert res.data["result"] == 25.0


@pytest.mark.asyncio
async def test_system_command_dangerous_blocking():
    """Verify dangerous shell command patterns are blocked."""
    tool = SystemCommandTool()
    ctx = ToolContext(user_id=uuid.uuid4(), session=None)  # type: ignore[arg-type]
    res = await tool.execute(ctx, command="rm -rf / --no-preserve-root")
    assert res.success is False
    assert "Prohibited dangerous pattern" in res.error


# ==============================================================================
# 2. Three-Tier Policy Engine Tests
# ==============================================================================


def test_policy_read_only_allowed():
    """Verify READ_ONLY tools evaluate to ALLOW without approval tokens."""
    policy = PolicyEngine()
    user_id = uuid.uuid4()
    verdict = policy.evaluate(user_id, "calculator", {"expression": "5 + 5"})
    assert verdict.decision == PolicyDecision.ALLOW
    assert verdict.risk_tier == RiskTier.READ_ONLY


def test_policy_mutating_requires_approval():
    """Verify MUTATING tools evaluate to REQUIRE_APPROVAL and issue signed tokens."""
    policy = PolicyEngine()
    user_id = uuid.uuid4()
    args = {"content": "User prefers dark mode", "category": "preference"}
    verdict = policy.evaluate(user_id, "create_note", args)

    assert verdict.decision == PolicyDecision.REQUIRE_APPROVAL
    assert verdict.risk_tier == RiskTier.MUTATING
    assert verdict.approval_token is not None

    # Resubmitting with the signed token produces ALLOW
    resumed = policy.evaluate(user_id, "create_note", args, approval_token=verdict.approval_token)
    assert resumed.decision == PolicyDecision.ALLOW


def test_policy_token_tampering_denied():
    """Verify tampered approval tokens are rejected."""
    policy = PolicyEngine()
    user_id = uuid.uuid4()
    args = {"content": "Safe note", "category": "general"}
    verdict = policy.evaluate(user_id, "create_note", args)

    # Attacker tampers with arguments while reusing token
    tampered_args = {"content": "Malicious injected payload", "category": "general"}
    tampered_verdict = policy.evaluate(
        user_id, "create_note", tampered_args, approval_token=verdict.approval_token
    )
    assert tampered_verdict.decision == PolicyDecision.DENY


def test_policy_token_replay_denied():
    """Verify single-use token cannot be replayed twice."""
    policy = PolicyEngine()
    user_id = uuid.uuid4()
    args = {"content": "One-time note", "category": "general"}
    verdict = policy.evaluate(user_id, "create_note", args)

    # First consumption -> ALLOW
    res1 = policy.evaluate(user_id, "create_note", args, approval_token=verdict.approval_token)
    assert res1.decision == PolicyDecision.ALLOW

    # Replay attempt with same token -> DENY
    res2 = policy.evaluate(user_id, "create_note", args, approval_token=verdict.approval_token)
    assert res2.decision == PolicyDecision.DENY


# ==============================================================================
# 3. Emergency Kill Switch Tests
# ==============================================================================


def test_kill_switch_blocks_policy_and_execution():
    """Verify engaging the kill switch halts all actions immediately."""
    kill_switch.disengage()
    assert not kill_switch.is_engaged

    policy = PolicyEngine()
    user_id = uuid.uuid4()

    # Normal state allows read-only
    assert (
        policy.evaluate(user_id, "calculator", {"expression": "1+1"}).decision
        == PolicyDecision.ALLOW
    )

    # Engage kill switch
    kill_switch.engage(reason="Security incident drill", actor_id="admin-1")
    assert kill_switch.is_engaged

    # Policy immediately returns DENY
    verdict = policy.evaluate(user_id, "calculator", {"expression": "1+1"})
    assert verdict.decision == PolicyDecision.DENY
    assert "kill switch" in verdict.reason.lower()

    # Check method raises exception
    with pytest.raises(KillSwitchActiveError):
        kill_switch.check()

    # Disengage restores service
    kill_switch.disengage()
    assert not kill_switch.is_engaged
    assert (
        policy.evaluate(user_id, "calculator", {"expression": "1+1"}).decision
        == PolicyDecision.ALLOW
    )


# ==============================================================================
# 4. Outcome Verifier Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_outcome_verifier():
    """Verify post-execution verification detects valid and invalid results."""
    ctx = ToolContext(user_id=uuid.uuid4(), session=None)  # type: ignore[arg-type]

    # Valid calculator result
    good_res = ToolResult(success=True, data={"result": 42.0})
    v_good = await outcome_verifier.verify("calculator", {"expression": "40+2"}, good_res, ctx)
    assert v_good.verified is True

    # Corrupted calculator result (missing 'result' key)
    bad_res = ToolResult(success=True, data={"wrong_key": 42.0})
    v_bad = await outcome_verifier.verify("calculator", {"expression": "40+2"}, bad_res, ctx)
    assert v_bad.verified is False


# ==============================================================================
# 5. SKILL.md Parser & Permission Validation Tests
# ==============================================================================


def test_skill_parser_valid():
    """Verify valid SKILL.md frontmatter is parsed and validated."""
    parser = SkillParser(registry=create_default_registry())
    content = (
        "---\n"
        "name: Math Tutor\n"
        "description: Solves arithmetic exercises step by step\n"
        "allowed_tools:\n"
        "  - calculator\n"
        "required_permissions:\n"
        "  - math:read\n"
        "---\n"
        "Always explain each step of the calculation clearly.\n"
    )
    skill = parser.parse(content, user_permissions={"math:read"})
    assert skill.metadata.name == "Math Tutor"
    assert skill.metadata.allowed_tools == ["calculator"]
    assert "Always explain each step" in skill.instructions


def test_skill_parser_unregistered_tool():
    """Verify skill requesting an unknown tool is rejected."""
    parser = SkillParser(registry=create_default_registry())
    content = (
        "---\n"
        "name: Rogue Skill\n"
        "description: Attempts to use unknown tool\n"
        "allowed_tools:\n"
        "  - nonexistent_super_tool\n"
        "---\n"
        "Instructions\n"
    )
    with pytest.raises(SkillValidationError, match="unregistered tool"):
        parser.parse(content)


def test_skill_parser_missing_permission():
    """Verify skill is rejected when caller lacks required permissions."""
    parser = SkillParser(registry=create_default_registry())
    content = (
        "---\n"
        "name: Admin Skill\n"
        "description: Requires privileged scope\n"
        "allowed_tools:\n"
        "  - calculator\n"
        "required_permissions:\n"
        "  - admin:all\n"
        "---\n"
        "Instructions\n"
    )
    with pytest.raises(SkillValidationError, match="lacks required permissions"):
        parser.parse(content, user_permissions={"user:standard"})


# ==============================================================================
# 6. MCP Client SSRF Defense Tests
# ==============================================================================


def test_mcp_client_ssrf_defense():
    """Verify MCP client strictly allows only allowlisted hostnames."""
    client = MCPClient(allowlisted_hosts={"localhost", "127.0.0.1"})
    assert client.is_url_allowed("http://localhost:8000/mcp") is True
    assert client.is_url_allowed("http://127.0.0.1:9090/mcp") is True

    # External, cloud metadata, or unknown domains blocked
    assert client.is_url_allowed("http://169.254.169.254/latest/meta-data") is False
    assert client.is_url_allowed("https://malicious-attacker.com/rpc") is False


# ==============================================================================
# 7. Agent API Endpoints Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_agent_tools_listing_api(app_client: AsyncClient):
    """Verify GET /api/v1/agent/tools lists registered tools and risk tiers."""
    token = await _register_and_get_token(app_client, "agent_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = await app_client.get("/api/v1/agent/tools", headers=headers)
    assert res.status_code == 200
    tools = res.json()
    names = [t["name"] for t in tools]
    assert "calculator" in names
    assert "create_note" in names
    assert "system_command" in names


@pytest.mark.asyncio
async def test_agent_run_direct_answer(app_client: AsyncClient):
    """Verify agent execution that answers directly without tools."""
    token = await _register_and_get_token(app_client, "direct_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = await app_client.post(
        "/api/v1/agent/run",
        headers=headers,
        json={"prompt": "Hello AURA, what can you do?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["final_answer"] is not None


@pytest.mark.asyncio
async def test_agent_kill_switch_api(app_client: AsyncClient):
    """Verify toggling emergency kill switch via API halts execution."""
    token = await _register_and_get_token(app_client, "admin_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Engage kill switch
    engage_res = await app_client.post(
        "/api/v1/agent/kill-switch",
        headers=headers,
        json={"engaged": True, "reason": "Automated security test halt"},
    )
    assert engage_res.status_code == 200
    assert engage_res.json()["is_engaged"] is True

    # 2. Attempt agent run -> BLOCKED
    run_res = await app_client.post(
        "/api/v1/agent/run",
        headers=headers,
        json={"prompt": "Run computation"},
    )
    assert run_res.status_code == 200
    assert run_res.json()["status"] == "BLOCKED"
    assert "kill switch" in run_res.json()["error"].lower()

    # 3. Disengage kill switch
    disengage_res = await app_client.post(
        "/api/v1/agent/kill-switch",
        headers=headers,
        json={"engaged": False},
    )
    assert disengage_res.status_code == 200
    assert disengage_res.json()["is_engaged"] is False
