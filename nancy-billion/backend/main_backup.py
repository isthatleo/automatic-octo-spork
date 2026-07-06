import os
import asyncio
import base64
import json
import logging
import threading
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
import numpy as np

# Fury imports
from fury import Agent, HistoryManager

# Local imports
from stt import stt_backend
from llm import llm_backend
from tts import tts_backend
from tools import get_tools
from wake_word import get_wake_word_detector
from audio_decode import decode_webm_opus_b64_to_pcm, pcm_int16_to_float32
from agent_executor import run_specialized_agent

load_dotenv()  # take environment variables from .env

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="Nancy/Billion Backend")

# Global loop reference for thread-safe async calls
main_loop = None

# Base system prompt for the Sovereign AI
BASE_SYSTEM_PROMPT = """
You are Nancy/Billion, a highly intelligent, versatile, and sovereign AI operating system. You are an expert general-purpose assistant capable of reasoning through complex problems, answering a wide range of questions, and controlling the user's computer through voice commands.

CRITICAL: Do NOT assume that a user's query is a map location, address, or city name unless it is explicitly framed as one. Treat every request with a general-purpose intelligence first. If the user asks a basic question, answer it directly and intelligently.

You have access to a variety of tools for system control, coding, web search, media generation, and more. You speak in a clear, confident, and helpful tone. You can spawn specialized agents to handle complex tasks. Always aim to assist the user efficiently and safely.
"""

# Create the core agent
agent = Agent(
    model=os.getenv("LLM_MODEL_PATH", "llamafactory/Llama-3-8B-Instruct-GGUF"),
    system_prompt=BASE_SYSTEM_PROMPT,
    tools=get_tools(),
)

# History manager for persistent conversation history
history_root = os.getenv("HISTORY_ROOT", "./data/fury_history")
history_manager = HistoryManager(
    history_root=history_root,
    persist_to_disk=True,
    agent=agent,
    session_id=os.getenv("HISTORY_SESSION_ID", "nancybillion"),
)


# WebSocket manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()


# Wake word detection
def on_wake_word():
    """Callback when wake word is detected."""
    logger.info("Wake word detected! Notifying clients to start listening.")
    # Broadcast to all connected websockets using the main loop
    if main_loop is not None:
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(json.dumps({"type": "wake_word_detected"})),
            main_loop,
        )
    else:
        logger.warning("Main loop not set, cannot broadcast wake word")


wake_word_detector = get_wake_word_detector()


def start_wake_word():
    wake_word_detector.start(on_wake_word)


wake_word_thread = threading.Thread(target=start_wake_word, daemon=True)
wake_word_thread.start()
logger.info("Wake word detector thread started.")


@app.post("/agent/run")
async def run_agent_http(payload: dict):
    """Run a specialized agent by registry key."""
    agent_key = payload.get("agent_key")
    input_text = payload.get("input_text")
    max_tokens = int(payload.get("max_tokens", 512))
    temperature = float(payload.get("temperature", 0.7))

    if not agent_key or input_text is None:
        return {"error": "Missing required fields: agent_key, input_text"}

    try:
        out = await run_specialized_agent(
            agent_key=agent_key,
            input_text=str(input_text),
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return {"agent_key": agent_key, "output": out}
    except Exception as e:
        logger.exception(f"run_agent_http failed: {e}")
        return {"agent_key": agent_key, "error": str(e)}


@app.get("/test")
async def test():
    print("Handling /test request")
    return {"message": "test ok"}


@app.post("/chat")
async def chat_endpoint(payload: dict):
    text = payload.get("text")
    history = payload.get("history", [])
    if not text:
        raise HTTPException(status_code=400, detail="Missing text")
    # Build prompt from history
    prompt_lines = []
    for msg in history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        prompt_lines.append(f"{role}: {content}")
    prompt_lines.append(f"user: {text}")
    prompt_lines.append("assistant:")
    prompt = "\n".join(prompt_lines)
    # Generate response using llm_backend
    try:
        response = await llm_backend.generate(prompt, max_tokens=512, temperature=0.7)
    except Exception as e:
        logger.exception(f"LLM generation failed: {e}")
        response = "My apologies, I encountered an error."
    # Return NancyDecision-like object with action none
    return {
        "reply": response.strip(),
        "action": "none",
        "category": None,
        "topic": None,
        "symbol": None,
        "panel": None,
        "target": None,
        "media": "articles",
        "autoOpenTop": False,
    }


def _history_to_text():
    history_lines = []
    for msg in history_manager.history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        history_lines.append(f"{role}: {content}")
    return "\n".join(history_lines)


async def _generate_response_via_hierarchy(user_text: str) -> tuple[str, dict]:
    """Council + Divisions orchestration wrapper.

    Falls back to base LLM if orchestration fails.
    """
    history_text = _history_to_text()

    try:
        from .orchestration.integration import run_nancy_hierarchy

        orch = await run_nancy_hierarchy(user_text, session_context=history_text)
        return orch.get("final_response", ""), orch.get("debug", {})
    except Exception as e:
        logger.exception(f"Orchestration failed, falling back to base LLM: {e}")
        prompt = f"{BASE_SYSTEM_PROMPT}\n{history_text}\nuser: {user_text}\nassistant:"
        resp = await llm_backend.generate(prompt, max_tokens=512, temperature=0.7)
        return resp, {}


@app.websocket(os.getenv("WS_PATH", "/ws"))
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "audio_chunk":
                audio_b64 = message.get("data")
                if audio_b64:
                    try:
                        decoded = decode_webm_opus_b64_to_pcm(
                            audio_b64,
                            target_sample_rate=int(os.getenv("STT_SAMPLE_RATE", "16000")),
                        )
                        audio_np = pcm_int16_to_float32(decoded.pcm_int16)
                    except Exception:
                        audio_bytes = base64.b64decode(audio_b64)
                        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                    transcript = await stt_backend.transcribe_chunk(audio_np)
                    if transcript:
                        await manager.send_personal_message(
                            json.dumps({"type": "transcript", "data": transcript}), websocket
                        )

            elif msg_type == "final_transcript":
                text = message.get("data", "")
                logger.info(f"Received final transcript: {text}")

                await history_manager.add({"role": "user", "content": text})

                response, debug_payload = await _generate_response_via_hierarchy(text)

                await history_manager.add({"role": "assistant", "content": response})

                logger.info(f"Sending orchestrated agent response: {response}")
                await manager.send_personal_message(
                    json.dumps({"type": "agent_response", "data": response, "debug": debug_payload}), websocket
                )

                logger.info(f"Synthesizing TTS for response: {response}")
                try:
                    audio_wav = await tts_backend.synthesize(response)
                    if audio_wav:
                        audio_b64 = base64.b64encode(audio_wav).decode()
                        await manager.send_personal_message(
                            json.dumps({"type": "tts_audio", "data": audio_b64}), websocket
                        )
                    else:
                        logger.warning("TTS synthesis returned empty audio")
                except Exception as e:
                    logger.error(f"Error in TTS synthesis: {e}")

            elif msg_type == "user_text":
                text = message.get("data", "")
                logger.info(f"Received user text: {text}")

                await history_manager.add({"role": "user", "content": text})

                response, debug_payload = await _generate_response_via_hierarchy(text)

                await history_manager.add({"role": "assistant", "content": response})

                logger.info(f"Sending orchestrated agent response: {response}")
                await manager.send_personal_message(
                    json.dumps({"type": "agent_response", "data": response, "debug": debug_payload}), websocket
                )

                logger.info(f"Synthesizing TTS for response: {response}")
                try:
                    audio_wav = await tts_backend.synthesize(response)
                    if audio_wav:
                        audio_b64 = base64.b64encode(audio_wav).decode()
                        await manager.send_personal_message(
                            json.dumps({"type": "tts_audio", "data": audio_b64}), websocket
                        )
                    else:
                        logger.warning("TTS synthesis returned empty audio")
                except Exception as e:
                    logger.error(f"Error in TTS synthesis: {e}")

            elif msg_type in ("run_agent", "run_specialized_agent"):
                agent_key = message.get("agent_key")
                input_text = message.get("input_text", "")
                max_tokens = int(message.get("max_tokens", 512))
                temperature = float(message.get("temperature", 0.7))

                if not agent_key:
                    await manager.send_personal_message(
                        json.dumps({"type": "agent_error", "data": "Missing agent_key"}), websocket
                    )
                    continue

                try:
                    out = await run_specialized_agent(
                        agent_key=str(agent_key),
                        input_text=str(input_text),
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    await manager.send_personal_message(
                        json.dumps({"type": "agent_response", "data": out}), websocket
                    )
                except Exception as e:
                    logger.exception(f"Specialized agent run failed: {e}")
                    await manager.send_personal_message(
                        json.dumps({"type": "agent_error", "data": str(e)}), websocket
                    )

            elif msg_type == "ping":
                await manager.send_personal_message(json.dumps({"type": "pong"}), websocket)
            else:
                logger.warning(f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    logger.info("Main loop captured for thread-safe wake word broadcasting")


@app.get("/")
async def get():
    return HTMLResponse("<h1>Nancy/Billion Backend is running</h1>")


if __name__ == "__main__":
    import uvicorn

    @app.get("/test")
    async def test():
        return {"message": "test ok"}

    @app.post("/chat")
    async def chat_endpoint(payload: dict):
        text = payload.get("text")
        history = payload.get("history", [])
        if not text:
            raise HTTPException(status_code=400, detail="Missing text")
        # Build prompt from history
        prompt_lines = []
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            prompt_lines.append(f"{role}: {content}")
        prompt_lines.append(f"user: {text}")
        prompt_lines.append("assistant:")
        prompt = "\n".join(prompt_lines)
        # Generate response using llm_backend
        try:
            response = await llm_backend.generate(prompt, max_tokens=512, temperature=0.7)
        except Exception as e:
            logger.exception(f"LLM generation failed: {e}")
            response = "My apologies, I encountered an error."
        # Return NancyDecision-like object with action none
        return {
            "reply": response.strip(),
            "action": "none",
            "category": None,
            "topic": None,
            "symbol": None,
            "target": None,
            "panel": None,
            "target": None,
            "media": "articles",
            "autoOpenTop": False,
        }

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=False,
    )
