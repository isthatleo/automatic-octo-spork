"""Real client for an actual Langflow instance (langflowai/langflow, the
official open-source visual flow builder) -- a genuine sibling service (see
docker-compose.yml's opt-in `langflow` profile), not a pip dependency
merged into this backend's own Python environment. Hits Langflow's real
REST API (list/get/run flows) over HTTP; nothing here simulates Langflow's
behavior.

Setup: `docker compose --profile langflow up -d`, then build a flow in
Langflow's own UI at http://localhost:7860, note its flow id, and either
pass that id directly to run_langflow_flow or reference it by name via
list_flows(). LANGFLOW_BASE_URL defaults to the compose service's DNS name
(http://langflow:7860) so this works out of the box when both containers
are on the same compose network; LANGFLOW_API_KEY is optional (only needed
if the Langflow instance has API-key auth enabled).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _base_url() -> str:
    return os.getenv("LANGFLOW_BASE_URL", "http://langflow:7860").rstrip("/")


def _headers() -> Dict[str, str]:
    api_key = os.getenv("LANGFLOW_API_KEY", "")
    return {"x-api-key": api_key} if api_key else {}


async def list_flows() -> Dict[str, Any]:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_base_url()}/api/v1/flows/", headers=_headers())
            resp.raise_for_status()
            return {"success": True, "flows": resp.json()}
    except Exception as e:
        return {"success": False, "error": f"Could not reach Langflow at {_base_url()}: {e}"}


async def get_flow(flow_id: str) -> Dict[str, Any]:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_base_url()}/api/v1/flows/{flow_id}", headers=_headers())
            resp.raise_for_status()
            return {"success": True, "flow": resp.json()}
    except Exception as e:
        return {"success": False, "error": f"Could not reach Langflow at {_base_url()}: {e}"}


async def run_flow(
    flow_id_or_name: str, input_value: str, tweaks: Optional[Dict[str, Any]] = None,
    input_type: str = "chat", output_type: str = "chat",
) -> Dict[str, Any]:
    """Real POST to Langflow's /api/v1/run/{flow_id_or_name} -- actually
    executes that flow inside the real Langflow instance and returns its
    real output."""
    import httpx
    payload = {"input_value": input_value, "input_type": input_type, "output_type": output_type}
    if tweaks:
        payload["tweaks"] = tweaks
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{_base_url()}/api/v1/run/{flow_id_or_name}", json=payload, headers=_headers())
            resp.raise_for_status()
            return {"success": True, "result": resp.json()}
    except Exception as e:
        return {"success": False, "error": f"Langflow run failed ({_base_url()}): {e}"}
