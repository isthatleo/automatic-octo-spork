import os
import asyncio
import base64
import json
import logging
import threading
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

# Fury imports
try:
    from fury import Agent, HistoryManager
    _FURY_AVAILABLE = True
except ImportError:
    _FURY_AVAILABLE = False
    Agent = None  # type: ignore
    HistoryManager = None  # type: ignore

# Local imports
from stt import stt_backend
from llm import llm_backend, select_llm_for_task
from tts import tts_backend
from tools import get_tools
from wake_word import get_wake_word_detector
from audio_decode import decode_webm_opus_b64_to_pcm, pcm_int16_to_float32
from agents.agent_service import agent_service
from context_manager import NancyContextualBrain, IntentType
from memory import MemoryManager, MemoryType
from startup import StartupCoordinator, NancyGreeting
from intelligent_greeting import IntelligentStartupCoordinator, PersonalContext
from trading import (
    ForexDataAggregator,
    TechnicalAnalysisEngine,
    StrategyAdvisor,
    RiskMonitor,
    TradingManager,
)

try:
    from agent_executor import run_specialized_agent as fury_run_agent
    _AGENT_EXEC_AVAILABLE = True
except Exception:
    _AGENT_EXEC_AVAILABLE = False
    async def fury_run_agent(*a, **kw):  # type: ignore
        raise RuntimeError("Fury agent executor not available")

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="Nancy/Billion Backend", version="2.0.0")

# CORS — allow the Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global loop reference for thread-safe async calls
main_loop = None

# Nancy's Startup Coordinator
startup_coordinator = StartupCoordinator()

# Nancy's Contextual Brain (handles routing, memory, context)
nancy_brain = NancyContextualBrain(user_id="user")

# Nancy's Memory System (long-term intelligence)
memory_manager = MemoryManager(user_id="user")
memory_manager.set_context_manager(nancy_brain.context)

# Nancy's Trading Intelligence System
forex_aggregator = ForexDataAggregator()
analysis_engine = TechnicalAnalysisEngine()
strategy_advisor = StrategyAdvisor()
risk_monitor = RiskMonitor(account_balance=100000)
trading_manager = TradingManager(user_id="user")

# Log Nancy's startup
logger.info("=" * 70)
logger.info("🎉 NANCY/BILLION AI OPERATING SYSTEM STARTING")
logger.info("=" * 70)
logger.info(f"Version: 2.0.0 - Production Ready")
logger.info(f"Persona: {startup_coordinator.persona.upper()}")
logger.info(f"Timestamp: {datetime.now().isoformat()}")
logger.info("=" * 70)

# ---------------------------------------------------------------------------
# Base system prompt
# ---------------------------------------------------------------------------
BASE_SYSTEM_PROMPT = """
You are Nancy/Billion, a highly intelligent, versatile, and sovereign AI operating system. You are an expert general-purpose assistant capable of reasoning through complex problems, answering a wide range of questions, and controlling the user's computer through voice commands.

CRITICAL: Do NOT assume that a user's query is a map location, address, or city name unless it is explicitly framed as one. Treat every request with a general-purpose intelligence first. If the user asks a basic question, answer it directly and intelligently.

You have access to a variety of tools for system control, coding, web search, media generation, and more. You speak in a clear, confident, and helpful tone. You can spawn specialized agents to handle complex tasks. Always aim to assist the user efficiently and safely.
"""

# ---------------------------------------------------------------------------
# Fury agent (optional)
# ---------------------------------------------------------------------------
if _FURY_AVAILABLE:
    try:
        agent = Agent(
            model=os.getenv("LLM_MODEL_PATH", "llamafactory/Llama-3-8B-Instruct-GGUF"),
            system_prompt=BASE_SYSTEM_PROMPT,
            tools=get_tools(),
        )
        history_root = os.getenv("HISTORY_ROOT", "./data/fury_history")
        history_manager = HistoryManager(
            history_root=history_root,
            persist_to_disk=True,
            agent=agent,
            session_id=os.getenv("HISTORY_SESSION_ID", "nancybillion"),
        )
    except Exception as e:
        logger.warning("Fury agent init failed (non-fatal): %s", e)
        agent = None
        history_manager = None
else:
    agent = None
    history_manager = None


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connected. Total: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket disconnected. Total: %d", len(self.active_connections))

    async def send(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Wake word
# ---------------------------------------------------------------------------
def on_wake_word():
    logger.info("Wake word detected!")
    if main_loop is not None:
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(json.dumps({"type": "wake_word_detected"})),
            main_loop,
        )

try:
    wake_word_detector = get_wake_word_detector()
    threading.Thread(target=lambda: wake_word_detector.start(on_wake_word), daemon=True).start()
    logger.info("Wake word detector started.")
except Exception as e:
    logger.warning("Wake word detector unavailable: %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _history_to_text() -> str:
    if history_manager is None:
        return ""
    history_lines = []
    for msg in history_manager.history:
        history_lines.append(f"{msg.get('role','?')}: {msg.get('content','')}")
    return "\n".join(history_lines)


async def _generate_response_via_hierarchy(user_text: str) -> tuple[str, dict]:
    history_text = _history_to_text()
    try:
        from orchestration.integration import run_nancy_hierarchy
        orch = await run_nancy_hierarchy(user_text, session_context=history_text)
        return orch.get("final_response", ""), orch.get("debug", {})
    except Exception as e:
        logger.warning("Orchestration failed, using LLM fallback: %s", e)
        prompt = f"{BASE_SYSTEM_PROMPT}\n{history_text}\nuser: {user_text}\nassistant:"
        try:
            resp = await llm_backend.generate(prompt, max_tokens=512, temperature=0.7)
        except Exception as llm_e:
            resp = f"I'm having trouble processing that right now. ({llm_e})"
        return resp, {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class AgentRunRequest(BaseModel):
    agent_key: str
    task_type: str
    payload: Dict[str, Any] = {}
    timeout: float = 60.0

class AgentAutoRequest(BaseModel):
    text: str
    timeout: float = 60.0

class ChatRequest(BaseModel):
    text: str
    history: list = []
    task_hint: str | None = None  # e.g., "coding", "fast_response", "general", "multimodal"


# ---------------------------------------------------------------------------
# REST routes — Core
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return HTMLResponse("<h1>Nancy/Billion Backend v2 — online</h1>")

@app.get("/test")
async def test():
    return {"message": "test ok", "agents_ready": agent_service.is_ready()}


# ---------------------------------------------------------------------------
# Startup & Greeting endpoints
# ---------------------------------------------------------------------------

@app.get("/startup")
async def startup_sequence():
    """Get Nancy's startup sequence"""
    sequence = startup_coordinator.start_up()
    return {
        "success": True,
        **sequence
    }


@app.get("/greeting")
async def get_greeting():
    """Get current greeting from Nancy"""
    greeting = startup_coordinator.greeting
    return {
        "success": True,
        "persona": startup_coordinator.persona,
        "boot_message": greeting.get_boot_message(),
        "ready_message": greeting.get_ready_message(),
        "context_aware_greeting": greeting.get_context_aware_greeting()
    }


@app.post("/persona/{persona_name}")
async def set_persona(persona_name: str):
    """Change Nancy's persona"""
    valid_personas = ["nancy", "billion", "jarvis"]

    if persona_name.lower() not in valid_personas:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid persona. Choose from: {', '.join(valid_personas)}"
        )

    startup_coordinator.set_persona(persona_name)

    greeting = startup_coordinator.greeting
    logger.info(f"Persona changed to: {persona_name}")

    return {
        "success": True,
        "persona": startup_coordinator.persona,
        "greeting": greeting.get_ready_message()
    }


@app.post("/greeting/personalized")
async def get_personalized_greeting(payload: Dict):
    """
    Get Nancy's intelligent personalized greeting.

    Nancy analyzes your context and gives you a smart greeting with:
    - Your meetings today
    - Build/deployment status
    - Market alerts you're watching
    - Project updates
    - Open trades
    - Tasks due

    Example response:
    "Morning. You have two meetings today, your overnight Docker build
     finished successfully, EUR/USD is approaching the level you've been
     watching, and Roxan's latest deployment completed without errors."
    """

    # Extract context from payload
    context = PersonalContext(
        meetings_today=payload.get("meetings_today", []),
        build_status=payload.get("build_status"),
        market_alerts=payload.get("market_alerts", []),
        project_updates=payload.get("project_updates", []),
        active_trades=payload.get("active_trades", []),
        tasks_due=payload.get("tasks_due", [])
    )

    # Create coordinator and generate greeting
    coordinator = IntelligentStartupCoordinator(persona=startup_coordinator.persona)
    startup_data = await coordinator.startup_with_context(context)

    logger.info(f"Generated personalized greeting for {len(context.meetings_today)} "
               f"meetings, {len(context.market_alerts)} market alerts, "
               f"{len(context.project_updates)} project updates")

    return {
        "success": True,
        **startup_data
    }


@app.post("/context/analyze")
async def analyze_context(payload: ChatRequest):
    """Analyze user input and return context/intent information (DEBUG endpoint)."""
    brain_decision = nancy_brain.process_input(payload.text)
    return {
        "input": payload.text,
        "intent": brain_decision['intent'],
        "confidence": brain_decision['confidence'],
        "should_show_map": brain_decision['should_use_map'],
        "routing_hints": brain_decision['routing_hints'],
        "active_topics": nancy_brain.context.active_topics,
    }


# ---------------------------------------------------------------------------
# Memory API endpoints
# ---------------------------------------------------------------------------

@app.get("/memory/summary")
async def memory_summary():
    """Get summary of Nancy's memory state"""
    summary = memory_manager.get_memory_summary()
    return {
        "success": True,
        "memory": summary
    }


@app.post("/memory/query")
async def memory_query(payload: ChatRequest):
    """Search Nancy's memories for relevant information"""
    if not payload.text:
        raise HTTPException(status_code=400, detail="Query text required")

    memories = memory_manager.get_relevant_memories(payload.text, top_k=10)

    return {
        "success": True,
        "query": payload.text,
        "memories": memories,
        "count": len(memories)
    }


@app.get("/memory/projects")
async def get_projects():
    """Get all projects Nancy remembers"""
    projects = memory_manager.get_project_context()
    return {
        "success": True,
        "projects": projects,
        "count": len(projects)
    }


@app.get("/memory/trades")
async def get_trades():
    """Get trade history from Nancy's memory"""
    trades = memory_manager.get_trade_history(limit=50)
    return {
        "success": True,
        "trades": trades,
        "count": len(trades)
    }


# ---------------------------------------------------------------------------
# Trading Intelligence API endpoints
# ---------------------------------------------------------------------------

@app.post("/trading/analyze")
async def analyze_pair(payload: ChatRequest):
    """Analyze a forex pair with technical analysis"""
    if not payload.text:
        raise HTTPException(status_code=400, detail="Pair name required")

    # Extract pair from text (e.g., "EUR/USD" or "What about EUR/USD")
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]
    pair = None
    for p in pairs:
        if p.upper() in payload.text.upper():
            pair = p
            break

    if not pair:
        raise HTTPException(status_code=400, detail="Forex pair not found in request")

    # Get market data
    snapshot = await forex_aggregator.get_price(pair)
    historical = await forex_aggregator.get_historical(pair)

    if not snapshot:
        raise HTTPException(status_code=400, detail=f"Could not get data for {pair}")

    # Perform analysis
    analysis = analysis_engine.analyze(pair, snapshot, historical)

    # Get recommendation
    rec = strategy_advisor.get_recommendation(analysis)

    return {
        "success": True,
        "pair": pair,
        "price": snapshot.price,
        "analysis": analysis.to_dict(),
        "recommendation": rec
    }


@app.get("/trading/recommendation/{pair}")
async def get_trading_recommendation(pair: str):
    """Get trading recommendation for a pair"""
    snapshot = await forex_aggregator.get_price(pair)
    if not snapshot:
        raise HTTPException(status_code=400, detail=f"Could not get data for {pair}")

    historical = await forex_aggregator.get_historical(pair)
    analysis = analysis_engine.analyze(pair, snapshot, historical)
    recommendation = strategy_advisor.get_recommendation(analysis)

    return {
        "success": True,
        "pair": pair,
        "recommendation": recommendation
    }


@app.get("/trading/risk-assessment")
async def assess_trading_risk():
    """Assess overall trading risk"""
    trades = trading_manager.trades
    risk_assessment = risk_monitor.assess_risk([
        {
            "risk_amount": t.profit_loss or 0,
            "result": "win" if (t.profit_loss or 0) > 0 else "loss"
        }
        for t in trades if t.status == "closed"
    ])

    return {
        "success": True,
        "risk_assessment": risk_assessment
    }


@app.post("/trading/record-trade")
async def record_trade(payload: Dict):
    """Record a new trade"""
    pair = payload.get("pair")
    direction = payload.get("direction")  # BUY or SELL
    entry_price = payload.get("entry_price")
    quantity = payload.get("quantity", 1.0)
    notes = payload.get("notes", "")

    if not all([pair, direction, entry_price]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    trade = trading_manager.record_trade(pair, direction, entry_price, quantity, notes)

    # Store in memory
    memory_manager.graph.add_memory(
        f"Opened {direction} trade on {pair} @ {entry_price}",
        MemoryType.TRADE,
        {"pair": pair, "direction": direction, "entry": entry_price},
        importance=0.8
    )

    return {
        "success": True,
        "trade": {
            "pair": trade.pair,
            "direction": trade.direction,
            "entry_price": trade.entry_price,
            "quantity": trade.quantity,
            "status": trade.status
        }
    }


@app.get("/trading/performance")
async def get_trading_performance():
    """Get trading performance metrics"""
    metrics = trading_manager.get_performance_metrics()

    return {
        "success": True,
        "metrics": metrics,
        "recommendation": trading_manager._get_trading_recommendation(metrics)
    }


@app.get("/trading/history")
async def get_trading_history(pair: str = None, limit: int = 50):
    """Get trading history"""
    trades = trading_manager.get_trade_history(pair=pair, limit=limit)

    return {
        "success": True,
        "trades": [
            {
                "pair": t.pair,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "profit_loss": t.profit_loss,
                "status": t.status,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time
            }
            for t in trades
        ],
        "count": len(trades)
    }


@app.get("/trading/report")
async def get_trading_report():
    """Get comprehensive trading report"""
    report = trading_manager.generate_trading_report()

    return {
        "success": True,
        "report": report
    }


@app.post("/chat")
async def chat_endpoint(payload: ChatRequest):
    """Primary chat endpoint with intelligent context-aware routing.

    Uses NancyContextualBrain to:
    - Understand user intent (NOT confuse weather with map!)
    - Select appropriate LLM based on task
    - Route to correct handler
    - Maintain conversation context

    Supports task_hint to route to specialized LLMs:
    - "coding" → Claude (Anthropic)
    - "fast_response" → Groq (speed optimized)
    - "multimodal" → Gemini
    - None / "general" → Uses full fallback chain (Ollama → Anthropic → Groq → OpenAI → etc.)
    """
    text = payload.text
    if not text:
        raise HTTPException(status_code=400, detail="Missing text")

    # Process input through Nancy's brain for intelligent routing
    brain_decision = nancy_brain.process_input(text)

    logger.info(f"User intent: {brain_decision['intent']} (confidence: {brain_decision['confidence']:.2f})")
    logger.info(f"Routing hints: {brain_decision['routing_hints']}")

    # Determine if we should show map (NOT for weather, research, etc!)
    should_show_map = brain_decision['should_use_map'] and brain_decision['confidence'] > 0.7

    prompt_lines = []
    for msg in payload.history:
        if isinstance(msg, dict):
            prompt_lines.append(f"{msg.get('role','user')}: {msg.get('content','')}")
    prompt_lines.append(f"user: {text}")
    prompt_lines.append("assistant:")
    prompt = "\n".join(prompt_lines)

    try:
        # Extract memories from conversation
        memory_manager.extract_memories_from_conversation()

        # Select LLM based on task hint or detected intent
        task_hint = payload.task_hint
        if not task_hint and brain_decision['intent'] == IntentType.TRADING.value:
            task_hint = "trading"
            logger.debug("Auto-detected trading task")
        elif not task_hint and brain_decision['intent'] == IntentType.CODING.value:
            task_hint = "coding"
            logger.debug("Auto-detected coding task")

        # Augment prompt with relevant memories
        augmented_prompt = memory_manager.augment_prompt_with_memory(prompt)

        selected_llm = select_llm_for_task(task_hint)
        logger.info(f"Chat endpoint using LLM: {selected_llm.__class__.__name__} (intent: {brain_decision['intent']}, task_hint: {task_hint})")

        response = await selected_llm.generate(augmented_prompt, max_tokens=512, temperature=0.7)

        # Record response in context
        nancy_brain.add_response(response)

        # Learn from this exchange
        memory_manager.learn_from_response(text, response)

    except Exception as e:
        logger.exception("LLM generation failed: %s", e)
        response = "My apologies, I encountered an error while processing your request."

    return {
        "reply": response.strip(),
        "action": "locate" if should_show_map else "none",  # Only show map for actual map requests!
        "category": None,
        "topic": None,
        "symbol": None,
        "panel": "map" if should_show_map else None,  # Don't show map for weather!
        "target": None,
        "media": "articles",
        "autoOpenTop": False,
        "intent": brain_decision['intent'],
        "confidence": brain_decision['confidence'],
    }


# ---------------------------------------------------------------------------
# REST routes — Specialized Agents
# ---------------------------------------------------------------------------

@app.get("/agents/list")
async def list_agents():
    """Return all 29 specialized agents with live status."""
    agents = agent_service.list_agents()
    stats  = agent_service.get_service_stats()
    return {
        "success": True,
        "agents":  agents,
        "stats":   stats,
        "total":   len(agents),
    }


@app.get("/agents/stats")
async def agent_stats():
    return {"success": True, **agent_service.get_service_stats()}


@app.get("/agents/{agent_key}/status")
async def agent_status(agent_key: str):
    """Full status for a single agent."""
    status = agent_service.get_agent_status(agent_key)
    return {"success": True, "agent_key": agent_key, "status": status}


@app.post("/agents/run")
async def run_agent(req: AgentRunRequest):
    """
    Run a specific agent with a typed task payload.

    Example:
        POST /agents/run
        {
          "agent_key": "quantum_reasoning",
          "task_type": "qrng",
          "payload": {"n_bits": 256}
        }
    """
    if not agent_service.is_ready():
        raise HTTPException(status_code=503, detail="AgentService not yet initialised")

    task_data = {"type": req.task_type, **req.payload}
    result = await agent_service.run(req.agent_key, task_data, timeout=req.timeout)
    return result


@app.post("/agents/auto")
async def auto_route_agent(req: AgentAutoRequest):
    """
    Auto-route a natural-language query to the best specialist agent.

    Example:
        POST /agents/auto
        {"text": "generate a 256-bit quantum random number"}
    """
    if not agent_service.is_ready():
        raise HTTPException(status_code=503, detail="AgentService not yet initialised")

    result = await agent_service.auto_run(req.text, timeout=req.timeout)
    return result


# Legacy HTTP agent runner (Fury-based)
@app.post("/agent/run")
async def run_fury_agent(payload: dict):
    """Run a Fury registry agent by key (legacy endpoint)."""
    agent_key  = payload.get("agent_key")
    input_text = payload.get("input_text")
    if not agent_key or input_text is None:
        return {"error": "Missing required fields: agent_key, input_text"}
    try:
        out = await fury_run_agent(
            agent_key=agent_key,
            input_text=str(input_text),
            max_tokens=int(payload.get("max_tokens", 512)),
            temperature=float(payload.get("temperature", 0.7)),
        )
        return {"agent_key": agent_key, "output": out}
    except Exception as e:
        return {"agent_key": agent_key, "error": str(e)}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket(os.getenv("WS_PATH", "/ws"))
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data    = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")

            # ---- Audio chunk (STT) ----
            if msg_type == "audio_chunk":
                audio_b64 = message.get("data")
                if audio_b64:
                    try:
                        if np is not None:
                            decoded  = decode_webm_opus_b64_to_pcm(
                                audio_b64,
                                target_sample_rate=int(os.getenv("STT_SAMPLE_RATE", "16000")),
                            )
                            audio_np = pcm_int16_to_float32(decoded.pcm_int16)
                        else:
                            audio_bytes = base64.b64decode(audio_b64)
                            import array as _arr
                            raw = _arr.array("h", audio_bytes)
                            audio_np = [s / 32768.0 for s in raw]
                    except Exception:
                        audio_bytes = base64.b64decode(audio_b64)
                        audio_np = [s / 32768.0 for s in audio_bytes]

                    transcript = await stt_backend.transcribe_chunk(audio_np)
                    if transcript:
                        await manager.send(
                            json.dumps({"type": "transcript", "data": transcript}),
                            websocket,
                        )

            # ---- Final transcript / user text ----
            elif msg_type in ("final_transcript", "user_text"):
                text = message.get("data", "")
                logger.info("Received %s: %s", msg_type, text[:80])

                if history_manager:
                    await history_manager.add({"role": "user", "content": text})

                response, debug_payload = await _generate_response_via_hierarchy(text)

                if history_manager:
                    await history_manager.add({"role": "assistant", "content": response})

                await manager.send(
                    json.dumps({
                        "type":  "agent_response",
                        "data":  response,
                        "debug": debug_payload,
                    }),
                    websocket,
                )

                # TTS
                try:
                    audio_wav = await tts_backend.synthesize(response)
                    if audio_wav:
                        await manager.send(
                            json.dumps({
                                "type": "tts_audio",
                                "data": base64.b64encode(audio_wav).decode(),
                            }),
                            websocket,
                        )
                except Exception as e:
                    logger.error("TTS error: %s", e)

            # ---- Specialized Python agent task (new) ----
            elif msg_type == "run_specialized_task":
                """
                Run one of the 29 Python specialized agents directly.
                Message format:
                {
                    "type":       "run_specialized_task",
                    "agent_key":  "quantum_reasoning",
                    "task_type":  "qrng",
                    "payload":    {"n_bits": 128},
                    "request_id": "abc123"   (optional, echoed back)
                }
                """
                agent_key  = message.get("agent_key", "")
                task_type  = message.get("task_type", "query")
                payload    = message.get("payload", {})
                request_id = message.get("request_id")

                if not agent_key:
                    await manager.send(
                        json.dumps({"type": "agent_error", "error": "Missing agent_key", "request_id": request_id}),
                        websocket,
                    )
                    continue

                task_data = {"type": task_type, **payload}

                try:
                    result = await agent_service.run(agent_key, task_data, timeout=60.0)
                    await manager.send(
                        json.dumps({
                            "type":       "agent_result",
                            "agent_key":  agent_key,
                            "request_id": request_id,
                            "result":     result,
                        }),
                        websocket,
                    )
                except Exception as e:
                    logger.exception("WS specialized task error: %s", e)
                    await manager.send(
                        json.dumps({
                            "type":       "agent_error",
                            "agent_key":  agent_key,
                            "request_id": request_id,
                            "error":      str(e),
                        }),
                        websocket,
                    )

            # ---- Auto-route NL to best agent ----
            elif msg_type == "auto_route_task":
                """
                {
                    "type": "auto_route_task",
                    "text": "generate a quantum random number",
                    "request_id": "xyz"
                }
                """
                text       = message.get("text", "")
                request_id = message.get("request_id")
                try:
                    result = await agent_service.auto_run(text, timeout=60.0)
                    await manager.send(
                        json.dumps({
                            "type":       "agent_result",
                            "request_id": request_id,
                            "result":     result,
                        }),
                        websocket,
                    )
                except Exception as e:
                    await manager.send(
                        json.dumps({"type": "agent_error", "error": str(e), "request_id": request_id}),
                        websocket,
                    )

            # ---- Legacy Fury agent runner ----
            elif msg_type in ("run_agent", "run_specialized_agent"):
                agent_key  = message.get("agent_key")
                input_text = message.get("input_text", "")
                if not agent_key:
                    await manager.send(
                        json.dumps({"type": "agent_error", "data": "Missing agent_key"}),
                        websocket,
                    )
                    continue
                try:
                    out = await fury_run_agent(
                        agent_key=str(agent_key),
                        input_text=str(input_text),
                        max_tokens=int(message.get("max_tokens", 512)),
                        temperature=float(message.get("temperature", 0.7)),
                    )
                    await manager.send(
                        json.dumps({"type": "agent_response", "data": out}),
                        websocket,
                    )
                except Exception as e:
                    await manager.send(
                        json.dumps({"type": "agent_error", "data": str(e)}),
                        websocket,
                    )

            elif msg_type == "ping":
                await manager.send(json.dumps({"type": "pong"}), websocket)

            else:
                logger.warning("Unknown WS message type: %s", msg_type)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.exception("WebSocket error: %s", e)
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    logger.info("Nancy/Billion backend starting up…")
    # Initialise all 29 specialized agents in background so startup is fast
    asyncio.create_task(_init_agents())


async def _init_agents():
    try:
        await agent_service.initialize(settings=None)
        stats = agent_service.get_service_stats()
        logger.info(
            "AgentService ready: %d online, %d offline.",
            stats["agents_online"], stats["agents_offline"],
        )
    except Exception as exc:
        logger.exception("AgentService init failed: %s", exc)


@app.on_event("shutdown")
async def shutdown_event():
    await agent_service.shutdown()
    logger.info("Nancy/Billion backend shut down.")


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=False,
    )
