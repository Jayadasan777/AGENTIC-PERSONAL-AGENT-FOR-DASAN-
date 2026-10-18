"""User-managed SKILL.md parser, schema validator, and permission enforcer."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml
from pydantic import BaseModel, Field

from backend.app.agent.tools.registry import ToolRegistry, get_tool_registry


class SkillValidationError(Exception):
    """Raised when a SKILL.md document fails syntax or permission checks."""


class SkillMetadata(BaseModel):
    """Frontmatter metadata structure for a custom agent skill."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    version: str = Field(default="1.0.0")
    allowed_tools: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)


@dataclass
class LoadedSkill:
    """Parsed and validated skill ready for agent activation."""

    metadata: SkillMetadata
    instructions: str
    active: bool = True
    attributes: dict[str, Any] = field(default_factory=dict)


class SkillParser:
    """Parses markdown files with YAML frontmatter into verified agent skills."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or get_tool_registry()

    def parse(
        self,
        content: str,
        user_permissions: set[str] | None = None,
    ) -> LoadedSkill:
        """Parse raw SKILL.md markdown text and validate tools and permissions."""
        user_perms = user_permissions or {"*"}

        # Extract YAML frontmatter enclosed by ---
        pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
        match = re.match(pattern, content.strip(), re.DOTALL)
        if not match:
            raise SkillValidationError(
                "Invalid SKILL.md format: missing YAML frontmatter enclosed in '---'."
            )

        frontmatter_raw, instructions = match.groups()
        try:
            parsed_yaml = yaml.safe_load(frontmatter_raw)
            if not isinstance(parsed_yaml, dict):
                raise SkillValidationError("Skill frontmatter must be a valid YAML mapping.")
            metadata = SkillMetadata.model_validate(parsed_yaml)
        except Exception as err:
            raise SkillValidationError(f"Failed to parse skill frontmatter: {err}") from err

        # 1. Validate that all declared allowed_tools exist in registry
        for tool_name in metadata.allowed_tools:
            if not self.registry.get(tool_name):
                raise SkillValidationError(f"Skill references unregistered tool '{tool_name}'.")

        # 2. Validate that user holds all required permissions
        if "*" not in user_perms:
            missing = [p for p in metadata.required_permissions if p not in user_perms]
            if missing:
                raise SkillValidationError(
                    f"User lacks required permissions to activate skill "
                    f"'{metadata.name}': {missing}"
                )

        return LoadedSkill(
            metadata=metadata,
            instructions=instructions.strip(),
        )


skill_parser = SkillParser()
