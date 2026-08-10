#!/usr/bin/env python3
"""Local FastAPI click-to-keep SAM studio with a preview-before-track gate."""

from __future__ import annotations

import argparse
import importlib
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from track import (
    SamAdapter,
    connected_component_clean,
    parse_points,
    prepare_frames,
    require_apple_silicon,
    require_dependencies,
    save_mask,
    save_preview,
)


HTML = """<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cutout studio</title>
<style>body{font:16px system-ui;margin:0 auto;max-width:760px;padding:18px;background:#fbfbfb;color:#111}img{max-width:100%;display:block;border:1px solid #ccc}button,input{font:inherit;padding:8px;margin:4px 0}p{color:#666}.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}</style></head>
<body><h1>Cutout studio</h1><p>Pick a frame where every limb you want is visible. Click to keep, shift-click to remove, then inspect the seed preview before Track.</p>
<img id="frame" alt="frame"><div class="row"><input id="slider" type="range" min="1" value="1"><span id="number"></span></div>
<button id="track">Track</button><p id="status"></p><script>
const frame=document.querySelector('#frame'), slider=document.querySelector('#slider'), number=document.querySelector('#number'), status=document.querySelector('#status');
let points=[]; let count=0;
async function init(){const r=await fetch('/api/info');const d=await r.json();count=d.frames;slider.max=count;slider.value=Math.max(2,Math.floor(count/2));show();}
function show(){number.textContent='frame '+slider.value;frame.src='/frames/'+String(slider.value).padStart(6,'0')+'.jpg';}
slider.addEventListener('input',show);
frame.addEventListener('click',async e=>{const box=frame.getBoundingClientRect();const x=(e.clientX-box.left)*frame.naturalWidth/box.width;const y=(e.clientY-box.top)*frame.naturalHeight/box.height;points.push([x,y,e.shiftKey?0:1]);status.textContent='points: '+points.length;await fetch('/api/points',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({frame:Number(slider.value)-1,points})});});
document.querySelector('#track').addEventListener('click',async()=>{status.textContent='Writing seed preview before propagation...';const r=await fetch('/api/track',{method:'POST'});const d=await r.json();status.textContent=d.message||d.detail||'done';});
init();
</script></body></html>"""


def build_app(clip: Path, checkpoint: Path, image_size: int) -> Any:
    try:
        fastapi = importlib.import_module("fastapi")
        responses = importlib.import_module("fastapi.responses")
    except ImportError as exc:
        raise RuntimeError("missing cutout studio dependency: fastapi. Install the optional cutout lines in pipeline/requirements.txt") from exc
    numpy, pil_image, (pil_draw, mlx_sam) = require_dependencies()
    frame_dir = Path(tempfile.mkdtemp(prefix="cutout-studio-"))
    frames = prepare_frames(clip, frame_dir)
    state: Dict[str, Any] = {"frame": 1, "points": [], "mask": None, "adapter": None}
    app = fastapi.FastAPI()

    @app.get("/", response_class=responses.HTMLResponse)
    def index() -> str:
        return HTML

    @app.get("/api/info")
    def info() -> Dict[str, int]:
        return {"frames": len(frames)}

    @app.get("/frames/{name}")
    def frame(name: str) -> Any:
        safe = Path(name).name
        path = frame_dir / safe
        if not path.exists():
            raise fastapi.HTTPException(status_code=404, detail="frame not found")
        return responses.FileResponse(path)

    @app.post("/api/points")
    def points(payload: Dict[str, Any]) -> Dict[str, str]:
        try:
            parsed = [(float(x), float(y), int(label)) for x, y, label in payload.get("points", [])]
            if int(payload.get("frame", 0)) <= 0:
                raise ValueError("choose a seed frame other than frame 0")
            state["frame"] = int(payload["frame"])
            state["points"] = parsed
            if state["adapter"] is None:
                state["adapter"] = SamAdapter(checkpoint, image_size, numpy, mlx_sam)
            mask = state["adapter"].predict_image(frames[state["frame"]], parsed)
            state["mask"], _ = connected_component_clean(mask, numpy)
            save_preview(frames[state["frame"]], state["mask"], parsed, clip.with_name(f"{clip.stem}_seed-preview.jpg"), state["frame"], pil_image, pil_draw, numpy)
            return {"message": "seed preview updated; inspect it before Track"}
        except (IndexError, TypeError, ValueError, RuntimeError) as exc:
            raise fastapi.HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/track")
    def track() -> Dict[str, str]:
        if state["mask"] is None or not state["points"]:
            raise fastapi.HTTPException(status_code=400, detail="click a seed frame first")
        preview = clip.with_name(f"{clip.stem}_seed-preview.jpg")
        save_preview(frames[state["frame"]], state["mask"], state["points"], preview, state["frame"], pil_image, pil_draw, numpy)
        masks = state["adapter"].propagate(frame_dir, state["frame"], state["points"])
        masks[state["frame"]] = state["mask"]
        output_dir = clip.with_name(f"{clip.stem}_masks")
        output_dir.mkdir(parents=True, exist_ok=True)
        for index, mask in sorted(masks.items()):
            save_mask(mask, output_dir / f"f{index + 1:05d}.png", pil_image, numpy)
        if len(masks) < len(frames):
            message = f"wrote {len(masks)} masks for {len(frames)} frames; inspect the missing frames"
        else:
            message = f"wrote {len(masks)} masks to {output_dir.name}"
        return {"message": message}

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clip", type=Path)
    parser.add_argument("--port", type=int, default=7870)
    parser.add_argument("--checkpoint", type=Path, default=Path("models/sam2.1-hiera-small-mlx"))
    parser.add_argument("--image-size", type=int, default=512)
    args = parser.parse_args()
    try:
        require_apple_silicon()
        clip = args.clip.resolve()
        if not clip.exists():
            raise RuntimeError(f"clip not found: {args.clip}")
        app = build_app(clip, args.checkpoint.resolve(), args.image_size)
        uvicorn = importlib.import_module("uvicorn")
        print(f"Serving cutout studio at http://127.0.0.1:{args.port}")
        uvicorn.run(app, host="127.0.0.1", port=args.port)
        return 0
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
