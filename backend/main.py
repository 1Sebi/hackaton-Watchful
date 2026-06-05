"""Watchful FastAPI app — REST + MJPEG + WebSockets, with the agent loop running
as a background thread for the app's lifetime.

Run:  uvicorn backend.main:app --reload   ->  http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import conditions, events, stream, ws, zones
from backend.core.pipeline import get_pipeline
from backend.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    pipeline = get_pipeline()
    pipeline.start()
    try:
        yield
    finally:
        pipeline.stop()


app = FastAPI(title="Watchful", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

app.include_router(conditions.router)
app.include_router(events.router)
app.include_router(zones.router)
app.include_router(stream.router)
app.include_router(ws.router)


@app.get("/", tags=["meta"])
def root():
    return {"name": "Watchful", "status": "ok", "pipeline": get_pipeline().state()}
