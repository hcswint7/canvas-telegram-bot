"""
run_briefing.py — single multi-mode entrypoint for the Canvas bot.

Replaces the old three-subprocess dance (fetcher | builder | exporter) with one
importable orchestrator that reuses those modules' functions directly. Used by
the scheduled GitHub Actions briefings AND by the /sync command in bot_poll.py.

Usage:
    python run_briefing.py --mode morning              # full radar + announcements + Notion sync
    python run_briefing.py --mode midday               # announcements pulse + brain teaser
    python run_briefing.py --mode evening              # recall drill + exam prep + tomorrow preview
    python run_briefing.py --mode morning --dry-run    # print message, send/write nothing

Schedule (see .github/workflows/briefings.yml) maps each cron to a --mode.
"""

import argparse
import os
import random
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

import spaced_rep_scheduler
from builder import (
    build_announcements_section,
    build_notion_tasks,
    build_telegram_message,
    bucket_assignments,
    fmt_date,
    short_course,
)
from exporter import update_dashboard_graphs, update_notion_database
from fetcher import get_canvas_data
from telegram_utils import escape_md, send_telegram

EXAM_KEYWORDS = ("exam", "test", "quiz", "midterm", "final")

# Plain-text only (no _ * ` [ ) so they're safe under Telegram Markdown v1.
BRAIN_TEASERS = [
    "Brain teaser: A farmer has 17 sheep and all but 9 run away. How many are left?",
    "Brain teaser: What has to be broken before you can use it?",
    "Brain teaser: I am tall when young and short when old. What am I?",
    "Brain teaser: What gets wetter the more it dries?",
    "Brain teaser: Forward I am heavy, backward I am not. What am I?",
    "Brain teaser: The more you take, the more you leave behind. What are they?",
    "Study check: Teach today's hardest concept to an imaginary 10-year-old. Where do you get stuck?",
    "Study check: Close your notes and write the 3 key points from your last reading.",
]


def log(msg):
    print(f"[BRIEFING] {msg}", file=sys.stderr)


def deliver(text: str, dry_run: bool, bot_token: str, chat_id: str) -> bool:
    """Send the message, or print it when dry-running."""
    if dry_run:
        print("\n----- DRY RUN MESSAGE -----")
        print(text)
        print("----- END DRY RUN -----\n")
        return True
    return send_telegram(bot_token, chat_id, text)


def build_quiz(courses: list) -> str:
    """A brain teaser or an active-recall prompt about a pending assignment.

    Shared by the midday briefing and the /quiz command.
    """
    today = datetime.now(timezone.utc).date()
    overdue, due_today, this_week, upcoming = bucket_assignments(courses, today)
    pending = overdue + due_today + this_week + upcoming

    use_assignment = pending and random.random() < 0.5
    if use_assignment:
        pick = random.choice(pending)
        prompts = [
            f'Without your notes: what is the main deliverable for *"{escape_md(pick["name"])}"*?',
            f'Explain the goal of *"{escape_md(pick["name"])}"* in one sentence.',
            f'What is the first step to finish *"{escape_md(pick["name"])}"*?',
        ]
        body = random.choice(prompts)
    else:
        body = escape_md(random.choice(BRAIN_TEASERS))

    return "\n".join([
        "🧠 *QUIZ TIME*",
        "",
        body,
        "",
        "_Think it through before you check._",
    ])


def _fetch_courses():
    """Return the courses list, or None after logging an error."""
    data = get_canvas_data()
    if "error" in data:
        log(f"Canvas fetch error: {data['error']}")
        return None
    return data.get("courses", [])


def run_morning(courses, today, dry_run, bot_token, chat_id):
    msg = build_telegram_message(courses, today)
    ann = build_announcements_section(courses)
    if ann:
        msg = msg + "\n" + "\n".join(ann)
    deliver(msg, dry_run, bot_token, chat_id)

    if dry_run:
        log("Dry run — skipping Notion sync and dashboard update.")
        return
    tasks = build_notion_tasks(courses, today)
    if tasks:
        update_notion_database(os.getenv("NOTION_TOKEN"), os.getenv("NOTION_DATABASE_ID"), tasks)
        update_dashboard_graphs(os.getenv("NOTION_TOKEN"), tasks)


def run_midday(courses, today, dry_run, bot_token, chat_id):
    lines = [f"☀️ *Midday Pulse — {fmt_date(today)}*", ""]
    ann = build_announcements_section(courses)
    if ann:
        lines += ann
    else:
        lines += ["No recent announcements.", ""]
    lines.append(build_quiz(courses))
    deliver("\n".join(lines), dry_run, bot_token, chat_id)


def run_evening(courses, today, dry_run, bot_token, chat_id):
    overdue, due_today, this_week, upcoming = bucket_assignments(courses, today)

    lines = [f"🌙 *Evening Review — {fmt_date(today)}*", ""]

    tomorrow = [e for e in this_week if (e["due"] - today).days == 1]
    if tomorrow:
        lines.append("🔔 *DUE TOMORROW*")
        for e in tomorrow:
            lines.append(f"• {escape_md(e['name'])} — {escape_md(short_course(e['course']))}")
        lines.append("")

    exams_soon = [
        e for e in (due_today + this_week)
        if any(k in e["name"].lower() for k in EXAM_KEYWORDS)
    ]
    if exams_soon:
        lines.append("📝 *EXAM / QUIZ PREP*")
        for e in exams_soon:
            lines.append(
                f"• {escape_md(e['name'])} — {escape_md(short_course(e['course']))}"
                f" _({fmt_date(e['due'])})_"
            )
        lines.append("")

    if not tomorrow and not exams_soon:
        lines += ["Nothing due tomorrow — good time to get ahead.", ""]

    lines += ["_Recall drill below if any cards are due._"]
    deliver("\n".join(lines), dry_run, bot_token, chat_id)

    # The spaced-rep drill sends its own Telegram message (and no-ops if the
    # Knowledge Base DB isn't configured). It cannot dry-run, so we skip it.
    if dry_run:
        log("Dry run — skipping spaced-rep recall drill.")
    else:
        spaced_rep_scheduler.main()


MODES = {
    "morning": run_morning,
    "midday": run_midday,
    "evening": run_evening,
}


def run(mode: str, dry_run: bool = False) -> bool:
    load_dotenv()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if mode not in MODES:
        log(f"Unknown mode: {mode}")
        return False

    courses = _fetch_courses()
    if courses is None:
        deliver("⚠️ Canvas fetch failed — could not build briefing.", dry_run, bot_token, chat_id)
        return False

    today = datetime.now(timezone.utc).date()
    log(f"Running '{mode}' briefing for {today} ({len(courses)} courses).")
    MODES[mode](courses, today, dry_run, bot_token, chat_id)
    log(f"'{mode}' briefing complete.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Canvas multi-mode briefing")
    parser.add_argument("--mode", required=True, choices=list(MODES.keys()))
    parser.add_argument("--dry-run", action="store_true", help="Print instead of send/write")
    args = parser.parse_args()
    ok = run(args.mode, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
