"""The planning page: which video goes out on which day, and which upload slots (Mon / Wed / Fri 15:00) are still free."""
from __future__ import annotations

import calendar
import datetime as dt
from pathlib import Path

from . import metadata, projects

SLOT_DAYS = (0, 2, 4)          # Monday, Wednesday, Friday
SLOT_HOUR = 15
FMT = "%Y-%m-%d %H:%M"


def parse(schedule: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(schedule, FMT)
    except (TypeError, ValueError):
        return None


def month_weeks(year: int, month: int) -> list[list[dt.date]]:
    """The weeks shown for a month, Monday first, including the days of the neighbouring months that fill the rows."""
    return calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    m = year * 12 + (month - 1) + delta
    return m // 12, m % 12 + 1


def by_day(items: list[dict]) -> dict[dt.date, list[dict]]:
    """Videos with a publish date, grouped per day (earliest time first)."""
    out: dict[dt.date, list[dict]] = {}
    for i in items:
        when = parse(i.get("schedule", ""))
        if when:
            out.setdefault(when.date(), []).append({**i, "when": when})
    for v in out.values():
        v.sort(key=lambda r: r["when"])
    return out


def free_slots(items: list[dict], n: int = 8, now: dt.datetime | None = None) -> list[dt.datetime]:
    """The next n upload slots in the future that no video uses yet."""
    now = now or dt.datetime.now()
    taken = {i.get("schedule", "") for i in items}
    out, day = [], now.date()
    while len(out) < n:
        slot = dt.datetime.combine(day, dt.time(SLOT_HOUR, 0))
        if day.weekday() in SLOT_DAYS and slot > now and slot.strftime(FMT) not in taken:
            out.append(slot)
        day += dt.timedelta(days=1)
    return out


def is_free_slot(day: dt.date, plan: dict[dt.date, list[dict]], now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now()
    return (day.weekday() in SLOT_DAYS and dt.datetime.combine(day, dt.time(SLOT_HOUR, 0)) > now and not plan.get(day))


def unplanned(items: list[dict], now: dt.datetime | None = None) -> list[dict]:
    """Videos not on YouTube yet that have no date, or a date that has already passed."""
    now = now or dt.datetime.now()
    out = []
    for i in items:
        if i.get("youtube_id"):
            continue
        when = parse(i.get("schedule", ""))
        if when is None or when <= now:
            out.append(i)
    return out


def assign(pdir: Path, when: dt.datetime) -> None:
    """Give a video a publish date. A video already on YouTube keeps the date YouTube has (change it in YouTube Studio)."""
    pdir = Path(pdir)
    m = projects.meta(pdir)
    if m.get("youtube_id"):
        raise RuntimeError("This video is already on YouTube: change its date in YouTube Studio.")
    sched = when.strftime(FMT)
    projects.set_meta(pdir, schedule=sched)
    if m.get("title") and (pdir / "upload.txt").exists():           # keep the upload notes in step
        tags = [t.strip() for t in (m.get("tags") or "").split(",") if t.strip()]
        (pdir / "upload.txt").write_text(metadata.upload_txt(m["title"], m.get("description", ""), tags, m.get("pinned", ""), sched),
                                         encoding="utf-8")


def unschedule(pdir: Path) -> None:
    pdir = Path(pdir)
    if projects.meta(pdir).get("youtube_id"):
        raise RuntimeError("This video is already on YouTube: change its date in YouTube Studio.")
    projects.set_meta(pdir, schedule="")
