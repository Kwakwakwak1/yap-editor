#!/usr/bin/env python3
"""Build a static, mobile-first review page and local render manifest."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def load_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"renders": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"could not read manifest: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("renders", []), list):
        raise RuntimeError("manifest must contain a renders array")
    return value


def make_html(entries: List[Dict[str, Any]]) -> str:
    embedded = json.dumps(entries, ensure_ascii=False).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reel review</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, sans-serif; background: #fbfbfb; color: #111; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #fbfbfb; color: #111; }}
    main {{ max-width: 680px; margin: 0 auto; padding: 22px 16px 48px; }}
    header {{ border-bottom: 1px solid #d7d7d7; padding-bottom: 16px; margin-bottom: 8px; }}
    h1 {{ font-size: 22px; font-weight: 650; margin: 0 0 5px; }}
    p {{ color: #666; margin: 5px 0; line-height: 1.45; }}
    .toolbar {{ display: flex; justify-content: flex-end; padding: 12px 0; }}
    button {{ border: 1px solid #222; background: #fff; color: #111; padding: 9px 12px; font: inherit; cursor: pointer; }}
    button:hover {{ background: #eef5f8; }}
    .render {{ border-top: 1px solid #d7d7d7; padding: 20px 0 24px; }}
    video {{ display: block; width: 100%; max-height: 74vh; background: #000; }}
    h2 {{ font-size: 17px; margin: 12px 0 3px; font-weight: 650; }}
    textarea {{ display: block; width: 100%; min-height: 66px; border: 1px solid #bbb; background: #fff; padding: 8px; font: inherit; margin: 10px 0; }}
    .actions {{ display: flex; gap: 8px; align-items: center; }}
    .status {{ color: #176b86; font-size: 14px; }}
    .approve {{ border-color: #176b86; }}
  </style>
</head>
<body>
  <main>
    <header><h1>Reel review</h1><p>Watch each render on the device where it will be judged. Decisions stay in this browser until copied.</p></header>
    <div class="toolbar"><button id="copy">Copy decisions</button></div>
    <section id="renders"></section>
  </main>
  <script>
    const renders = {embedded};
    const storageKey = 'yap-editor-review-decisions';
    let decisions = {{}};
    try {{ decisions = JSON.parse(localStorage.getItem(storageKey) || '{{}}'); }} catch (error) {{ decisions = {{}}; }}
    const save = () => localStorage.setItem(storageKey, JSON.stringify(decisions));
    const renderList = document.querySelector('#renders');
    function draw() {{
      renderList.innerHTML = renders.map((item) => {{
        const decision = decisions[item.filename] || {{}};
        const status = decision.status ? 'Decision: ' + decision.status : 'No decision yet';
        return `<article class="render"><video controls playsinline preload="metadata" src="${{item.src}}"></video><h2>${{item.title}}</h2><p>${{item.note || ''}}</p><textarea data-note="${{item.filename}}" placeholder="Notes for the editor">${{decision.note || ''}}</textarea><div class="actions"><button class="approve" data-status="approved" data-file="${{item.filename}}">Approve</button><button data-status="denied" data-file="${{item.filename}}">Deny</button><span class="status">${{status}}</span></div></article>`;
      }}).join('');
      document.querySelectorAll('[data-status]').forEach((button) => button.addEventListener('click', () => {{
        const filename = button.dataset.file;
        const note = document.querySelector(`[data-note="${{CSS.escape(filename)}}"]`).value;
        decisions[filename] = {{status: button.dataset.status, note, decided_at: new Date().toISOString()}};
        save(); draw();
      }}));
      document.querySelectorAll('[data-note]').forEach((field) => field.addEventListener('input', () => {{
        const existing = decisions[field.dataset.note] || {{}};
        decisions[field.dataset.note] = {{...existing, note: field.value}};
        save();
      }}));
    }}
    document.querySelector('#copy').addEventListener('click', async () => {{
      const blob = JSON.stringify(decisions, null, 2);
      try {{ await navigator.clipboard.writeText(blob); alert('Decisions copied'); }} catch (error) {{ window.prompt('Copy decisions', blob); }}
    }});
    draw();
  </script>
</body>
</html>
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--add", required=True, type=Path)
    parser.add_argument("--title", default=None)
    parser.add_argument("--note", default="")
    parser.add_argument("--out", type=Path, default=Path("review/build"))
    args = parser.parse_args()
    source = args.add.resolve()
    if not source.exists() or not source.is_file():
        print(f"ERROR: render not found: {args.add}", file=sys.stderr)
        return 1
    out = args.out.resolve()
    media_dir = out / "media"
    manifest_path = out / "manifest.json"
    try:
        manifest = load_manifest(manifest_path)
        destination = media_dir / source.name
        media_dir.mkdir(parents=True, exist_ok=True)
        if source != destination:
            shutil.copy2(source, destination)
        entry = {
            "filename": source.name,
            "src": f"media/{source.name}",
            "title": args.title or source.stem.replace("-", " "),
            "note": args.note,
            "added_at": now(),
        }
        entries = [item for item in manifest["renders"] if item.get("filename") != source.name]
        entries.append(entry)
        manifest["renders"] = entries
        out.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (out / "index.html").write_text(make_html(entries), encoding="utf-8")
        print(f"Added {source.name} to review manifest")
        print(f"Wrote {display_path(out / 'index.html')}")
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
