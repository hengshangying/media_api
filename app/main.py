#!/usr/bin/env python3
"""Minimal media library API for Flutter clients."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

TZ = timezone(timedelta(hours=8))
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/workspace/media")).resolve()
META_DIR = MEDIA_ROOT / ".meta"
PROGRESS_DIR = META_DIR / "progress"
API_TOKEN = os.environ.get("MEDIA_API_TOKEN", "").strip()
BASE_PUBLIC = os.environ.get("MEDIA_PUBLIC_BASE", "http://127.0.0.1:8787").rstrip("/")

TYPE_DIRS = {
    "movie": MEDIA_ROOT / "movies",
    "episode": MEDIA_ROOT / "shows",
    "music": MEDIA_ROOT / "music",
}

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".ts"}
AUDIO_EXTS = {".mp3", ".flac", ".aac", ".m4a", ".wav", ".ogg"}
SUB_EXTS = {".srt", ".vtt", ".ass"}
COVER_NAMES = ("cover.jpg", "cover.png", "poster.jpg", "poster.png", "folder.jpg")

for d in list(TYPE_DIRS.values()) + [META_DIR, PROGRESS_DIR, MEDIA_ROOT / "uploads"]:
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="media-api", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
security = HTTPBearer(auto_error=False)


def now_iso() -> str:
    return datetime.now(TZ).isoformat()


def ok(data: Any) -> dict:
    return {"ok": True, "data": data, "error": None}


def err(code: str, message: str, status: int = 400):
    return JSONResponse(
        status_code=status,
        content={"ok": False, "data": None, "error": {"code": code, "message": message}},
    )


def require_auth(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not API_TOKEN:
        return True
    if creds is None or creds.scheme.lower() != "bearer" or creds.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


def meta_path(vid: str) -> Path:
    return META_DIR / f"{vid}.json"


def load_meta(vid: str) -> Optional[dict]:
    p = meta_path(vid)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_meta(meta: dict) -> None:
    meta_path(meta["id"]).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def list_all_meta() -> list[dict]:
    items = []
    for p in META_DIR.glob("*.json"):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items


def guess_type(name: str, explicit: Optional[str] = None) -> str:
    if explicit in TYPE_DIRS:
        return explicit
    ext = Path(name).suffix.lower()
    if ext in AUDIO_EXTS:
        return "music"
    return "movie"


def probe_basic(path: Path) -> dict:
    size = path.stat().st_size if path.exists() else 0
    return {
        "duration_sec": None,
        "size_bytes": size,
        "resolution": None,
        "mime": "application/octet-stream",
    }


def public_url(path: str) -> str:
    return f"{BASE_PUBLIC}{path}"


def to_list_item(m: dict) -> dict:
    return {
        "id": m["id"],
        "title": m["title"],
        "type": m["type"],
        "duration_sec": m.get("duration_sec"),
        "size_bytes": m.get("size_bytes"),
        "resolution": m.get("resolution"),
        "cover_url": public_url(f"/api/v1/videos/{m['id']}/cover"),
        "created_at": m.get("created_at"),
        "updated_at": m.get("updated_at"),
    }


def to_detail(m: dict) -> dict:
    item = to_list_item(m)
    item.update(
        {
            "path": m.get("rel_path"),
            "mime": m.get("mime"),
            "subtitle_tracks": m.get("subtitle_tracks", []),
            "qualities": m.get(
                "qualities",
                [{"id": "source", "label": "原画", "width": None, "height": None}],
            ),
        }
    )
    return item


def scan_sidecar_subs(file_path: Path, vid: str) -> list[dict]:
    tracks = []
    stem = file_path.stem
    for p in file_path.parent.glob(stem + ".*"):
        if p.suffix.lower() not in SUB_EXTS:
            continue
        sid = f"sub_{uuid.uuid4().hex[:8]}"
        lang = "und"
        m = re.search(r"\.(zh|zh-cn|zh-hans|en|ja|ko)\.", p.name, re.I)
        if m:
            lang = m.group(1).lower()
        tracks.append(
            {
                "id": sid,
                "lang": lang,
                "label": p.name,
                "file": str(p.relative_to(MEDIA_ROOT)),
                "url": public_url(f"/api/v1/videos/{vid}/subtitles/{sid}"),
            }
        )
    return tracks


@app.get("/health")
def health():
    return {"status": "up", "time": now_iso()}


@app.get("/api/v1/videos")
def list_videos(
    q: Optional[str] = None,
    type: str = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: bool = Depends(require_auth),
):
    items = list_all_meta()
    if type and type != "all":
        items = [i for i in items if i.get("type") == type]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in (i.get("title") or "").lower()]
    total = len(items)
    start = (page - 1) * page_size
    chunk = items[start : start + page_size]
    return ok(
        {
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": [to_list_item(i) for i in chunk],
        }
    )


@app.get("/api/v1/search")
def search(q: str = Query(...), page: int = 1, page_size: int = 20, _: bool = Depends(require_auth)):
    return list_videos(q=q, type="all", page=page, page_size=page_size)


@app.get("/api/v1/videos/{vid}")
def video_detail(vid: str, _: bool = Depends(require_auth)):
    m = load_meta(vid)
    if not m:
        return err("NOT_FOUND", "video not found", 404)
    return ok(to_detail(m))


@app.get("/api/v1/videos/{vid}/play")
def video_play(vid: str, quality: str = "source", _: bool = Depends(require_auth)):
    m = load_meta(vid)
    if not m:
        return err("NOT_FOUND", "video not found", 404)
    return ok(
        {
            "play_type": "direct",
            "url": public_url(f"/api/v1/videos/{vid}/stream?quality={quality}"),
            "expires_in": 3600,
            "headers": {"Authorization": "Bearer <same-token>"},
            "quality": quality,
        }
    )


@app.get("/api/v1/videos/{vid}/stream")
def video_stream(vid: str, quality: str = "source", _: bool = Depends(require_auth)):
    m = load_meta(vid)
    if not m:
        raise HTTPException(404, "not found")
    path = MEDIA_ROOT / m["rel_path"]
    if not path.exists():
        raise HTTPException(404, "file missing")
    return FileResponse(
        path,
        media_type=m.get("mime") or "application/octet-stream",
        filename=path.name,
    )


@app.get("/api/v1/videos/{vid}/cover")
def video_cover(vid: str, _: bool = Depends(require_auth)):
    m = load_meta(vid)
    if not m:
        raise HTTPException(404, "not found")
    cover = m.get("cover_path")
    if cover:
        p = MEDIA_ROOT / cover
        if p.exists():
            return FileResponse(p)
    # sidecar covers next to media
    media = MEDIA_ROOT / m["rel_path"]
    for name in COVER_NAMES:
        cand = media.parent / name
        if cand.exists():
            return FileResponse(cand)
    raise HTTPException(404, "no cover")


@app.get("/api/v1/videos/{vid}/subtitles")
def list_subs(vid: str, _: bool = Depends(require_auth)):
    m = load_meta(vid)
    if not m:
        return err("NOT_FOUND", "video not found", 404)
    tracks = m.get("subtitle_tracks", [])
    return ok([{"id": t["id"], "lang": t.get("lang"), "label": t.get("label"), "url": t.get("url")} for t in tracks])


@app.get("/api/v1/videos/{vid}/subtitles/{sub_id}")
def get_sub(vid: str, sub_id: str, _: bool = Depends(require_auth)):
    m = load_meta(vid)
    if not m:
        raise HTTPException(404, "not found")
    for t in m.get("subtitle_tracks", []):
        if t["id"] == sub_id:
            p = MEDIA_ROOT / t["file"]
            if not p.exists():
                raise HTTPException(404, "subtitle missing")
            return FileResponse(p)
    raise HTTPException(404, "subtitle not found")


@app.put("/api/v1/videos/{vid}/progress")
async def put_progress(vid: str, body: dict, _: bool = Depends(require_auth)):
    m = load_meta(vid)
    if not m:
        return err("NOT_FOUND", "video not found", 404)
    device = body.get("device_id") or "default"
    payload = {
        "position_sec": float(body.get("position_sec") or 0),
        "duration_sec": body.get("duration_sec"),
        "device_id": device,
        "updated_at": now_iso(),
    }
    out = PROGRESS_DIR / f"{vid}__{device}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ok({"saved": True})


@app.get("/api/v1/videos/{vid}/progress")
def get_progress(vid: str, device_id: str = "default", _: bool = Depends(require_auth)):
    m = load_meta(vid)
    if not m:
        return err("NOT_FOUND", "video not found", 404)
    p = PROGRESS_DIR / f"{vid}__{device_id}.json"
    if not p.exists():
        return ok({"position_sec": 0, "duration_sec": None, "device_id": device_id})
    return ok(json.loads(p.read_text(encoding="utf-8")))


@app.post("/api/v1/videos/upload")
async def upload_video(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    type: Optional[str] = Form("movie"),
    _: bool = Depends(require_auth),
):
    filename = Path(file.filename or "upload.bin").name
    vtype = guess_type(filename, type)
    dest_dir = TYPE_DIRS[vtype]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    # avoid overwrite
    if dest.exists():
        dest = dest_dir / f"{dest.stem}_{uuid.uuid4().hex[:6]}{dest.suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    vid = f"vid_{uuid.uuid4().hex[:12]}"
    basic = probe_basic(dest)
    rel = str(dest.relative_to(MEDIA_ROOT))
    mime = file.content_type or basic["mime"]
    meta = {
        "id": vid,
        "title": title or dest.stem,
        "type": vtype,
        "rel_path": rel,
        "mime": mime,
        "duration_sec": basic["duration_sec"],
        "size_bytes": basic["size_bytes"],
        "resolution": basic["resolution"],
        "cover_path": None,
        "qualities": [{"id": "source", "label": "原画", "width": None, "height": None}],
        "subtitle_tracks": scan_sidecar_subs(dest, vid),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    save_meta(meta)
    return ok(to_detail(meta))


@app.delete("/api/v1/videos/{vid}")
def delete_video(vid: str, _: bool = Depends(require_auth)):
    m = load_meta(vid)
    if not m:
        return err("NOT_FOUND", "video not found", 404)
    path = MEDIA_ROOT / m["rel_path"]
    if path.exists():
        path.unlink()
    meta_path(vid).unlink(missing_ok=True)
    for p in PROGRESS_DIR.glob(f"{vid}__*.json"):
        p.unlink(missing_ok=True)
    return ok({"deleted": True, "id": vid})


@app.get("/")
def root():
    return {
        "service": "media-api",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
        "api": "/api/v1/videos",
    }
