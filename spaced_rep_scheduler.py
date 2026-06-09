import os
import random
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from notion_client import Client

from telegram_utils import escape_md, send_telegram


def log(msg):
    print(f"[SPACED_REP] {msg}", file=sys.stderr)


RECALL_PROMPTS = [
    "Without your notes: explain {}.",
    "Core idea of {} — say it in plain English.",
    "Give a real-world example of {}.",
    "What's the most important thing to remember about {}?",
    "How would you apply {} in a real situation?",
]


def recall_question(topic: str) -> str:
    return random.choice(RECALL_PROMPTS).format(f'*"{escape_md(topic)}"*')


def get_course_name(notion, course_id: str, cache: dict) -> str:
    """Fetch course name with a local cache to avoid N+1 Notion calls."""
    if course_id in cache:
        return cache[course_id]
    try:
        page = notion.pages.retrieve(page_id=course_id)
        title_prop = page.get("properties", {}).get("Course Name", {})
        if title_prop.get("type") == "title" and title_prop.get("title"):
            name = title_prop["title"][0].get("plain_text", "General")
        else:
            name = "General"
    except Exception:
        name = "General"
    cache[course_id] = name
    return name


def main():
    load_dotenv()

    notion_token = os.getenv("NOTION_TOKEN")
    kb_db_id = os.getenv("NOTION_KB_DB_ID")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not notion_token or not kb_db_id:
        log("Notion credentials or KB_DB_ID missing. Skipping.")
        return

    notion = Client(auth=notion_token)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log(f"Checking spaced repetition reviews due on or before {today_str}...")

    try:
        results = notion.databases.query(
            database_id=kb_db_id,
            filter={
                "and": [
                    {
                        "property": "Status",
                        "select": {"does_not_equal": "Mastered"},
                    },
                    {
                        "or": [
                            {
                                "property": "Next Review Date",
                                "date": {"on_or_before": today_str},
                            },
                            {
                                "property": "Next Review Date",
                                "date": {"is_empty": True},
                            },
                        ]
                    },
                ]
            },
        )
    except Exception as e:
        log(f"Error querying Knowledge Base: {e}")
        return

    cards = results.get("results", [])
    log(f"Found {len(cards)} cards due for review today.")

    if not cards:
        log("No active recall reviews due today.")
        return

    course_cache: dict = {}

    lines = [
        "🧠 *ACTIVE RECALL DRILL*",
        "_Test yourself before opening each card._",
        "",
    ]

    for idx, card in enumerate(cards, 1):
        props = card.get("properties", {})

        # Extract title
        topic = "Untitled Topic"
        for v in props.values():
            if v.get("type") == "title" and v.get("title"):
                topic = v["title"][0].get("plain_text", topic)
                break

        # Resolve course name (cached)
        course_text = "General"
        course_prop = props.get("Course", {})
        if course_prop.get("type") == "relation":
            relations = course_prop.get("relation", [])
            if relations:
                course_text = get_course_name(notion, relations[0]["id"], course_cache)

        card_id = card["id"].replace("-", "")
        notion_url = f"https://notion.so/{card_id}"

        lines.append(f"{idx}\\. *{escape_md(topic)}* — {escape_md(course_text)}")
        lines.append(f"   💭 _{recall_question(topic)}_")
        lines.append(f"   👉 [Review card]({notion_url})")
        lines.append("")

        # Stay well under Telegram's 4096-char limit; leave room for the footer
        if len("\n".join(lines)) > 3600:
            remaining = len(cards) - idx
            if remaining > 0:
                lines.append(f"_...and {remaining} more card(s) — open Notion to review all._")
            break

    lines += [
        "─────────────────────",
        "Rate your recall \\(1-5\\) inside each card to update review intervals\\.",
    ]

    send_telegram(bot_token, chat_id, "\n".join(lines))


if __name__ == "__main__":
    main()
