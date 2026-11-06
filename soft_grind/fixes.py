"""Repair existing projects: give videos that share a headline their own (the oldest keeps it)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import headlines, metadata, projects, thumbnail as T


def duplicates(root: Path, window: int = headlines.RECENT) -> list[tuple[str, list[str]]]:
    """[(quote, [project names, oldest first])] for quotes that two videos less than `window` videos apart share.
    Reusing a headline after that many videos is fine."""
    rows = []
    for d in projects.project_dirs(root):
        m = projects.meta(d)
        rows.append((m.get("created", 0), d.name, (m.get("quote") or "").strip()))
    rows.sort()
    groups: dict[str, list[tuple[int, str, str]]] = {}
    for pos, (_, name, q) in enumerate(rows):
        if q:
            groups.setdefault(q.lower(), []).append((pos, name, q))
    out = []
    for g in groups.values():
        if any(b[0] - a[0] < window for a, b in zip(g, g[1:])):
            out.append((g[0][2], [n for _, n, _ in g]))
    return out


def retitle(pdir: Path, new: str) -> dict:
    """New headline for one project: meta, title, first line of the description, upload.txt and the thumbnail picture."""
    pdir = Path(pdir)
    m = projects.meta(pdir)
    old = m.get("quote", "")
    title, desc = m.get("title", ""), m.get("description", "")
    if old and title.startswith(old):
        title = new + title[len(old):]
    if old and desc.startswith(old):
        desc = new + desc[len(old):]
    projects.set_meta(pdir, quote=new, title=title, description=desc, quote_placeholder=False)
    if m.get("title"):
        (pdir / "upload.txt").write_text(metadata.upload_txt(title, desc, [t.strip() for t in m.get("tags", "").split(",") if t.strip()],
                                                             m.get("pinned", ""), m.get("schedule", "")), encoding="utf-8")
    src = None
    li = m.get("library_image")
    candidates = ([pdir / "images" / f"{Path(li).stem}_16x9.png"] if li else []) + sorted((pdir / "images").glob("*_16x9.png"))
    for c in candidates:
        if c.exists():
            src = c
            break
    redrawn = False
    if src is not None and (pdir / "thumbnail.png").exists():
        im = Image.open(src); im.load()
        T.render_thumbnail(im, new, T.Layout()).save(pdir / "thumbnail.png")
        if m.get("headline_on_video", True):
            T.render_still(im, quote=new, layout=T.Layout()).save(pdir / "still.png")      # the video picture carries the headline too
        redrawn = True
    return {"name": pdir.name, "old": old, "new": new, "thumbnail_redrawn": redrawn}


def make_unique(root: Path) -> list[dict]:
    used = {(projects.meta(d).get("quote") or "").lower() for d in projects.project_dirs(root)}      # strict: avoids every existing one
    report = []
    for _, names in duplicates(root):
        for name in names[1:]:                                           # the oldest keeps its headline
            m = projects.meta(Path(root) / name)
            new = headlines.suggest(m.get("mood") or "calm", m.get("topic") or [], used, 1)[0]
            used.add(new.lower())
            report.append(retitle(Path(root) / name, new))
    return report
