"""SnoopLog pipeline — FastAPI application."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from pipeline.integrations.discord import configure_discord_integration
from shared.events import bus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("snooplog.pipeline")

app = FastAPI(title="SnoopLog Pipeline", version="0.1.0")

# CORS — allow dashboard on Vercel and local dev
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,https://*.vercel.app",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "snooplog-pipeline"}


# ── WebSocket ───────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    bus.register_ws(ws)
    logger.info("WebSocket client connected")
    try:
        while True:
            # Keep connection alive; client can send pings
            await ws.receive_text()
    except WebSocketDisconnect:
        bus.unregister_ws(ws)
        logger.info("WebSocket client disconnected")


# ── Route mounting ──────────────────────────────────────────────────────
# Person 1 adds ingestion routes here
# Person 2 wires cascade subscribers at startup

from pipeline.ingestion.routes import router as ingestion_router  # noqa: E402

app.include_router(ingestion_router, prefix="/api")


@app.on_event("startup")
async def startup():
    logger.info("SnoopLog pipeline starting up")
    configure_discord_integration()
    # Person 2: wire tier router subscription here
    # e.g. bus.subscribe("log:scored", tier_router.handle)
