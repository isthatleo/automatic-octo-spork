import logging
import os
import subprocess
import json
import shutil
import time
import re
from typing import Any, Dict, List, Optional
from fury.types import create_tool

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover
    BeautifulSoup = None


logger = logging.getLogger(__name__)

def echo_execute(text: str) -> str:
    """Simple echo tool for testing."""
    logger.info(f"Echo tool called with: {text}")
    return f"Echo: {text}"

# =============================================================================
# System Control Tools
# =============================================================================

def open_app_execute(app_name: str) -> str:
    """Open an application (platform-specific)."""
    logger.info(f"Opening app: {app_name}")
    try:
        if os.name == 'nt':  # Windows
            os.startfile(app_name)
        elif os.name == 'posix':
            subprocess.Popen(['open', app_name])  # macOS
            # For Linux, could use subprocess.Popen(['xdg-open', app_name])
        else:
            logger.warning(f"Unsupported OS for opening app: {os.name}")
            return f"Failed to open {app_name}: unsupported OS"
        return f"Opened {app_name}"
    except Exception as e:
        logger.error(f"Error opening app {app_name}: {e}")
        return f"Error opening {app_name}: {e}"

def close_app_execute(app_name: str) -> str:
    """Close an application by name (platform-specific)."""
    logger.info(f"Closing app: {app_name}")
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/IM', f'{app_name}.exe', '/F'], check=False)
        else:
            subprocess.run(['pkill', '-f', app_name], check=False)
        return f"Closed {app_name}"
    except Exception as e:
        logger.error(f"Error closing app {app_name}: {e}")
        return f"Error closing {app_name}: {e}"

def list_files_execute(directory: str = ".") -> str:
    """List files in a directory."""
    logger.info(f"Listing files in: {directory}")
    try:
        files = os.listdir(directory)
        return json.dumps(files)
    except Exception as e:
        logger.error(f"Error listing files in {directory}: {e}")
        return f"Error listing files: {e}"

def read_file_execute(filepath: str) -> str:
    """Read contents of a file."""
    logger.info(f"Reading file: {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        logger.error(f"Error reading file {filepath}: {e}")
        return f"Error reading file: {e}"

def write_file_execute(filepath: str, content: str) -> str:
    """Write content to a file."""
    logger.info(f"Writing to file: {filepath}")
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Written to {filepath}"
    except Exception as e:
        logger.error(f"Error writing file {filepath}: {e}")
        return f"Error writing file: {e}"

def delete_file_execute(filepath: str) -> str:
    """Delete a file."""
    logger.info(f"Deleting file: {filepath}")
    try:
        os.remove(filepath)
        return f"Deleted {filepath}"
    except Exception as e:
        logger.error(f"Error deleting file {filepath}: {e}")
        return f"Error deleting file: {e}"

def run_process_execute(command: str) -> str:
    """Run a system command and return stdout."""
    logger.info(f"Running command: {command}")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        output = result.stdout
        if result.stderr:
            output += "\nSTDERR: " + result.stderr
        return output
    except subprocess.TimeoutExpired:
        return "Command timed out"
    except Exception as e:
        logger.error(f"Error running command {command}: {e}")
        return f"Error running command: {e}"

def kill_process_execute(pid: int) -> str:
    """Kill a process by PID."""
    logger.info(f"Killing process PID: {pid}")
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(pid), '/F'], check=False)
        else:
            subprocess.run(['kill', '-9', str(pid)], check=False)
        return f"Killed process {pid}"
    except Exception as e:
        logger.error(f"Error killing process {pid}: {e}")
        return f"Error killing process: {e}"

# =============================================================================
# Developer Assistance Tools
# =============================================================================

def run_code_execute(code: str, language: str = "python") -> str:
    """Run a snippet of code (currently only Python)."""
    logger.info(f"Running {language} code")
    if language.lower() != "python":
        return f"Unsupported language: {language}"
    try:
        # Use exec in a restricted environment? For simplicity, we'll just eval.
        # WARNING: This is unsafe; in production use a sandbox.
        local_vars = {}
        exec(code, {}, local_vars)
        # If there's a variable named 'result', return it; else return str of locals
        if 'result' in local_vars:
            return str(local_vars['result'])
        else:
            return str(local_vars)
    except Exception as e:
        logger.error(f"Error running code: {e}")
        return f"Error running code: {e}"

def git_status_execute(repo_path: str = ".") -> str:
    """Run git status in a repository."""
    logger.info(f"Running git status in {repo_path}")
    try:
        result = subprocess.run(['git', 'status'], cwd=repo_path, capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        logger.error(f"Error running git status: {e}")
        return f"Error running git status: {e}"

def git_commit_execute(repo_path: str, message: str) -> str:
    """Git add all and commit."""
    logger.info(f"Git commit in {repo_path} with message: {message}")
    try:
        subprocess.run(['git', 'add', '.'], cwd=repo_path, check=True)
        result = subprocess.run(['git', 'commit', '-m', message], cwd=repo_path, capture_output=True, text=True)
        if result.returncode == 0:
            return f"Commit successful: {result.stdout}"
        else:
            return f"Commit failed: {result.stderr}"
    except Exception as e:
        logger.error(f"Error during git commit: {e}")
        return f"Error during git commit: {e}"

def run_terminal_command_execute(command: str) -> str:
    """Run an arbitrary terminal command (same as run_process)."""
    return run_process_execute(command)

# =============================================================================
# Web & Data Tools
# =============================================================================

def web_search_execute(query: str, num_results: int = 5) -> str:
    """Perform a web search (best-effort).

    Priority:
    1) DuckDuckGo HTML results scraping (no API key)
    """
    logger.info(f"Web search for: {query}")

    if requests is None or BeautifulSoup is None:
        return "Web search unavailable: install 'requests' and 'beautifulsoup4'."

    try:
        # DuckDuckGo HTML endpoint
        url = "https://duckduckgo.com/html/"
        params = {"q": query}
        resp = requests.get(url, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict[str, str]] = []

        # DuckDuckGo typically uses result links inside a table/div.
        for a in soup.select("a.result__a"):
            href = a.get("href")
            title = a.get_text(strip=True)
            if href and title:
                results.append({"title": title, "url": href})
            if len(results) >= num_results:
                break

        # Fallback selector
        if not results:
            for a in soup.select("a.result-link"):
                href = a.get("href")
                title = a.get_text(strip=True)
                if href and title:
                    results.append({"title": title, "url": href})
                if len(results) >= num_results:
                    break

        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return f"Web search error: {e}"


def scrape_url_execute(url: str, max_chars: int = 40000) -> str:
    """Scrape a URL and return readable text (best-effort)."""
    logger.info(f"Scraping URL: {url}")

    if requests is None or BeautifulSoup is None:
        return "Scrape unavailable: install 'requests' and 'beautifulsoup4'."

    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script/style
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        # Light cleanup
        text = re.sub(r"\n{3,}", "\n\n", text)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[TRUNCATED]"

        return text
    except Exception as e:
        logger.error(f"Scrape error: {e}")
        return f"Scrape error: {e}"


def api_call_execute(url: str, method: str = "GET", data: str = None, headers_json: str = "{}") -> str:
    """Make an HTTP API call (best-effort).

    - If response is JSON, pretty-print it.
    - Otherwise return response text.
    """
    logger.info(f"API call {method} {url}")

    if requests is None:
        return "API call unavailable: install 'requests'."

    try:
        headers: dict[str, str] = {}
        if headers_json:
            try:
                headers = json.loads(headers_json)
            except Exception:
                headers = {}

        m = method.upper().strip()
        kwargs: dict[str, Any] = {"timeout": 20, "headers": headers}

        if data is None:
            data = ""

        # If data looks like JSON, send as JSON; else as raw text.
        if data and isinstance(data, str):
            stripped = data.strip()
            if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
                try:
                    kwargs["json"] = json.loads(stripped)
                except Exception:
                    kwargs["data"] = data
            else:
                kwargs["data"] = data

        resp = requests.request(m, url, **kwargs)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                return json.dumps(resp.json(), ensure_ascii=False, indent=2)
            except Exception:
                pass

        return resp.text
    except Exception as e:
        logger.error(f"API call error: {e}")
        return f"API call error: {e}" 


# =============================================================================
# Media Generation Tools (Open Generative AI wrappers)
# =============================================================================

def _ogai_settings() -> dict[str, str]:
    return {
        "api_key": os.getenv("OGAI_API_KEY", ""),
        "studio_image": os.getenv("OGAI_IMAGE_STUDIO_URL", ""),
        "studio_video": os.getenv("OGAI_VIDEO_STUDIO_URL", ""),
        "studio_lip": os.getenv("OGAI_LIP_SYNC_STUDIO_URL", ""),
        "studio_cinema": os.getenv("OGAI_CINEMA_STUDIO_URL", ""),
    }


def generate_image_execute(prompt: str, model: str = "default", width: int = 512, height: int = 512) -> str:
    """Generate an image via Open Generative AI (best-effort wrapper).

    Uses environment variables:
    - OGAI_IMAGE_STUDIO_URL
    - OGAI_API_KEY
    """
    logger.info(f"Generating image: {prompt}")

    settings = _ogai_settings()
    studio = settings["studio_image"]
    api_key = settings["api_key"]

    if not studio:
        return "Image generation unavailable: set OGAI_IMAGE_STUDIO_URL"

    if requests is None:
        return "Image generation unavailable: install 'requests'"

    try:
        payload = {
            "prompt": prompt,
            "model": model,
            "width": width,
            "height": height,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        resp = requests.post(studio, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()

        # best-effort: if json has url/path
        try:
            j = resp.json()
            for k in ("url", "image_url", "result_url", "path"):
                if k in j:
                    return str(j[k])
            return json.dumps(j, ensure_ascii=False, indent=2)
        except Exception:
            return resp.text
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return f"Image generation error: {e}"


def generate_video_execute(prompt: str, model: str = "default", duration_sec: int = 5) -> str:
    """Generate a video via Open Generative AI (best-effort wrapper)."""
    logger.info(f"Generating video: {prompt}")

    settings = _ogai_settings()
    studio = settings["studio_video"]
    api_key = settings["api_key"]

    if not studio:
        return "Video generation unavailable: set OGAI_VIDEO_STUDIO_URL"
    if requests is None:
        return "Video generation unavailable: install 'requests'"

    try:
        payload = {
            "prompt": prompt,
            "model": model,
            "duration_sec": duration_sec,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        resp = requests.post(studio, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        try:
            j = resp.json()
            for k in ("url", "video_url", "result_url", "path"):
                if k in j:
                    return str(j[k])
            return json.dumps(j, ensure_ascii=False, indent=2)
        except Exception:
            return resp.text
    except Exception as e:
        logger.error(f"Video generation error: {e}")
        return f"Video generation error: {e}"


def lip_sync_execute(video_path: str, audio_path: str) -> str:
    """Lip-sync a video via Open Generative AI (best-effort wrapper)."""
    logger.info(f"Lip-syncing {video_path} with {audio_path}")

    settings = _ogai_settings()
    studio = settings["studio_lip"]
    api_key = settings["api_key"]

    if not studio:
        return "Lip-sync unavailable: set OGAI_LIP_SYNC_STUDIO_URL"
    if requests is None:
        return "Lip-sync unavailable: install 'requests'"

    try:
        if not os.path.exists(video_path):
            return f"Video path not found: {video_path}"
        if not os.path.exists(audio_path):
            return f"Audio path not found: {audio_path}"

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        with open(video_path, "rb") as vf, open(audio_path, "rb") as af:
            files = {
                "video": (os.path.basename(video_path), vf),
                "audio": (os.path.basename(audio_path), af),
            }
            resp = requests.post(studio, files=files, headers=headers, timeout=180)
        resp.raise_for_status()

        try:
            j = resp.json()
            for k in ("url", "video_url", "result_url", "path"):
                if k in j:
                    return str(j[k])
            return json.dumps(j, ensure_ascii=False, indent=2)
        except Exception:
            return resp.text
    except Exception as e:
        logger.error(f"Lip-sync error: {e}")
        return f"Lip-sync error: {e}"


def cinema_execute(prompt: str, model: str = "default", length_sec: int = 10) -> str:
    """Generate a cinema scene via Open Generative AI (best-effort wrapper)."""
    logger.info(f"Generating cinema: {prompt}")

    settings = _ogai_settings()
    studio = settings["studio_cinema"]
    api_key = settings["api_key"]

    if not studio:
        return "Cinema generation unavailable: set OGAI_CINEMA_STUDIO_URL"
    if requests is None:
        return "Cinema generation unavailable: install 'requests'"

    try:
        payload = {
            "prompt": prompt,
            "model": model,
            "length_sec": length_sec,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        resp = requests.post(studio, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        try:
            j = resp.json()
            for k in ("url", "video_url", "result_url", "path"):
                if k in j:
                    return str(j[k])
            return json.dumps(j, ensure_ascii=False, indent=2)
        except Exception:
            return resp.text
    except Exception as e:
        logger.error(f"Cinema generation error: {e}")
        return f"Cinema generation error: {e}"


# =============================================================================
# Memory Operations Tools
# =============================================================================

# =============================================================================
# Persistent Memory Operations
# =============================================================================

_memory_store: Dict[str, Any] = {
    "facts": {},     # key -> fact text
    "episodes": []  # list of episode dicts
}


def _memory_root() -> str:
    root = os.getenv("MEMORY_ROOT", "./data/fury_memory")
    return root


def _ensure_memory_dirs() -> None:
    os.makedirs(_memory_root(), exist_ok=True)


def _memory_paths() -> dict[str, str]:
    root = _memory_root()
    return {
        "facts": os.path.join(root, "facts.json"),
        "episodes": os.path.join(root, "episodes.json"),
    }


def _load_memory_from_disk() -> None:
    """Load facts + episodes into the in-process cache."""
    try:
        _ensure_memory_dirs()
        paths = _memory_paths()

        facts_path = paths["facts"]
        episodes_path = paths["episodes"]

        if os.path.exists(facts_path):
            with open(facts_path, "r", encoding="utf-8") as f:
                _memory_store["facts"] = json.load(f) or {}

        if os.path.exists(episodes_path):
            with open(episodes_path, "r", encoding="utf-8") as f:
                _memory_store["episodes"] = json.load(f) or []
    except Exception as e:
        logger.error(f"Failed to load memory from disk: {e}")


def _persist_memory_to_disk() -> None:
    try:
        _ensure_memory_dirs()
        paths = _memory_paths()
        with open(paths["facts"], "w", encoding="utf-8") as f:
            json.dump(_memory_store["facts"], f, ensure_ascii=False, indent=2)
        with open(paths["episodes"], "w", encoding="utf-8") as f:
            json.dump(_memory_store["episodes"], f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to persist memory to disk: {e}")


_load_memory_from_disk()


def save_fact_execute(key: str, fact: str) -> str:
    """Save a fact with a key (persisted)."""
    logger.info(f"Saving fact with key: {key}")
    _memory_store["facts"][key] = fact
    _persist_memory_to_disk()
    return f"Fact saved with key {key}"


def recall_fact_execute(key: str) -> str:
    """Recall a fact by key (persisted)."""
    logger.info(f"Recalling fact with key: {key}")
    fact = _memory_store["facts"].get(key)
    if fact is None:
        return f"No fact found for key {key}"
    return fact


def list_facts_execute() -> str:
    """List all fact keys (persisted)."""
    logger.info("Listing all facts")
    return json.dumps(list(_memory_store["facts"].keys()))


def save_episode_execute(episode: Dict[str, Any]) -> str:
    """Save an episode (a dict) to episodic memory (persisted)."""
    title = episode.get("title") or episode.get("summary") or "unnamed"
    logger.info(f"Saving episode: {title}")
    _memory_store["episodes"].append(episode)
    _persist_memory_to_disk()
    return f"Episode saved, total episodes: {len(_memory_store['episodes'])}"


def recall_episode_execute(index: int) -> str:
    """Recall an episode by index (persisted)."""
    logger.info(f"Recalling episode index: {index}")
    try:
        episode = _memory_store["episodes"][index]
        return json.dumps(episode)
    except IndexError:
        return f"No episode at index {index}"

# =============================================================================
# Agent Generation Tools
# =============================================================================

# =============================================================================
# Agent Generation Tools (registry-backed)
# =============================================================================

# Note: Fury tool execution happens inside the core server process.
# We keep these tools as "control-plane" helpers. Actual instantiation
# of specialized Fury Agents is handled in backend/main.py on demand.


def spawn_agent_execute(role_prompt: str, tools: List[str] = None) -> str:
    """Spawn a new specialized agent.

    In the registry-backed architecture, `role_prompt` can be either:
    - an `agent_key` present in data/agent_registry.json
    - or an ad-hoc prompt (fallback: returns a control message)

    The core server will decide whether to interpret role_prompt as a key.
    """
    logger.info(f"spawn_agent called with role_prompt={role_prompt!r}")
    # This tool is primarily for the model/LLM to request specialized agents.
    # Returning structured text is enough; backend/main.py will also expose
    # direct tool execution for running a specialized agent.
    return json.dumps(
        {
            "ok": True,
            "requested": {
                "agent_key_or_prompt": role_prompt,
                "tool_ids": tools or [],
            }
        },
        ensure_ascii=False,
    )


def run_specialized_agent_execute(agent_key: str, input_text: str) -> str:
    """Run a specialized agent by registry key.

    This calls backend/agent_executor.py which instantiates a Fury Agent on demand
    using the registry's system_prompt and allowed tool set.
    """
    try:
        import asyncio
        from agent_executor import run_specialized_agent

        # If already in an event loop, we can't blockingly wait; Fury tool execution
        # in this project is synchronous, so we run a new loop.
        return asyncio.run(run_specialized_agent(agent_key=agent_key, input_text=input_text))
    except RuntimeError as e:
        # Common case: running within an existing loop (depends on Fury integration).
        # Fall back to running in a new task via a simple loop helper.
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



def list_agents_execute() -> str:
    """List available agent specs from the registry."""
    try:
        from agent_registry import load_registry

        reg = load_registry()
        return json.dumps({"agents": reg.keys}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Tool Registration
# =============================================================================

def get_tools() -> List[Any]:
    """
    Return a list of Tool objects to be registered with the Agent.

    NOTE:
    This module is used by the Fury Agent. Tool IDs are part of the external contract.
    """
    tools = []

    # Helper to add a tool
    def add_tool(tool_id: str, description: str, execute_func, input_schema: Dict, output_schema: Dict):
        tool = create_tool(
            id=tool_id,
            description=description,
            execute=execute_func,
            input_schema=input_schema,
            output_schema=output_schema
        )
        tools.append(tool)

# --- System Control ---
    add_tool(
        "open_app",
        "Open an application by name.",
        open_app_execute,

        {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "Name or path of the application to open"}
            },
            "required": ["app_name"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Status message"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "close_app",
        "Close an application by name.",
        close_app_execute,
        {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "Name of the application to close"}
            },
            "required": ["app_name"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Status message"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "list_files",
        "List files in a directory.",
        list_files_execute,
        {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory path (default: \".\")", "default": "."}
            },
            "required": []
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "JSON array of file names"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "read_file",
        "Read the contents of a file.",
        read_file_execute,
        {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file to read"}
            },
            "required": ["filepath"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "File contents"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "write_file",
        "Write content to a file.",
        write_file_execute,
        {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file to write"},
                "content": {"type": "string", "description": "Content to write to the file"}
            },
            "required": ["filepath", "content"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Status message"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "delete_file",
        "Delete a file.",
        delete_file_execute,
        {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file to delete"}
            },
            "required": ["filepath"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Status message"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "run_process",
        "Run a system command and return its output.",
        run_process_execute,
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to execute"}
            },
            "required": ["command"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Command output (stdout + stderr)"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "kill_process",
        "Kill a process by its PID.",
        kill_process_execute,
        {
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "Process ID to kill"}
            },
            "required": ["pid"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Status message"}
            },
            "required": ["result"]
        }
    )

    # =============================================================================
    # System Monitoring & Health Tools
    # =============================================================================

    def system_health_execute() -> str:
        """Get comprehensive system health information."""
        logger.info("Getting system health information")
        try:
            import psutil
            import platform
            from datetime import datetime
            
            # CPU information
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            # Memory information
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # Disk information
            disk = psutil.disk_usage('/')
            
            # Network information
            network = psutil.net_io_counters()
            
            # Boot time
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            
            health_info = {
                "timestamp": datetime.now().isoformat(),
                "system": {
                    "platform": platform.platform(),
                    "processor": platform.processor(),
                    "boot_time": boot_time.isoformat()
                },
                "cpu": {
                    "usage_percent": cpu_percent,
                    "count": cpu_count,
                    "frequency_mhz": cpu_freq.current if cpu_freq else None
                },
                "memory": {
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "used_gb": round(memory.used / (1024**3), 2),
                    "usage_percent": memory.percent,
                    "swap_total_gb": round(swap.total / (1024**3), 2),
                    "swap_used_gb": round(swap.used / (1024**3), 2),
                    "swap_usage_percent": swap.percent
                },
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "usage_percent": round((disk.used / disk.total) * 100, 2)
                },
                "network": {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv
                }
            }
            
            return json.dumps(health_info, indent=2)
        except ImportError:
            # Fallback if psutil is not available
            return json.dumps({
                "error": "psutil module not available for detailed system monitoring",
                "timestamp": datetime.now().isoformat(),
                "basic_status": "System monitoring requires psutil installation"
            }, indent=2)
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return json.dumps({
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }, indent=2)

    def predictive_maintenance_execute() -> str:
        """Perform predictive maintenance analysis."""
        logger.info("Running predictive maintenance analysis")
        try:
            import psutil
            from datetime import datetime, timedelta
            
            # Get current system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Analyze trends and predict issues
            alerts = []
            recommendations = []
            
            # CPU usage analysis
            if cpu_percent > 80:
                alerts.append("HIGH CPU USAGE: Consider optimizing running processes")
                recommendations.append("Investigate high CPU usage processes")
            elif cpu_percent > 60:
                recommendations.append("Monitor CPU usage for trends")
            
            # Memory analysis
            if memory.percent > 85:
                alerts.append("HIGH MEMORY USAGE: Risk of system slowdown")
                recommendations.append("Consider closing unnecessary applications or adding RAM")
            elif memory.percent > 70:
                recommendations.append("Monitor memory usage trends")
            
            # Disk analysis
            disk_usage_percent = (disk.used / disk.total) * 100
            if disk_usage_percent > 90:
                alerts.append("CRITICAL DISK SPACE: Immediate action required")
                recommendations.append("Clean up disk space immediately")
            elif disk_usage_percent > 80:
                alerts.append("LOW DISK SPACE: Consider cleanup soon")
                recommendations.append("Plan disk cleanup within next 24 hours")
            
            # Temperature check (if available)
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        for entry in entries:
                            if entry.current > 80:  # Assuming Celsius
                                alerts.append(f"HIGH TEMPERATURE on {name}: {entry.current}Â°C")
                                recommendations.append(f"Check cooling system for {name}")
            except AttributeError:
                pass  # Temperature sensors not available on all systems
            
            # Generate maintenance report
            maintenance_report = {
                "timestamp": datetime.now().isoformat(),
                "analysis_period": "real_time",
                "system_status": "healthy" if len(alerts) == 0 else "needs_attention",
                "alerts": alerts,
                "recommendations": recommendations,
                "metrics": {
                    "cpu_usage_percent": cpu_percent,
                    "memory_usage_percent": memory.percent,
                    "disk_usage_percent": round(disk_usage_percent, 2),
                    "temperature_check": "available" if 'temps' in locals() else "limited"
                }
            }
            
            return json.dumps(maintenance_report, indent=2)
        except ImportError:
            return json.dumps({
                "error": "psutil module not available for predictive maintenance",
                "timestamp": datetime.now().isoformat()
            }, indent=2)
        except Exception as e:
            logger.error(f"Error in predictive maintenance: {e}")
            return json.dumps({
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }, indent=2)

    def auto_recovery_execute(action: str = "analyze") -> str:
        """Perform automatic system recovery operations."""
        logger.info(f"Performing auto recovery action: {action}")
        try:
            import psutil
            import subprocess
            from datetime import datetime
            
            recovery_log = []
            
            if action == "analyze":
                # Analyze system for issues that might benefit from recovery
                issues = []
                
                # Check for zombie processes
                try:
                    zombie_count = sum(1 for p in psutil.process_iter(['status']) if p.info['status'] == psutil.STATUS_ZOMBIE)
                    if zombie_count > 0:
                        issues.append(f"Found {zombie_count} zombie processes")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                
                # Check for high resource processes
                try:
                    high_cpu_processes = []
                    high_memory_processes = []
                    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                        try:
                            if proc.info['cpu_percent'] > 50:
                                high_cpu_processes.append(f"{proc.info['name']} (PID: {proc.info['pid']}): {proc.info['cpu_percent']}%")
                            if proc.info['memory_percent'] > 10:
                                high_memory_processes.append(f"{proc.info['name']} (PID: {proc.info['pid']}): {proc.info['memory_percent']}%")
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    
                    if high_cpu_processes:
                        issues.append(f"High CPU processes: {', '.join(high_cpu_processes[:3])}")
                    if high_memory_processes:
                        issues.append(f"High memory processes: {', '.join(high_memory_processes[:3])}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                
                recovery_log.append({"action": "analysis", "findings": issues, "timestamp": datetime.now().isoformat()})
                
                return json.dumps({
                    "recovery_action": "analyze",
                    "timestamp": datetime.now().isoformat(),
                    "issues_found": issues,
                    "recommended_actions": ["Consider restarting high resource processes", "Check for memory leaks", "Monitor system stability"] if issues else ["No immediate recovery actions needed"],
                    "log": recovery_log
                }, indent=2)
                
            elif action == "cleanup":
                # Perform safe cleanup operations
                cleanup_actions = []
                
                # Clear temporary files (Windows)
                if os.name == 'nt':
                    try:
                        temp_dir = os.environ.get('TEMP', 'C:\\Windows\\Temp')
                        # Note: In a real implementation, we'd be more careful about what we delete
                        cleanup_actions.append(f"Would clean temporary directory: {temp_dir} (simulation)")
                    except Exception:
                        cleanup_actions.append("Could not access temporary directory")
                
                # Suggest process cleanup (but don't actually kill without explicit permission)
                cleanup_actions.append("Process cleanup requires explicit user authorization for safety")
                
                recovery_log.append({"action": "cleanup", "actions_performed": cleanup_actions, "timestamp": datetime.now().isoformat()})
                
                return json.dumps({
                    "recovery_action": "cleanup",
                    "timestamp": datetime.now().isoformat(),
                    "actions_performed": cleanup_actions,
                    "note": "For safety, actual process termination requires explicit user authorization",
                    "log": recovery_log
                }, indent=2)
                
            else:
                return json.dumps({
                    "error": f"Unknown recovery action: {action}. Supported actions: 'analyze', 'cleanup'",
                    "timestamp": datetime.now().isoformat()
                }, indent=2)
                
        except ImportError:
            return json.dumps({
                "error": "psutil module not available for auto recovery",
                "timestamp": datetime.now().isoformat()
            }, indent=2)
        except Exception as e:
            logger.error(f"Error in auto recovery: {e}")
            return json.dumps({
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }, indent=2)

    def security_hardening_execute() -> str:
        """Perform security hardening checks and recommendations."""
        logger.info("Running security hardening analysis")
        try:
            import subprocess
            import os
            from datetime import datetime
            
            security_checks = []
            recommendations = []
            
            # Check for Windows Defender (if on Windows)
            if os.name == 'nt':
                try:
                    # Check if Windows Defender is running
                    result = subprocess.run(['sc', 'query', 'WinDefend'], capture_output=True, text=True, timeout=10)
                    if 'RUNNING' in result.stdout:
                        security_checks.append("Windows Defender: ACTIVE")
                    else:
                        security_checks.append("Windows Defender: INACTIVE")
                        recommendations.append("Consider enabling Windows Defender for real-time protection")
                except subprocess.TimeoutExpired:
                    security_checks.append("Windows Defender: STATUS UNKNOWN (timeout)")
                except Exception:
                    security_checks.append("Windows Defender: UNABLE TO CHECK")
            
            # Check firewall status
            try:
                if os.name == 'nt':
                    result = subprocess.run(['netsh', 'advfirewall', 'show', 'allprofiles', 'state'], 
                                          capture_output=True, text=True, timeout=10)
                    if 'State ON' in result.stdout:
                        security_checks.append("Windows Firewall: ACTIVE")
                    else:
                        security_checks.append("Windows Firewall: INACTIVE")
                        recommendations.append("Consider enabling Windows Firewall")
                else:
                    # For Linux/macOS, we could check ufw, iptables, etc.
                    security_checks.append("Firewall: CHECK REQUIRED (platform-specific)")
            except Exception:
                security_checks.append("Firewall: UNABLE TO CHECK")
            
            # Check for recent system updates
            security_checks.append("System Updates: CHECK MANUALLY (recommended regularly)")
            recommendations.append("Ensure operating system and security software are up to date")
            
            # Check for suspicious network connections (basic)
            try:
                import psutil
                network_connections = psutil.net_connections()
                # Just report count for now - detailed analysis would be more complex
                security_checks.append(f"Network Connections: {len(network_connections)} active")
            except ImportError:
                security_checks.append("Network Connections: psutil not available for detailed analysis")
            except Exception:
                security_checks.append("Network Connections: UNABLE TO CHECK")
            
            # Generate security report
            security_report = {
                "timestamp": datetime.now().isoformat(),
                "security_score": "NEEDS_ASSESSMENT",  # Would be calculated based on checks in a full implementation
                "checks_performed": security_checks,
                "recommendations": recommendations,
                "next_steps": [
                    "Review and implement high-priority recommendations",
                    "Schedule regular security scans",
                    "Consider implementing intrusion detection systems",
                    "Ensure regular backups are maintained"
                ]
            }
            
            return json.dumps(security_report, indent=2)
        except Exception as e:
            logger.error(f"Error in security hardening: {e}")
            return json.dumps({
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }, indent=2)

    # --- Developer Assistance ---
    add_tool(
        "run_code",
        "Run a snippet of code (currently Python only).",
        run_code_execute,
        {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to execute"},
                "language": {"type": "string", "description": "Programming language (default: \"python\")", "default": "python"}
            },
            "required": ["code"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Output of the code execution"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "git_status",
        "Show the git status of a repository.",
        git_status_execute,
        {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Path to the git repository (default: \".\")", "default": "."}
            },
            "required": []
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Git status output"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "git_commit",
        "Stage all changes and commit with a message.",
        git_commit_execute,
        {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Path to the git repository"},
                "message": {"type": "string", "description": "Commit message"}
            },
            "required": ["repo_path", "message"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Result of the git commit operation"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "run_terminal_command",
        "Run an arbitrary terminal command (alias for run_process).",
        run_terminal_command_execute,
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Terminal command to execute"}
            },
            "required": ["command"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Command output"}
            },
            "required": ["result"]
        }
    )

    # --- Web & Data ---
    add_tool(
        "web_search",
        "Perform a web search for a query.",
        web_search_execute,
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "description": "Number of results to return (default: 5)", "default": 5}
            },
            "required": ["query"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Search results (placeholder)"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "scrape_url",
        "Scrape a URL and return its text content.",
        scrape_url_execute,
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to scrape"}
            },
            "required": ["url"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Scraped text content (placeholder)"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "api_call",
        "Make an HTTP API call.",
        api_call_execute,
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL"},
                "method": {"type": "string", "description": "HTTP method (GET, POST, etc.)", "default": "GET"},
                "data": {"type": "string", "description": "Request body (for POST/PUT)", "default": ""}
            },
            "required": ["url"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "API response (placeholder)"}
            },
            "required": ["result"]
        }
    )

    # --- Media Generation ---
    add_tool(
        "generate_image",
        "Generate an image from a text prompt.",
        generate_image_execute,
        {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text prompt for image generation"},
                "model": {"type": "string", "description": "Model to use (default: \"default\")", "default": "default"},
                "width": {"type": "integer", "description": "Image width in pixels (default: 512)", "default": 512},
                "height": {"type": "integer", "description": "Image height in pixels (default: 512)", "default": 512}
            },
            "required": ["prompt"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "URL or path to the generated image"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "generate_video",
        "Generate a video from a text prompt.",
        generate_video_execute,
        {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text prompt for video generation"},
                "model": {"type": "string", "description": "Model to use (default: \"default\")", "default": "default"},
                "duration_sec": {"type": "integer", "description": "Video duration in seconds (default: 5)", "default": 5}
            },
            "required": ["prompt"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "URL or path to the generated video"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "lip_sync",
        "Lip-sync a video with an audio track.",
        lip_sync_execute,
        {
            "type": "object",
            "properties": {
                "video_path": {"type": "string", "description": "Path to the video file"},
                "audio_path": {"type": "string", "description": "Path to the audio file"}
            },
            "required": ["video_path", "audio_path"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "URL or path to the lip-synced video"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "cinema",
        "Generate a cinema scene from a prompt.",
        cinema_execute,
        {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text prompt for cinema generation"},
                "model": {"type": "string", "description": "Model to use (default: \"default\")", "default": "default"},
                "length_sec": {"type": "integer", "description": "Length of the cinema scene in seconds (default: 10)", "default": 10}
            },
            "required": ["prompt"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "URL or path to the generated cinema video"}
            },
            "required": ["result"]
        }
    )

    # --- Memory Operations ---
    add_tool(
        "save_fact",
        "Save a fact with a key for later recall.",
        save_fact_execute,
        {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key to associate with the fact"},
                "fact": {"type": "string", "description": "The fact to store"}
            },
            "required": ["key", "fact"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Status message"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "recall_fact",
        "Recall a fact by its key.",
        recall_fact_execute,
        {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key of the fact to recall"}
            },
            "required": ["key"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "The fact associated with the key"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "list_facts",
        "List all saved fact keys.",
        list_facts_execute,
        {
            "type": "object",
            "properties": {}
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "JSON array of fact keys"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "save_episode",
        "Save an episode (a dictionary) to episodic memory.",
        save_episode_execute,
        {
            "type": "object",
            "properties": {
                "episode": {"type": "object", "description": "Episode data to store"}
            },
            "required": ["episode"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Status message"}
            },
            "required": ["result"]
        }
    )
    add_tool(
        "recall_episode",
        "Recall an episode by its index.",
        recall_episode_execute,
        {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "Index of the episode to recall"}
            },
            "required": ["index"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Episode data as JSON"}
            },
            "required": ["result"]
        }
    )

    # --- Agent Generation ---
    add_tool(
        "spawn_agent",
        "Request spawning a specialized agent.",
        spawn_agent_execute,
        {
            "type": "object",
            "properties": {
                "role_prompt": {"type": "string", "description": "Either an agent_key from the registry OR an ad-hoc prompt"},
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of tool IDs (only used if ad-hoc spawning)"
                }
            },
            "required": ["role_prompt"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Structured request message"}
            },
            "required": ["result"]
        }
    )

    add_tool(
        "run_specialized_agent",
        "Run a specialized agent by registry key and return its response (backend/main handles).",
        run_specialized_agent_execute,
        {
            "type": "object",
            "properties": {
                "agent_key": {"type": "string", "description": "agent_key from the registry"},
                "input_text": {"type": "string", "description": "User input to pass to the specialized agent"}
            },
            "required": ["agent_key", "input_text"]
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Specialized agent response"}
            },
            "required": ["result"]
        }
    )

    add_tool(
        "list_agents",
        "List all spawned agents and their configurations.",
        list_agents_execute,
        {
            "type": "object",
            "properties": {}
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "JSON object of all spawned agents"}
            },
            "required": ["result"]
        }
    )

    # Keep the original echo tool for testing
    echo_tool = create_tool(
        id="echo",
        description="Simple echo tool for testing. Returns the input text prefixed with 'Echo: '.",
        execute=echo_execute,
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to echo back"
                }
            },
            "required": ["text"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {
                    "type": "string",
                    "description": "The echoed text"
                }
            },
            "required": ["result"]
        }
    )
    tools.append(echo_tool)

    # =============================================================================
    # System Monitoring & Health Tools (Added for Autonomous System Management)
    # =============================================================================

    add_tool(
        "system_health",
        "Get comprehensive system health information including CPU, memory, disk, and network status.",
        system_health_execute,
        {
            "type": "object",
            "properties": {}
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "System health information in JSON format"}
            },
            "required": ["result"]
        }
    )
    
    add_tool(
        "predictive_maintenance",
        "Perform predictive maintenance analysis to anticipate hardware/software issues before they occur.",
        predictive_maintenance_execute,
        {
            "type": "object",
            "properties": {}
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Predictive maintenance analysis in JSON format"}
            },
            "required": ["result"]
        }
    )
    
    add_tool(
        "auto_recovery",
        "Perform automatic system recovery operations to detect and recover from failures.",
        auto_recovery_execute,
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Recovery action to perform: 'analyze' or 'cleanup'", "default": "analyze"}
            },
            "required": []
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Auto recovery operation results in JSON format"}
            },
            "required": ["result"]
        }
    )
    
    add_tool(
        "security_hardening",
        "Perform security hardening checks and recommendations to continuously scan for vulnerabilities.",
        security_hardening_execute,
        {
            "type": "object",
            "properties": {}
        },
        {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Security hardening analysis and recommendations in JSON format"}
            },
            "required": ["result"]
