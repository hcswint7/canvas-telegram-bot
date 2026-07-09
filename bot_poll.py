"""
bot_poll.py — inbound Telegram command handler (two-way control).

Pure `requests` long-polling, no new dependencies. Designed to be invoked
statelessly from GitHub Actions every few minutes:

    python bot_poll.py --once     # drain pending updates, act, ack, exit (Actions)
    python bot_poll.py --loop     # continuous long-poll (local always-on use)

Stateless offset trick: after handling a batch we call getUpdates again with
offset = last_update_id + 1, which tells Telegram to drop those updates so the
next run won't see them again — no offset file to persist across runs.

Security: every update is checked against TELEGRAM_CHAT_ID; anything from any
other chat is ignored, so only the owner can drive the bot.

Commands: /sync /today /week /done <name> /check /quiz /help
"""

import argparse
import difflib
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Chicago")

import requests
from dotenv import load_dotenv
from notion_client import Client

import run_briefing
from builder import build_telegram_message, short_course
from fetcher import get_canvas_data, get_canvas_inbox
from telegram_utils import escape_md, send_telegram

SUBMITTED_STATUS = "Submitted"

HELP_TEXT = "\n".join([
    "🤖 *Canvas Bot — Commands*",
    "",
    "/sync — re-fetch Canvas, update Notion, send a fresh radar",
    "/today — what's due today (plus overdue)",
    "/week — what's due in the next 7 days",
    "/done <name> — mark an assignment Submitted in Notion",
    "/check — Canvas inbox messages and announcements",
    "/quiz — a brain teaser or recall question",
    "/help — this list",
])


def log(msg):
    print(f"[BOT] {msg}", file=sys.stderr)


def api(token, method, params=None, timeout=20):
    url = f"https://api.telegram.org/bot{token}/{method}"
    r = requests.get(url, params=params or {}, timeout=timeout)
    r.raise_for_status()
    return r.json().get("result", [])


def reply(token, chat_id, text):
    send_telegram(token, chat_id, text)


# ── Command handlers ─────────────────────────────────────────────────────

def _radar(chat_scope):
    """Shared: fetch Canvas and render the compact radar at the given scope."""
    data = get_canvas_data()
    if "error" in data:
        return None
    today = datetime.now(LOCAL_TZ).date()
    return build_telegram_message(data.get("courses", []), today, scope=chat_scope)


def cmd_today(token, chat_id):
    msg = _radar("today")
    reply(token, chat_id, msg if msg else "⚠️ Canvas fetch failed.")


def cmd_week(token, chat_id):
    msg = _radar("week")
    reply(token, chat_id, msg if msg else "⚠️ Canvas fetch failed.")


def cmd_check(token, chat_id):
    lines = ["📬 *Inbox & Announcements*", ""]

    data = get_canvas_data()
    anns = []
    if "error" not in data:
        for course in data.get("courses", []):
            for ann in course.get("announcements", []):
                anns.append((ann.get("title") or "Untitled", course.get("name", "")))
    if anns:
        lines.append("📣 *Announcements*")
        for title, course in anns[:5]:
            lines.append(f"• {escape_md(title)} — {escape_md(short_course(course))}")
        lines.append("")

    inbox = get_canvas_inbox()
    msgs = [] if "error" in inbox else inbox.get("messages", [])
    if msgs:
        lines.append("✉️ *Canvas Inbox*")
        for m in msgs:
            mark = "🔵 " if m.get("unread") else ""
            lines.append(f"• {mark}{escape_md(m['subject'])}")
        lines.append("")
    elif "error" in inbox:
        lines.append("_Inbox check unavailable._")

    if not anns and not msgs:
        lines.append("Nothing new right now.")
    reply(token, chat_id, "\n".join(lines))


def cmd_quiz(token, chat_id):
    data = get_canvas_data()
    courses = data.get("courses", []) if "error" not in data else []
    reply(token, chat_id, run_briefing.build_quiz(courses))


def cmd_done(token, chat_id, query):
    query = query.strip()
    if not query:
        reply(token, chat_id, "Usage: /done <assignment name>")
        return

    notion_token = os.getenv("NOTION_TOKEN")
    db_id = os.getenv("NOTION_DATABASE_ID")
    if not notion_token or not db_id:
        reply(token, chat_id, "⚠️ Notion not configured.")
        return

    notion = Client(auth=notion_token)
    titles = {}  # title -> page_id
    cursor = None
    try:
        while True:
            payload = {"database_id": db_id}
            if cursor:
                payload["start_cursor"] = cursor
            res = notion.databases.query(**payload)
            for page in res.get("results", []):
                for v in page.get("properties", {}).values():
                    if v.get("type") == "title" and v.get("title"):
                        titles[v["title"][0].get("plain_text", "")] = page["id"]
                        break
            if not res.get("has_more"):
                break
            cursor = res.get("next_cursor")
    except Exception as e:
        log(f"/done query error: {e}")
        reply(token, chat_id, "⚠️ Couldn't read your Notion tasks.")
        return

    # Match: collect all substring matches; require an unambiguous target.
    q = query.lower()
    matches = [t for t in titles if q in t.lower()]
    if len(matches) > 1:
        shown = "\n".join(f"• {escape_md(m)}" for m in matches[:8])
        extra = "" if len(matches) <= 8 else f"\n_…and {len(matches) - 8} more_"
        reply(token, chat_id,
              f"🔎 {len(matches)} matches for *{escape_md(query)}* — be more specific:\n{shown}{extra}")
        return
    if len(matches) == 1:
        match = matches[0]
    else:
        close = difflib.get_close_matches(query, list(titles.keys()), n=3, cutoff=0.5)
        if not close:
            reply(token, chat_id, f"❓ No assignment matching *{escape_md(query)}* found.")
            return
        if len(close) > 1:
            shown = "\n".join(f"• {escape_md(m)}" for m in close)
            reply(token, chat_id, f"🤔 No exact match — did you mean:\n{shown}")
            return
        match = close[0]

    try:
        notion.pages.update(
            page_id=titles[match],
            properties={"Status": {"select": {"name": SUBMITTED_STATUS}}},
        )
        reply(token, chat_id, f"✅ Marked *{escape_md(match)}* as {SUBMITTED_STATUS}.")
    except Exception as e:
        log(f"/done update error: {e}")
        reply(token, chat_id, f"⚠️ Couldn't update *{escape_md(match)}*.")


def cmd_sync(token, chat_id):
    reply(token, chat_id, "🔄 Syncing Canvas → Notion + radar…")
    ok = run_briefing.run("morning", dry_run=False)
    if not ok:
        reply(token, chat_id, "⚠️ Sync hit an error — check the logs.")


# ── Dispatch ─────────────────────────────────────────────────────────────

def handle_update(update, token, owner_chat_id):
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat_id = str(msg.get("chat", {}).get("id", ""))
    if chat_id != str(owner_chat_id):
        log(f"Ignoring message from non-owner chat {chat_id}.")
        return

    text = (msg.get("text") or "").strip()
    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0].lstrip("/").split("@")[0].lower()  # strip /, @botname
    arg = parts[1] if len(parts) > 1 else ""

    log(f"Command: /{cmd} {arg!r}")
    if cmd == "sync":
        cmd_sync(token, chat_id)
    elif cmd == "today":
        cmd_today(token, chat_id)
    elif cmd == "week":
        cmd_week(token, chat_id)
    elif cmd == "done":
        cmd_done(token, chat_id, arg)
    elif cmd == "check":
        cmd_check(token, chat_id)
    elif cmd == "quiz":
        cmd_quiz(token, chat_id)
    elif cmd in ("help", "start"):
        reply(token, chat_id, HELP_TEXT)
    else:
        reply(token, chat_id, f"Unknown command /{escape_md(cmd)}. Try /help.")


def process_once(token, owner_chat_id, poll_timeout=0):
    updates = api(token, "getUpdates", {"timeout": poll_timeout}, timeout=poll_timeout + 20)
    if not updates:
        return 0
    last_id = max(u["update_id"] for u in updates)
    for u in updates:
        try:
            handle_update(u, token, owner_chat_id)
        except Exception as e:
            log(f"Error handling update {u.get('update_id')}: {e}")
    # Ack: confirm offset so these aren't returned again.
    api(token, "getUpdates", {"offset": last_id + 1, "timeout": 0}, timeout=20)
    return len(updates)


def main():
    parser = argparse.ArgumentParser(description="Telegram command poller")
    parser.add_argument("--once", action="store_true", help="Drain pending updates and exit")
    parser.add_argument("--loop", action="store_true", help="Continuous long-poll")
    args = parser.parse_args()

    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    owner_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not owner_chat_id:
        log("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        sys.exit(1)

    if args.loop:
        log("Starting continuous poll (Ctrl-C to stop).")
        while True:
            try:
                process_once(token, owner_chat_id, poll_timeout=30)
            except Exception as e:
                log(f"Poll error: {e}")
    else:
        try:
            n = process_once(token, owner_chat_id, poll_timeout=0)
            log(f"Processed {n} update(s).")
        except Exception as e:
            # Transient Telegram/network hiccup: log and exit clean so the
            # scheduled run doesn't show a spurious failure.
            log(f"Poll error (non-fatal): {e}")
            sys.exit(0)


if __name__ == "__main__":
    main()
