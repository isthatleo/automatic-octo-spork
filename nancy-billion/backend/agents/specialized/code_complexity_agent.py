"""
Code Complexity Agent for Nancy/Billion.
Real AST-based static metrics on a real code string (Python) -- actual
parsed structure, not an LLM's guess at "how complex" code looks.
"""
from __future__ import annotations

import ast
from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent

_BRANCH_NODES = (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.BoolOp, ast.ExceptHandler)


class CodeComplexityAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Code Complexity Agent", "code-complexity")
        self.capabilities.update({
            "description": "Real AST-based Python code metrics: functions, classes, branch count, an approximate cyclomatic complexity",
            "confidence": 0.8,
            "specializations": ["static-analysis", "cyclomatic-complexity"],
            "tools": ["ast"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "analyze":
            return self._analyze(task_data.get("code", ""))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    def _analyze(self, code: str) -> Dict[str, Any]:
        if not code.strip():
            return {"success": False, "error": "code is required"}
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {"success": False, "error": f"Syntax error: {e}"}

        functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        branches = sum(1 for n in ast.walk(tree) if isinstance(n, _BRANCH_NODES))
        # Approximate cyclomatic complexity: 1 (base path) + one per branch node.
        cyclomatic_complexity = 1 + branches
        lines = code.count("\n") + 1

        per_function = []
        for fn in functions:
            fn_branches = sum(1 for n in ast.walk(fn) if isinstance(n, _BRANCH_NODES))
            per_function.append({"name": fn.name, "approx_complexity": 1 + fn_branches, "arg_count": len(fn.args.args)})

        return {
            "success": True,
            "line_count": lines,
            "function_count": len(functions),
            "class_count": len(classes),
            "branch_count": branches,
            "approx_cyclomatic_complexity": cyclomatic_complexity,
            "functions": per_function,
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I compute real AST-based metrics on Python code: function/class counts, branch count, and approximate cyclomatic complexity."
        )}
