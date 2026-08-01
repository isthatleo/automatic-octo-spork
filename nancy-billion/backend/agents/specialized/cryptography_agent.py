"""
Cryptography Agent for Nancy/Billion.
Real cryptographic primitives via the standard library (hashlib) and the
already-installed `cryptography` package (Fernet symmetric encryption) --
never a fabricated hash or a made-up "encrypted" string.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent

_HASH_ALGOS = {"md5": hashlib.md5, "sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512}


class CryptographyAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Cryptography Agent", "cryptography")
        self.capabilities.update({
            "description": "Real hashing, symmetric encryption (Fernet), and base64 encoding -- never a fabricated result",
            "confidence": 0.85,
            "specializations": ["hashing", "symmetric-encryption", "encoding"],
            "tools": ["hashlib", "cryptography.fernet"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "hash":
            return self._hash(task_data.get("text", ""), task_data.get("algorithm", "sha256"))
        if task_type == "generate_key":
            return self._generate_key()
        if task_type == "encrypt":
            return self._encrypt(task_data.get("text", ""), task_data.get("key", ""))
        if task_type == "decrypt":
            return self._decrypt(task_data.get("token", ""), task_data.get("key", ""))
        if task_type == "encode_base64":
            return {"success": True, "result": base64.b64encode(task_data.get("text", "").encode()).decode()}
        if task_type == "decode_base64":
            try:
                return {"success": True, "result": base64.b64decode(task_data.get("text", "")).decode(errors="replace")}
            except Exception as e:
                return {"success": False, "error": str(e)}
        if task_type == "status":
            return {"success": True, "status": "ready", "algorithms": list(_HASH_ALGOS)}
        return await self._general(task_data)

    def _hash(self, text: str, algorithm: str) -> Dict[str, Any]:
        fn = _HASH_ALGOS.get(algorithm.lower())
        if fn is None:
            return {"success": False, "error": f"Unsupported algorithm '{algorithm}'. Use one of {list(_HASH_ALGOS)}."}
        return {"success": True, "algorithm": algorithm, "hexdigest": fn(text.encode()).hexdigest()}

    def _generate_key(self) -> Dict[str, Any]:
        try:
            from cryptography.fernet import Fernet
            return {"success": True, "key": Fernet.generate_key().decode()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _encrypt(self, text: str, key: str) -> Dict[str, Any]:
        try:
            from cryptography.fernet import Fernet
            f = Fernet(key.encode())
            return {"success": True, "token": f.encrypt(text.encode()).decode()}
        except Exception as e:
            return {"success": False, "error": f"Encryption failed (is the key a valid Fernet key?): {e}"}

    def _decrypt(self, token: str, key: str) -> Dict[str, Any]:
        try:
            from cryptography.fernet import Fernet, InvalidToken
            f = Fernet(key.encode())
            return {"success": True, "text": f.decrypt(token.encode()).decode()}
        except Exception as e:
            return {"success": False, "error": f"Decryption failed (wrong key, or not a real token from this agent): {e}"}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I do real hashing (md5/sha1/sha256/sha512), Fernet symmetric encryption, and base64 encode/decode."
        )}
