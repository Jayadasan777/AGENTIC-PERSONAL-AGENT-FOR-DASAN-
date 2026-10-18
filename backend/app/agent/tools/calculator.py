"""Safe AST-based arithmetic calculator tool without eval()."""

from __future__ import annotations

import ast
import operator
from typing import Any

from pydantic import BaseModel, Field

from backend.app.agent.tools.base import AgentTool, RiskTier, ToolContext, ToolResult

# Allowed AST math operations
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> float | int:
    """Recursively evaluate AST node containing only arithmetic."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in OPERATORS:
            raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero")
        return OPERATORS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return OPERATORS[op_type](_eval_node(node.operand))
    raise ValueError(f"Unsupported syntax in expression: {type(node).__name__}")


def safe_eval_expression(expression: str) -> float | int:
    """Evaluate a mathematical expression string using safe AST parsing."""
    cleaned = expression.strip()
    if not cleaned:
        raise ValueError("Expression cannot be empty")
    # Limit length to prevent parser exhaustion
    if len(cleaned) > 200:
        raise ValueError("Expression is too long (max 200 characters)")
    parsed = ast.parse(cleaned, mode="eval")
    return _eval_node(parsed.body)


class CalculatorArgs(BaseModel):
    """Input parameters for arithmetic calculation."""

    expression: str = Field(
        ...,
        description="Mathematical expression to evaluate (e.g. '125 * 4 + (30 / 2)').",
    )


class CalculatorTool(AgentTool):
    """Safe mathematical calculator tool for deterministic arithmetic."""

    name = "calculator"
    description = (
        "Evaluate mathematical and arithmetic expressions accurately and safely. "
        "Supports addition (+), subtraction (-), multiplication (*), division (/), "
        "modulo (%), and power (**)."
    )
    risk_tier = RiskTier.READ_ONLY
    args_schema = CalculatorArgs

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        """Safely compute mathematical expression."""
        expr = kwargs.get("expression", "")
        try:
            result = safe_eval_expression(expr)
            return ToolResult(
                success=True,
                data={"expression": expr, "result": result},
            )
        except Exception as err:
            return ToolResult(
                success=False,
                error=f"Calculation error: {err}",
            )
