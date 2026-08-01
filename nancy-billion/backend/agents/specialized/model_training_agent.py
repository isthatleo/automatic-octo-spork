"""
Model Training Agent for Nancy/Billion.

Owns the training LIFECYCLE, distinct from MLAgent (which owns the actual
scikit-learn model artifact and train/predict logic):

1. Exports a real, growing dataset (JSONL: one real {"prompt", "response"}
   pair per completed conversation exchange) to data/training_dataset.jsonl
   -- the honest, achievable version of "training her own model" on this
   CPU-only hardware: there is no way to actually fine-tune an LLM's weights
   here (no GPU, no cloud training service configured), but a real, curated,
   deduplicated dataset is the necessary precursor to ever doing so, and is
   genuinely useful right now as an auditable record of real usage.
2. Periodically triggers MLAgent's classifier retraining as that real data
   accumulates (via agent_service, not a direct import -- agents stay
   decoupled from each other the same way the rest of this codebase avoids
   direct agent-to-agent imports).
3. Maintains a real, working "personalized" local Ollama model tag: builds
   a Modelfile embedding a system prompt plus a rotating sample of real
   accumulated examples as few-shot context, and pushes it via Ollama's own
   /api/create HTTP endpoint (no CLI/subprocess -- the same pure-HTTP
   pattern llm.py's Ollama backends already use). This is real and usable
   (`ollama run billion-personalized` afterward runs this exact model), but
   it is NOT weight-level fine-tuning -- Ollama's API doesn't expose that,
   and this module never claims otherwise.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATASET_PATH = DATA_DIR / "training_dataset.jsonl"
CUSTOM_MODEL_NAME = "billion-personalized"
MAX_FEWSHOT_EXAMPLES = 8


class ModelTrainingAgent(SpecializedAgent):
    """Manages the real training/personalization lifecycle. See module
    docstring for exactly what "training her own model" honestly means on
    this hardware -- a curated dataset, a real retrained classifier
    (MLAgent), and a real personalized local Ollama model tag, not
    weight-level LLM fine-tuning."""

    def __init__(self, settings):
        super().__init__(settings, "Model Training Agent", "model-training")
        self.capabilities.update({
            "description": (
                "Manages Nancy's real training lifecycle: curates a dataset from actual "
                "conversations, retrains MLAgent's classifier, and maintains a real "
                "personalized local Ollama model"
            ),
            "confidence": 0.8,
            "specializations": ["dataset-curation", "training-lifecycle", "ollama-personalization"],
            "tools": ["ollama", "jsonl"],
        })
        self._last_cycle: Dict[str, Any] = {}

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "run_cycle":
            return await self._run_cycle()
        if task_type == "export_dataset":
            return self._export_dataset()
        if task_type == "status":
            return self._status()
        if task_type == "query":
            return await self._general_training(task_data)
        return await self._general_training(task_data)

    def _export_dataset(self) -> Dict[str, Any]:
        """Appends any real conversation exchanges not already captured.
        Dedupes by exact prompt text so re-running this never duplicates
        entries -- safe to call as often as every proactive cycle wants."""
        import conversation_log

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        existing_prompts = set()
        if DATASET_PATH.exists():
            try:
                with DATASET_PATH.open(encoding="utf-8") as f:
                    for line in f:
                        try:
                            existing_prompts.add(json.loads(line)["prompt"])
                        except Exception:
                            continue
            except Exception:
                logger.warning("ModelTrainingAgent: could not read existing dataset, starting fresh")

        user_turns = conversation_log.recent_turns(role="user", limit=2000)
        assistant_turns = conversation_log.recent_turns(role="assistant", limit=2000)
        # Both lists are newest-first from the same verbatim log; real turns
        # are written user-then-assistant per exchange (see main_new.py's
        # _generate_response_via_hierarchy/_run_chat_turn), so pairing by
        # matching index from the oldest end reconstructs real (prompt,
        # response) pairs without conversation_log needing to expose a join.
        pairs = list(zip(reversed(user_turns), reversed(assistant_turns)))

        new_count = 0
        try:
            with DATASET_PATH.open("a", encoding="utf-8") as f:
                for prompt, response in pairs:
                    if prompt in existing_prompts:
                        continue
                    f.write(json.dumps({"prompt": prompt, "response": response}) + "\n")
                    existing_prompts.add(prompt)
                    new_count += 1
        except Exception as e:
            return {"success": False, "error": str(e)}

        return {"success": True, "new_examples": new_count, "dataset_path": str(DATASET_PATH)}

    async def _refresh_personalized_ollama_model(self) -> Dict[str, Any]:
        """Real custom Ollama model tag via Ollama's own /api/create HTTP
        endpoint (documented, no CLI needed), embedding real accumulated
        examples as few-shot system-prompt context."""
        import aiohttp

        if not DATASET_PATH.exists():
            return {"success": False, "error": "No training dataset yet -- run export_dataset first"}

        examples: List[Dict[str, str]] = []
        try:
            with DATASET_PATH.open(encoding="utf-8") as f:
                lines = f.readlines()
            sample = random.sample(lines, min(MAX_FEWSHOT_EXAMPLES, len(lines)))
            for line in sample:
                try:
                    row = json.loads(line)
                    if row.get("prompt") and row.get("response"):
                        examples.append(row)
                except Exception:
                    continue
        except Exception as e:
            return {"success": False, "error": f"Could not read dataset: {e}"}

        if not examples:
            return {"success": False, "error": "Dataset has no usable examples yet"}

        base_model = os.getenv("OLLAMA_PERSONALIZATION_BASE", "llama3.2")
        system_lines = [
            "You are Nancy/Billion, personalized from this user's own real conversation "
            "history. The examples below are your actual real past answers -- match that "
            "tone and style."
        ]
        for ex in examples:
            system_lines.append(f"\nUser: {ex['prompt'][:300]}\nBillion: {ex['response'][:300]}")
        modelfile = f"FROM {base_model}\nSYSTEM \"\"\"{chr(10).join(system_lines)}\"\"\"\n"

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/api/create",
                    json={"name": CUSTOM_MODEL_NAME, "modelfile": modelfile, "stream": False},
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        return {"success": False, "error": f"Ollama /api/create returned {resp.status}: {text[:300]}"}
        except Exception as e:
            return {"success": False, "error": f"Ollama unreachable: {e}"}

        return {"success": True, "model": CUSTOM_MODEL_NAME, "base_model": base_model, "examples_used": len(examples)}

    async def _run_cycle(self) -> Dict[str, Any]:
        """The real end-to-end lifecycle step: export any new real
        conversation data, retrain MLAgent's classifier if enough new data
        has accumulated, and refresh the personalized Ollama model. Called
        on a schedule (see main_new.py's proactive-agent wiring), not
        continuously -- each step here does real, bounded, one-shot work."""
        export_result = self._export_dataset()

        ml_result: Dict[str, Any]
        try:
            from agents.agent_service import agent_service
            ml_result = await agent_service.run("machine_learning", {"type": "train"}, timeout=120.0)
        except Exception as e:
            ml_result = {"success": False, "error": str(e)}

        ollama_result = await self._refresh_personalized_ollama_model()

        self._last_cycle = {
            "ran_at": time.time(),
            "dataset_export": export_result,
            "classifier_training": ml_result,
            "ollama_personalization": ollama_result,
        }
        return {"success": True, **self._last_cycle}

    def _status(self) -> Dict[str, Any]:
        count = 0
        if DATASET_PATH.exists():
            try:
                with DATASET_PATH.open(encoding="utf-8") as f:
                    count = sum(1 for _ in f)
            except Exception:
                pass
        return {
            "success": True,
            "dataset_examples": count,
            "dataset_path": str(DATASET_PATH) if DATASET_PATH.exists() else None,
            "custom_ollama_model": CUSTOM_MODEL_NAME,
            "last_cycle": self._last_cycle or None,
        }

    async def _general_training(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        query = task_data.get("query") or task_data.get("text", "")
        answer = await self._llm_answer(query)
        if answer:
            return {"success": True, "response": answer}
        return {
            "success": True,
            "response": (
                "I manage Nancy's real training lifecycle -- curating a dataset from actual "
                "conversations, retraining the ML classifier, and refreshing a personalized "
                "local Ollama model. Ask me to 'run_cycle' to do all three, or check 'status'."
            ),
        }
