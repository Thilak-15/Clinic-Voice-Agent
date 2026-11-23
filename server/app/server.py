"""HTTP server: WebRTC signalling for calls + a small REST/SSE API for the dashboard.

Routes
  POST  /api/offer          browser sends a WebRTC offer -> we answer and start a bot
  PATCH /api/offer          trickle ICE candidates
  GET   /api/doctors        doctors with their upcoming slots
  GET   /api/appointments   all appointments, newest first
  GET   /api/events         Server-Sent Events: bookings, cancellations, call state
  POST  /api/reset          wipe and re-seed the mock data (handy before a demo)
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from . import config, db, events
from .bot import run_bot

webrtc = SmallWebRTCRequestHandler(ice_servers=[IceServer(urls="stun:stun.l.google.com:19302")])


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    logger.info(f"Database ready at {config.DB_PATH}")
    yield
    await webrtc.close()


app = FastAPI(title="Clinic Voice Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ calls


@app.post("/api/offer")
async def offer(request: SmallWebRTCRequest, background_tasks: BackgroundTasks):
    async def on_connection(connection: SmallWebRTCConnection):
        background_tasks.add_task(run_bot, connection)

    return await webrtc.handle_web_request(
        request=request, webrtc_connection_callback=on_connection
    )


@app.patch("/api/offer")
async def ice_candidate(request: SmallWebRTCPatchRequest):
    await webrtc.handle_patch_request(request)
    return {"status": "ok"}


# --------------------------------------------------------------- dashboard


@app.get("/api/doctors")
def doctors():
    slots_by_doctor: dict[str, list[dict]] = {}
    for s in db.upcoming_slots(only_free=False):
        slots_by_doctor.setdefault(s["doctor_id"], []).append(
            {"id": s["id"], "starts_at": s["starts_at"], "booked": bool(s["is_booked"])}
        )
    return [
        {**d, "slots": slots_by_doctor.get(d["id"], [])}
        for d in db.list_doctors()
    ]


@app.get("/api/appointments")
def appointments():
    return db.list_appointments()


@app.get("/api/meta")
def meta():
    return {
        "clinic": config.CLINIC_NAME,
        "agent": config.AGENT_NAME,
        "timezone": config.CLINIC_TIMEZONE,
        "now": db.now().isoformat(),
        "llm": config.GOOGLE_MODEL,
    }


@app.post("/api/reset")
def reset():
    db.init(reset=True)
    events.publish("data_reset")
    return {"ok": True}


@app.get("/api/events")
async def stream(request: Request):
    queue = events.subscribe()

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while not await request.is_disconnected():
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {msg}\n\n"
                except TimeoutError:
                    yield f": ping {datetime.now().isoformat()}\n\n"  # keep proxies happy
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Serve the built dashboard (client/dist) if it exists, so one process runs it all.
DIST = Path(__file__).resolve().parents[2] / "client" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        file = DIST / path
        if path and file.is_file() and DIST in file.resolve().parents:
            return FileResponse(file)
        return FileResponse(DIST / "index.html")
