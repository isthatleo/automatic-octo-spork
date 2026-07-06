import argparse
import json
import logging
import os
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def _design_md_path() -> str:
    """
    The MD lives at repo root (automatic-octo-spork/), not inside nancy-billion/.
    Resolve robustly from this file location.
    """
    nancy_root = os.path.dirname(os.path.dirname(__file__))  # .../nancy-billion
    repo_root = os.path.dirname(nancy_root)  # .../automatic-octo-spork
    return os.path.join(repo_root, "NÅNCY-BILLION OS Sovereign AI  Design.md")


def _registry_out_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "agent_registry.json")


def _normalize_ws(s: str) -> str:
    s = s.replace("\r", "")
    # collapse runs of spaces/tabs
    s = re.sub(r"[ \t]+", " ", s)
    # normalize blank lines
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _clean_noise_lines(lines: List[str]) -> List[str]:
    """
    Remove repeated PDF export artifacts and tiny page markers like:
      Printed using ChatGPT to PDF...
      Show moreShow less
      End of Volume...
    """
    noise_res = [
        r"^Printed using ChatGPT to PDF.*$",
        r"^Show moreShow less.*$",
        r"^Printed using ChatGPT to PDF.*\d+/\d+.*$",
    ]
    out: List[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if any(re.match(p, s) for p in noise_res):
            continue
        # keep markdown headings / content
        out.append(line)
    return out


def _load_design_text() -> Tuple[str, str]:
    md_path = _design_md_path()
    if not os.path.exists(md_path):
        raise FileNotFoundError(f"Design MD not found at: {md_path}")

    with open(md_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # line-based cleaning helps avoid repeated "Printed using ChatGPT..." noise
    lines = _clean_noise_lines(raw.splitlines())
    text = "\n".join(lines)
    text = _normalize_ws(text)
    return text, md_path


def _split_into_agent_like_chunks(text: str, min_chunk_chars: int = 150) -> List[str]:
    """
    Create one "agent-like" chunk per markdown heading.

    The input MD is rich in headings (`## ...`). The safest way to reach
    >=200 chunks is to split on *every* `##` heading and take the content
    until the next `##` heading.
    """
    lines = text.splitlines()

    heading_idxs: List[int] = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            heading_idxs.append(i)

    if not heading_idxs:
        # Fallback: no headings detected -> single chunk.
        return [text] if len(text) >= min_chunk_chars else []

    chunks: List[str] = []
    for hi, start_i in enumerate(heading_idxs):
        end_i = heading_idxs[hi + 1] if hi + 1 < len(heading_idxs) else len(lines)
        chunk_lines = lines[start_i:end_i]

        # Drop empty/noise-only headings
        chunk = "\n".join(chunk_lines).strip()
        if not chunk:
            continue

        # Avoid making chunks that are pure metadata
        if len(chunk) < min_chunk_chars:
            continue

        chunks.append(chunk)

    return chunks


def _infer_category_role(chunk: str) -> Tuple[str, str]:
    c = chunk.lower()

    # Category/domain
    if "memory" in c or "mnemosyne" in c:
        category = "memory"
    elif "decision" in c or "judgment" in c or "planning" in c:
        category = "decision_intelligence"
    elif "agent" in c or "orchestr" in c or "runtime" in c:
        category = "agent_civilization"
    elif "simulation" in c or "digital twin" in c or "policy sandbox" in c:
        category = "simulation"
    elif "security" in c or "anomaly" in c:
        category = "security"
    elif "economy" in c or "treasury" in c or "tax" in c:
        category = "economics"
    elif "govern" in c or "regulatory" in c or "ministry" in c:
        category = "governance"
    elif "voice" in c or "/voice" in c or "companion" in c or "presence" in c:
        category = "voice_ui"
    else:
        category = "general"

    # Role (more specific)
    if "chapter" in c and "chapter" in chunk.lower():
        role = ""
    if "memory" in c and "law" in c:
        role = "memory_governance"
    elif "decision" in c and "engine" in c:
        role = "decision_engine"
    elif "agent" in c and "scheduler" in c:
        role = "agent_scheduler"
    elif "simulation" in c and "engine" in c:
        role = "simulation_engine"
    elif "economy" in c and "engine" in c:
        role = "economic_engine"
    elif "autonomy" in c:
        role = "autonomy_controller"
    elif "companion" in c or "presence" in c:
        role = "companion_layer"
    else:
        role = ""

    return category, role


def _extract_first_heading_name(chunk: str, idx: int) -> str:
    # Prefer first line that looks like a markdown heading.
    for line in chunk.splitlines():
        s = line.strip()
        if s.startswith("## "):
            name = s[3:].strip()
            # strip trailing markdown artifacts
            name = re.sub(r"\s+$", "", name)
            if name:
                return name
    return f"Agent Chunk {idx}"


_TOOL_SYNONYMS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bweb search\b|duckduckgo|scrape|url", re.I), "web_search"),
    (re.compile(r"\bread file\b|open file|file contents", re.I), "read_file"),
    (re.compile(r"\bwrite file\b|save file|create file", re.I), "write_file"),
    (re.compile(r"\bdelete file\b|remove file", re.I), "delete_file"),
    (re.compile(r"\brun (system )?command\b|terminal|process", re.I), "run_process"),
    (re.compile(r"\bapi call\b|http", re.I), "api_call"),
    (re.compile(r"\bsave fact\b|fact memory|recall fact", re.I), "save_fact"),
    (re.compile(r"\bepisode\b|episodic memory|save_episode|recall_episode", re.I), "save_episode"),
    (re.compile(r"\bimage\b|generate image|studio_image", re.I), "generate_image"),
    (re.compile(r"\bvideo\b|generate video", re.I), "generate_video"),
    (re.compile(r"\blip sync\b", re.I), "lip_sync"),
    (re.compile(r"\bgit\b|repository|pull request|issues", re.I), "git_status"),
]

_MEMORY_DOMAIN_SYNONYMS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bfact\b", re.I), "facts"),
    (re.compile(r"\bepisode\b", re.I), "episodes"),
    (re.compile(r"\bmemory\b", re.I), "memory"),
]


def _infer_tool_ids_and_memory(chunk: str) -> Tuple[List[str], List[str]]:
    tools: List[str] = []
    chunk_l = chunk.lower()

    for pat, tool_id in _TOOL_SYNONYMS:
        if pat.search(chunk):
            if tool_id not in tools:
                tools.append(tool_id)

    mems: List[str] = []
    for pat, mem in _MEMORY_DOMAIN_SYNONYMS:
        if pat.search(chunk_l):
            if mem not in mems:
                mems.append(mem)

    return tools, mems


def _build_registry(min_agents: int = 200) -> Dict[str, Any]:
    text, md_path = _load_design_text()

    # Keep many small sections too; Phase 1.9 requires extracting ~200+ specs.
    chunks = _split_into_agent_like_chunks(text, min_chunk_chars=20)

    logger.info(f"Split design MD into {len(chunks)} agent-like chunks")

    agents: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunks, start=1):
        # Use the chunk as system_prompt (trim to keep model prompt manageable).
        system_prompt = chunk.strip()[:3500]

        name = _extract_first_heading_name(chunk, idx)
        category, role = _infer_category_role(chunk)
        tool_ids, memory_domains = _infer_tool_ids_and_memory(chunk)

        key_slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", name.strip().lower())
        key_slug = re.sub(r"_+", "_", key_slug).strip("_")
        if not key_slug:
            key_slug = "agent_chunk"

        # Make keys always unique by including idx (prevents dedup collapse)
        key = f"{key_slug}_{idx}"

        agents.append(
            {
                "key": key,
                "name": name,
                "category": category or "",
                "role": role or "",
                "description": "",
                "system_prompt": system_prompt,
                "tool_ids": tool_ids,
                "memory_domains": memory_domains,
            }
        )

    if len(agents) < min_agents:
        logger.warning(
            f"Parsed {len(agents)} agents; less than min_agents={min_agents}. "
            f"Try lowering min_chunk_chars further."
        )

    # Optionally trim to at least min_agents if we got a lot more.
    agents_out = agents[: max(min_agents, len(agents))]  # keep all if <= min_agents

    registry = {
        "schema_version": 1,
        "source": {
            "md_path": os.path.basename(md_path),
        },
        "generated": True,
        "agents": agents_out,
    }
    return registry


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--min-agents", type=int, default=200, help="Minimum desired agent count")
    parser.add_argument("--out", type=str, default=_registry_out_path(), help="Output path for agent_registry.json")
    args = parser.parse_args()

    out_path = args.out
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    registry = _build_registry(min_agents=args.min_agents)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    logger.info(f"Wrote agent registry: {out_path} (agents={len(registry['agents'])})")


if __name__ == "__main__":
    main()

