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
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
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
                "atype": derive_type(a["name"], a.get("submission_types")),
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


# Above this many items in a bucket, collapse to per-course counts instead of
# listing each — keeps bunched deadlines from spamming the message.
LIST_THRESHOLD = 8

# Human-friendly type words for the count summaries (Reading = textbook work).
TYPE_LABEL = {
    "Discussion": "discussion", "Reading": "textbook", "Quiz": "quiz",
    "Exam": "exam", "Assignment": "assignment", "Project": "project",
}


def _type_label(atype: str) -> str:
    return TYPE_LABEL.get(atype or "Assignment", "assignment")


def _breakdown(entries: list) -> str:
    """'3 discussion · 3 textbook · 2 quiz' — type counts, most first."""
    c = Counter(_type_label(e.get("atype")) for e in entries)
    return " · ".join(f"{n} {lab}" for lab, n in
                      sorted(c.items(), key=lambda x: (-x[1], x[0])))


def _course_summary(entries: list) -> list:
    """One compact line per course: '*MKT-230* · 9 — 3 discussion · 3 textbook'."""
    groups = defaultdict(list)
    for e in entries:
        groups[short_course(e["course"])].append(e)
    lines = []
    for course in sorted(groups, key=lambda c: -len(groups[c])):
        es = groups[course]
        lines.append(f"  *{escape_md(course)}* · {len(es)} — {_breakdown(es)}")
    return lines


def _item_lines(entries: list, show_due: bool = False, today=None) -> list:
    """Individual bullet lines with links — for the most urgent buckets."""
    out = []
    for e in sorted(entries, key=lambda x: (x["course"], x["name"])):
        tail = f" _(was {fmt_date(e['due'])})_" if (show_due and today) else ""
        out.append(f"• {escape_md(e['name'])} — {escape_md(short_course(e['course']))}"
                   f"{tail}{link_suffix(e.get('url'))}")
    return out


def build_telegram_message(courses: list, today, include_daily_question: bool = True) -> str:
    """Compact, urgency-first radar.

    Imminent work (overdue + today) is listed by name with links so it's
    actionable; everything further out is collapsed to per-course type counts
    ('MKT-230 · 9 — 3 discussion · 3 textbook · 3 quiz') so bunched deadlines
    stay scannable. Emojis encode urgency: 🆘 overdue · 🔴 today · 🟠 tomorrow ·
    🟡 in 2 days · 🟢 this week.
    """
    overdue, due_today, this_week, upcoming = bucket_assignments(courses, today)
    tomorrow = [e for e in this_week if (e["due"] - today).days == 1]
    day2 = [e for e in this_week if (e["due"] - today).days == 2]
    rest = [e for e in this_week if (e["due"] - today).days >= 3]

    lines = [f"⚡ *Canvas · {fmt_date(today)}*", ""]

    # Urgent buckets list by name — unless bunched, then collapse to counts.
    if overdue:
        lines.append(f"🆘 *OVERDUE · {len(overdue)}*")
        lines += (_item_lines(overdue, show_due=True, today=today)
                  if len(overdue) <= LIST_THRESHOLD else _course_summary(overdue))
        lines.append("")

    if due_today:
        lines.append(f"🔴 *TODAY · {len(due_today)}*")
        lines += (_item_lines(due_today)
                  if len(due_today) <= LIST_THRESHOLD else _course_summary(due_today))
        lines.append("")

    if tomorrow:
        lines.append(f"🟠 *TOMORROW ({fmt_date(today + timedelta(days=1))}) · {len(tomorrow)}*")
        lines += _course_summary(tomorrow)
        lines.append("")

    if day2:
        lines.append(f"🟡 *{fmt_date(today + timedelta(days=2))} · {len(day2)}*")
        lines += _course_summary(day2)
        lines.append("")

    if rest:
        lines.append(f"🟢 *THIS WEEK · {len(rest)}*")
        lines += _course_summary(rest)
        lines.append("")

    if upcoming:
        lines.append(f"⚪ _Later: {len(upcoming)} more_")
        lines.append("")

    if not any([overdue, due_today, tomorrow, day2, rest, upcoming]):
        lines += ["✅ *All clear — nothing due.*", ""]

    if include_daily_question:
        lines += build_daily_question(overdue + due_today + this_week + upcoming)

    return "\n".join(lines).rstrip()


def derive_type(name: str, submission_types) -> str:
    """Map Canvas submission types + name to a Notion 'Assignment Type' option
    (Assignment / Quiz / Exam / Discussion / Project / Reading)."""
    st = submission_types or []
    low = (name or "").lower()
    if "discussion_topic" in st:
        return "Discussion"
    if any(k in low for k in ("exam", "midterm", "final")) or (
            "test" in low and "smartbook" not in low):
        return "Exam"
    if "online_quiz" in st or "quiz" in low:
        return "Quiz"
    if "smartbook" in low or "reading" in low or "read " in low:
        return "Reading"
    if "project" in low:
        return "Project"
    return "Assignment"


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
                    "atype": derive_type(a["name"], a.get("submission_types")),
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
                "atype": derive_type(a["name"], a.get("submission_types")),
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
