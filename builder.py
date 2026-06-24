"""
builder.py — converts fetcher.py output into export_payload.json.

Usage:
    python fetcher.py > canvas_raw.json
    python builder.py canvas_raw.json [export_payload.json]

The output file is then passed to exporter.py:
    python exporter.py export_payload.json
"""

import json
import random
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telegram_utils import escape_md, link_suffix

# Canvas due_at is UTC. Students care about the calendar day in their own zone,
# so convert to Central before taking the date (an 11:59 PM Central deadline is
# 04:59 UTC the NEXT day — taking the UTC date shows it one day late).
LOCAL_TZ = ZoneInfo("America/Chicago")


def log(msg):
    print(f"[BUILDER] {msg}", file=sys.stderr)


def parse_due(due_at: str):
    if not due_at:
        return None
    try:
        dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        # Date-only or naive string: treat as a wall date, no shift.
        return dt.date()
    # Timezone-aware (e.g. Canvas "...Z"): convert to Central, then take the date.
    return dt.astimezone(LOCAL_TZ).date()


def bucket_assignments(courses: list, today):
    """Sort unsubmitted, dated assignments into time buckets.

    Returns (overdue, due_today, this_week, upcoming) lists of
    {name, course, due} dicts. Shared by the radar message and the
    /today, /week and evening-preview handlers so the bucketing rules
    live in exactly one place.
    """
    overdue, due_today, this_week, upcoming = [], [], [], []
    for course in courses:
        for a in course.get("assignments", []):
            if a.get("has_submitted"):
                continue
            due = parse_due(a.get("due_at"))
            if due is None:
                continue
            entry = {
                "name": a["name"],
                "course": course["name"],
                "due": due,
                "url": a.get("url"),
            }
            delta = (due - today).days
            if delta < 0:
                overdue.append(entry)
            elif delta == 0:
                due_today.append(entry)
            elif delta <= 7:
                this_week.append(entry)
            else:
                upcoming.append(entry)
    return overdue, due_today, this_week, upcoming


def build_announcements_section(courses: list, limit: int = 5) -> list:
    """Lines for recent course announcements (already fetched by fetcher.py).

    Returns [] when there are none, so callers can `lines += ...` freely.
    """
    items = []
    for course in courses:
        for ann in course.get("announcements", []):
            items.append({
                "title": ann.get("title") or "Untitled",
                "course": course.get("name", ""),
            })
    if not items:
        return []
    lines = ["📣 *ANNOUNCEMENTS*"]
    for a in items[:limit]:
        lines.append(
            f"• {escape_md(a['title'])} — {escape_md(short_course(a['course']))}"
        )
    if len(items) > limit:
        lines.append(f"_...and {len(items) - limit} more_")
    lines.append("")
    return lines


def fmt_date(d) -> str:
    """'Mon Jun 8' — no leading zero, works on all platforms."""
    return f"{d.strftime('%a %b')} {d.day}"


def short_course(name: str) -> str:
    """'MKT-230-353' → 'MKT-230'"""
    parts = name.split("-")
    return "-".join(parts[:2]) if len(parts) >= 3 else name


def build_daily_question(all_pending) -> list:
    """Daily active-recall prompt block. Returns [] when nothing is pending."""
    if not all_pending:
        return []
    pick = random.choice(all_pending)
    prompts = [
        f'Without your notes: What is the main deliverable for *"{escape_md(pick["name"])}"*?',
        f'Explain the goal of *"{escape_md(pick["name"])}"* in one sentence.',
        f'What do you need to do first to complete *"{escape_md(pick["name"])}"*?',
        f'What would a strong submission of *"{escape_md(pick["name"])}"* look like?',
    ]
    return [
        "─────────────────────",
        "🧠 *DAILY QUESTION*",
        "",
        random.choice(prompts),
        "",
        "_Think first. Then check your notes._",
        "─────────────────────",
    ]


def build_telegram_message(courses: list, today, include_daily_question: bool = True) -> str:
    overdue, due_today, this_week, upcoming = bucket_assignments(courses, today)

    lines = [f"⚡ *Canvas Radar — {fmt_date(today)}*", ""]

    if overdue:
        lines.append("⛔ *OVERDUE — ACT NOW*")
        for e in overdue:
            lines.append(
                f"• {escape_md(e['name'])} — {escape_md(short_course(e['course']))}"
                f" _(was due {fmt_date(e['due'])})_{link_suffix(e.get('url'))}"
            )
        lines.append("")

    if due_today:
        lines.append("🔴 *DUE TODAY*")
        for e in due_today:
            lines.append(
                f"• {escape_md(e['name'])} — {escape_md(short_course(e['course']))}"
                f"{link_suffix(e.get('url'))}"
            )
        lines.append("")

    if this_week:
        lines.append("📅 *DUE THIS WEEK*")
        for e in this_week:
            lines.append(
                f"• {escape_md(e['name'])} — {escape_md(short_course(e['course']))}"
                f" _({fmt_date(e['due'])})_{link_suffix(e.get('url'))}"
            )
        lines.append("")

    if upcoming:
        lines.append("📌 *COMING UP*")
        for e in upcoming[:5]:
            lines.append(
                f"• {escape_md(e['name'])} — {escape_md(short_course(e['course']))}"
                f" _({fmt_date(e['due'])})_{link_suffix(e.get('url'))}"
            )
        if len(upcoming) > 5:
            lines.append(f"_...and {len(upcoming) - 5} more_")
        lines.append("")

    if not any([overdue, due_today, this_week, upcoming]):
        lines += ["✅ All clear. Nothing pending.", ""]

    if include_daily_question:
        lines += build_daily_question(overdue + due_today + this_week + upcoming)

    return "\n".join(lines)


def build_notion_tasks(courses: list, today, max_ahead_days=None) -> list:
    tasks = []
    for course in courses:
        for a in course.get("assignments", []):
            due = parse_due(a.get("due_at"))

            if due is None:
                # No due date: still real work, so surface it in Notion. Submitted
                # ones are marked "Submitted" (NOT dropped) so the dashboard shows
                # the correct status and can file them under the Submitted view.
                tasks.append({
                    "title": a["name"],
                    "course": course["name"],
                    "due_date": None,
                    "status": "Submitted" if a.get("has_submitted") else "To Do",
                    "checklist": "",
                    "url": a.get("url"),
                    "points": a.get("points_possible"),
                })
                continue

            delta = (due - today).days

            # Keep the Notion planner light: drop only FAR-FUTURE, still-unsubmitted
            # work. Submitted items are always synced so their status stays correct
            # (previously past+submitted were skipped → stuck showing "To Do").
            if (max_ahead_days is not None and delta > max_ahead_days
                    and not a.get("has_submitted")):
                continue

            if a.get("has_submitted"):
                status = "Submitted"
            elif delta < 0:
                status = "Overdue"
            else:
                status = "To Do"

            tasks.append({
                "title": a["name"],
                "course": course["name"],
                # Central calendar date (parse_due handles the UTC->Central shift),
                # not the raw UTC prefix which lands a day late.
                "due_date": due.isoformat(),
                "status": status,
                "checklist": "",
                "url": a.get("url"),
                "points": a.get("points_possible"),
            })
    return tasks


def main():
    if len(sys.argv) < 2:
        log("Usage: python builder.py <canvas_raw.json> [export_payload.json]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "export_payload.json"

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        log(f"Failed to read {input_path}: {e}")
        sys.exit(1)

    canvas = raw.get("canvas", {})
    if "error" in canvas:
        log(f"Canvas error in input: {canvas['error']}")
        sys.exit(1)

    courses = canvas.get("courses", [])
    today = datetime.now(timezone.utc).date()

    telegram_msg = build_telegram_message(courses, today)
    notion_tasks = build_notion_tasks(courses, today)

    payload = {
        "telegram_message": telegram_msg,
        "notion_tasks": notion_tasks,
    }

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        log(
            f"Written to {output_path} "
            f"({len(notion_tasks)} tasks, {len(telegram_msg)} chars in message)"
        )
    except Exception as e:
        log(f"Failed to write {output_path}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
