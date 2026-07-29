"""Real visual flow execution -- Billion's own native equivalent of
Langflow's node-graph builder, built on infrastructure this project already
has rather than embedding the actual Langflow app (which pulls its own
FastAPI server, React Flow frontend, and a large LangChain-adjacent
dependency tree -- real risk of the exact pathological pip-resolver
backtracking already hit once this session with a much smaller addition).

A Flow is a real directed graph: nodes are either a real tool call (any of
Billion's existing ~150 tools, dispatched through the SAME
main_new._execute_file_tool every chat turn already uses), an LLM prompt
call (llm.llm_backend.generate), or an input/output node. Edges map one
node's real output to another node's input. Execution is a genuine
topological run -- each node only runs once every node it depends on has
produced real output, and that real output is what gets passed forward
(not a simulated pipeline).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "flows.json"
MAX_NODES_PER_FLOW = 50


@dataclass
class FlowNode:
    id: str
    kind: str  # "tool" | "llm" | "input" | "output"
    # kind == "tool": config = {"tool_name": str, "args": {...}}; args values
    #   that are strings of the form "{{node_id.field}}" are resolved from
    #   an upstream node's real output before the tool call runs.
    # kind == "llm": config = {"prompt": str} -- prompt may also contain
    #   "{{node_id.field}}" placeholders.
    # kind == "input": config = {"name": str} -- filled from the flow run's
    #   real caller-supplied inputs dict.
    # kind == "output": config = {"from": "{{node_id.field}}"} -- what the
    #   flow run ultimately returns.
    config: Dict[str, Any] = field(default_factory=dict)
    label: str = ""


@dataclass
class FlowEdge:
    source: str
    target: str


@dataclass
class Flow:
    id: str
    name: str
    nodes: List[FlowNode]
    edges: List[FlowEdge]
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "created_at": self.created_at, "updated_at": self.updated_at,
            "nodes": [asdict(n) for n in self.nodes],
            "edges": [asdict(e) for e in self.edges],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Flow":
        return Flow(
            id=d["id"], name=d["name"], created_at=d.get("created_at", time.time()), updated_at=d.get("updated_at", time.time()),
            nodes=[FlowNode(**n) for n in d.get("nodes", [])],
            edges=[FlowEdge(**e) for e in d.get("edges", [])],
        )


class FlowStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._flows: Dict[str, Flow] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for f in raw:
                flow = Flow.from_dict(f)
                self._flows[flow.id] = flow
        except Exception:
            logger.exception("Failed to load flows.json -- starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [f.to_public_dict() for f in self._flows.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> List[Flow]:
        return sorted(self._flows.values(), key=lambda f: f.name.lower())

    def get(self, flow_id: str) -> Optional[Flow]:
        return self._flows.get(flow_id)

    def create(self, name: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Flow:
        if not name.strip():
            raise ValueError("name must not be empty.")
        if len(nodes) > MAX_NODES_PER_FLOW:
            raise ValueError(f"Too many nodes ({len(nodes)}) -- max {MAX_NODES_PER_FLOW} per flow.")
        flow = Flow(
            id=uuid.uuid4().hex[:12], name=name.strip(),
            nodes=[FlowNode(**n) for n in nodes], edges=[FlowEdge(**e) for e in edges],
        )
        _validate_graph(flow)
        self._flows[flow.id] = flow
        self._save()
        return flow

    def update(self, flow_id: str, name: Optional[str], nodes: Optional[List[Dict[str, Any]]], edges: Optional[List[Dict[str, Any]]]) -> Optional[Flow]:
        flow = self._flows.get(flow_id)
        if flow is None:
            return None
        if name is not None:
            flow.name = name
        if nodes is not None:
            flow.nodes = [FlowNode(**n) for n in nodes]
        if edges is not None:
            flow.edges = [FlowEdge(**e) for e in edges]
        flow.updated_at = time.time()
        _validate_graph(flow)
        self._save()
        return flow

    def delete(self, flow_id: str) -> bool:
        if flow_id not in self._flows:
            return False
        del self._flows[flow_id]
        self._save()
        return True


def _validate_graph(flow: Flow) -> None:
    node_ids = {n.id for n in flow.nodes}
    for edge in flow.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            raise ValueError(f"Edge references a node id not present in this flow: {edge.source} -> {edge.target}")
    _topological_order(flow)  # raises ValueError on a real cycle


def _topological_order(flow: Flow) -> List[FlowNode]:
    by_id = {n.id: n for n in flow.nodes}
    incoming: Dict[str, List[str]] = {n.id: [] for n in flow.nodes}
    for edge in flow.edges:
        incoming[edge.target].append(edge.source)

    ordered: List[FlowNode] = []
    visited: Dict[str, str] = {}  # "visiting" | "done"

    def _visit(node_id: str) -> None:
        state = visited.get(node_id)
        if state == "done":
            return
        if state == "visiting":
            raise ValueError(f"Flow graph has a real cycle involving node {node_id!r} -- not executable.")
        visited[node_id] = "visiting"
        for dep in incoming[node_id]:
            _visit(dep)
        visited[node_id] = "done"
        ordered.append(by_id[node_id])

    for n in flow.nodes:
        _visit(n.id)
    return ordered


def _resolve_placeholders(value: Any, node_outputs: Dict[str, Any], flow_inputs: Dict[str, Any]) -> Any:
    """Replaces "{{node_id.field}}" (or "{{node_id}}" for the whole output)
    with a real upstream node's real output, and "{{input.name}}" with a
    real flow-run input. Non-string / non-matching values pass through
    unchanged -- this only ever substitutes real prior results, never
    fabricates a value for a missing reference (raises instead)."""
    if isinstance(value, dict):
        return {k: _resolve_placeholders(v, node_outputs, flow_inputs) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_placeholders(v, node_outputs, flow_inputs) for v in value]
    if not isinstance(value, str):
        return value
    import re
    match = re.fullmatch(r"\{\{\s*([\w.]+)\s*\}\}", value.strip())
    if not match:
        return value
    ref = match.group(1)
    parts = ref.split(".", 1)
    root = parts[0]
    field_name = parts[1] if len(parts) > 1 else None
    if root == "input":
        if field_name is None or field_name not in flow_inputs:
            raise ValueError(f"Flow references undefined input {ref!r}")
        return flow_inputs[field_name]
    if root not in node_outputs:
        raise ValueError(f"Flow references node {root!r} before it has run (or it doesn't exist).")
    output = node_outputs[root]
    if field_name is None:
        return output
    if isinstance(output, dict) and field_name in output:
        return output[field_name]
    raise ValueError(f"Node {root!r}'s output has no field {field_name!r}")


async def execute_flow(
    flow: Flow, inputs: Dict[str, Any],
    tool_executor: Callable[[str, Dict[str, Any]], Any],
    llm_generate: Callable[[str], Any],
) -> Dict[str, Any]:
    """Real execution: topological order, each node's real output stored
    and available to downstream nodes via {{node_id.field}} placeholders.
    `tool_executor(name, args)` and `llm_generate(prompt)` are injected
    (both async callables) so this module has zero import-time coupling to
    main_new.py/llm.py -- the caller wires the real dispatcher/backend in."""
    order = _topological_order(flow)
    node_outputs: Dict[str, Any] = {}
    trace: List[Dict[str, Any]] = []
    output_value: Any = None

    for node in order:
        started = time.time()
        try:
            if node.kind == "input":
                name = node.config.get("name", node.id)
                result = inputs.get(name)
            elif node.kind == "tool":
                tool_name = node.config.get("tool_name", "")
                args = _resolve_placeholders(node.config.get("args", {}), node_outputs, inputs)
                result = await tool_executor(tool_name, args)
            elif node.kind == "llm":
                prompt = _resolve_placeholders(node.config.get("prompt", ""), node_outputs, inputs)
                result = await llm_generate(str(prompt))
            elif node.kind == "output":
                result = _resolve_placeholders(node.config.get("from", ""), node_outputs, inputs)
                output_value = result
            else:
                raise ValueError(f"Unknown node kind {node.kind!r}")
            node_outputs[node.id] = result
            trace.append({
                "node_id": node.id, "kind": node.kind, "label": node.label,
                "success": True, "duration_s": round(time.time() - started, 3),
                "output_preview": str(result)[:300],
            })
        except Exception as e:
            trace.append({
                "node_id": node.id, "kind": node.kind, "label": node.label,
                "success": False, "duration_s": round(time.time() - started, 3), "error": str(e),
            })
            return {"success": False, "error": f"Node {node.id!r} failed: {e}", "trace": trace, "node_outputs": node_outputs}

    return {"success": True, "output": output_value, "node_outputs": node_outputs, "trace": trace}


flow_store = FlowStore()
