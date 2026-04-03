"""FastAPI server: REST API + WebSocket replay + static file serving."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .data_loader import DataLoader
from .db import AnnotationDB
from .models import AnnotationCreate
from .trace_builder import build_agent_graph, build_outer_graph, build_replay_events

app = FastAPI(title="OpenClaw Trace Viewer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialized at startup
loader: DataLoader = None  # type: ignore
annotation_db: AnnotationDB = None  # type: ignore


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


@app.get("/api/sessions")
def list_sessions(
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    model: Optional[str] = None,
    confidence: Optional[str] = None,
    has_errors: Optional[bool] = None,
    keyword: Optional[str] = None,
    annotation_status: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
):
    loader.check_reload()
    ann_map = annotation_db.get_status_map()
    items, total = loader.get_sessions(
        category=category,
        subcategory=subcategory,
        model=model,
        confidence=confidence,
        has_errors=has_errors,
        keyword=keyword,
        annotation_status=annotation_status,
        annotation_map=ann_map,
        offset=offset,
        limit=limit,
    )
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    loader.check_reload()
    session = loader.get_session(sid)
    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    annotation = annotation_db.get(sid)
    session["annotation"] = annotation.model_dump() if annotation else None
    return session


@app.get("/api/sessions/{sid}/graph")
def get_session_graph(sid: str):
    loader.check_reload()
    session = loader.get_session(sid)
    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    agent_trace = session.get("agent_trace", [])
    classification = session.get("classification", {})
    error_report = session.get("error_report")
    graph = build_agent_graph(agent_trace, classification, error_report)
    return graph


@app.get("/api/pipeline/graph")
def get_pipeline_graph():
    loader.check_reload()
    summary = loader.get_summary()
    graph = build_outer_graph(summary, loader.total)
    return graph


@app.get("/api/summary")
def get_summary():
    loader.check_reload()
    return loader.get_summary()


@app.get("/api/filters")
def get_filters():
    loader.check_reload()
    return loader.get_filters()


@app.get("/api/subcategory-counts")
def get_subcategory_counts(category: Optional[str] = None):
    loader.check_reload()
    counts = loader.get_subcategory_counts(category=category)
    return {"counts": counts, "category": category}


@app.get("/api/error-sessions")
def list_error_sessions(
    model: Optional[str] = None,
    error_type: Optional[str] = None,
    recovered: Optional[bool] = None,
    error_loop: Optional[bool] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
):
    """List only sessions that have errors, with error_report data merged."""
    loader.check_reload()
    results = []
    for sid in loader.sids:
        session = loader.get_session(sid)
        cls = session.get("classification", {})
        err = session.get("error_report")
        if not err or cls.get("tool_error_count", 0) == 0:
            continue
        if model and cls.get("model") != model:
            continue
        if category and cls.get("primary_category") != category:
            continue
        if error_type and error_type not in cls.get("error_types", []):
            continue
        if recovered is not None and err.get("agent_recovered") != recovered:
            continue
        if error_loop is not None and err.get("error_loop_detected") != error_loop:
            continue
        if keyword:
            kw = keyword.lower()
            if kw not in (cls.get("user_intent_summary", "") + cls.get("sid", "")).lower():
                continue
        results.append({**cls, "error_report": err})
    results.sort(key=lambda x: x.get("tool_error_count", 0), reverse=True)
    return {"items": results, "total": len(results)}


# --- Annotations ---

@app.post("/api/annotations/{sid}")
def upsert_annotation(sid: str, body: AnnotationCreate):
    annotation_db.upsert(sid, body)
    return {"ok": True}


@app.get("/api/annotations")
def list_annotations():
    annotations = annotation_db.get_all()
    progress = annotation_db.progress(loader.total)
    return {"annotations": [a.model_dump() for a in annotations], "progress": progress.model_dump()}


@app.get("/api/annotations/export")
def export_annotations():
    data = annotation_db.export_jsonl()
    return JSONResponse(data)


@app.delete("/api/annotations/{sid}")
def delete_annotation(sid: str):
    ok = annotation_db.delete(sid)
    return {"ok": ok}


# ---------------------------------------------------------------------------
# WebSocket replay
# ---------------------------------------------------------------------------


@app.websocket("/ws/replay/{sid}")
async def replay_trace(websocket: WebSocket, sid: str):
    await websocket.accept()
    session = loader.get_session(sid)
    if not session:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return

    events = build_replay_events(session)
    speed = 1.0  # default speed multiplier

    try:
        for i, event in enumerate(events):
            # Check for control messages (non-blocking)
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.01)
                if msg.get("type") == "speed":
                    speed = max(0.1, min(10.0, float(msg.get("value", 1.0))))
                elif msg.get("type") == "pause":
                    # Wait for resume
                    while True:
                        msg = await websocket.receive_json()
                        if msg.get("type") == "resume":
                            break
                        if msg.get("type") == "speed":
                            speed = max(0.1, min(10.0, float(msg.get("value", 1.0))))
            except asyncio.TimeoutError:
                pass

            await websocket.send_json(event)

            # Delay between events
            if i < len(events) - 1:
                next_t = events[i + 1]["timestamp"]
                delay_ms = (next_t - event["timestamp"]) / speed
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000.0)

    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Static files (served after API routes)
# ---------------------------------------------------------------------------

UI_DIST = Path(__file__).parent / "ui" / "dist"


@app.get("/")
def index():
    index_file = UI_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"error": "Frontend not built. Run: cd ui && npm run build"}, status_code=404)


# Mount static assets if dist exists
if UI_DIST.exists():
    app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="OpenClaw Trace Viewer")
    parser.add_argument("--data-dir", required=True, help="Path to pipeline output directory")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    global loader, annotation_db
    data_dir = Path(args.data_dir)
    loader = DataLoader(data_dir)
    annotation_db = AnnotationDB(data_dir / "annotations.db")

    print(f"Loaded {loader.total} sessions from {data_dir}")
    print(f"Starting server at http://{args.host}:{args.port}")

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
