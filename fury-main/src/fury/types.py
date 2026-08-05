from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Literal, Optional


@dataclass
class ToolResult:
    content: Any
    output_schema: Optional[Dict[str, Any]] = None


@dataclass
class Tool:
    name: str
    description: str
    execute: Callable[..., Any]
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]


@dataclass
class ToolCallEvent:
    tool_name: str
    arguments: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None


@dataclass
class ToolUiEvent:
    id: str
    title: str
    type: Literal["tool_call", "other"]
    metadata: Any = None


@dataclass
class ChatStreamEvent:
    content: Optional[str] = None
    reasoning: Optional[str] = None
    tool_call: Optional[ToolCallEvent] = None
    tool_ui: Optional[ToolUiEvent] = None
    # Set by runtime.chat()'s exception handler when `content` is an error
    # message rather than real model output, so a caller accumulating
    # `.content` across the stream (e.g. FuryLLM.generate() in nancy-billion)
    # can tell a connection failure apart from an actual reply instead of
    # silently treating the exception text as if the model had said it.
    error: bool = False


def create_tool(
    id: str,
    description: str,
    execute: Callable[..., Any],
    input_schema: Dict[str, Any],
    output_schema: Dict[str, Any],
) -> Tool:
    """Create a Tool instance from the provided metadata and callbacks."""
    return Tool(
        name=id,
        description=description,
        execute=execute,
        input_schema=input_schema,
        output_schema=output_schema,
    )
