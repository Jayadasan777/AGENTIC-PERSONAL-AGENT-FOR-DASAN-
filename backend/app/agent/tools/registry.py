"""Central registry for managing, discovering, and schema-exporting Agent Tools."""

from __future__ import annotations

from backend.app.agent.tools.base import AgentTool
from backend.app.agent.tools.calculator import CalculatorTool
from backend.app.agent.tools.documents import DocumentSearchTool
from backend.app.agent.tools.memory import CreateNoteTool, MemorySearchTool
from backend.app.agent.tools.sandbox import CodeExecutionTool
from backend.app.agent.tools.system import SystemCommandTool


class ToolRegistry:
    """Stores and resolves tools available to the AURA Agent Harness."""

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        """Register a new tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool | None:
        """Look up tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[AgentTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_schemas(self) -> list[dict]:
        """Export all tool JSON schemas for LLM tool calling."""
        return [tool.to_schema() for tool in self._tools.values()]


def create_default_registry() -> ToolRegistry:
    """Instantiate and populate registry with built-in tools."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(MemorySearchTool())
    registry.register(CreateNoteTool())
    registry.register(DocumentSearchTool())
    registry.register(SystemCommandTool())
    registry.register(CodeExecutionTool())
    return registry


_default_registry = create_default_registry()


def get_tool_registry() -> ToolRegistry:
    """Return the global default tool registry."""
    return _default_registry
