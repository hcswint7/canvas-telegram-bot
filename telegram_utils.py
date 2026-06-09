import re
import sys
import requests


def strip_md(text: str) -> str:
    """Remove Markdown formatting so the message can be sent as plain text."""
    # Convert [label](url) links into "label url" so they stay readable.
    text = re.sub(r"\[([^\]]*)\]\((https?://[^)]+)\)", r"\1 \2", text)
    return (
        text
        .replace("*", "")
        .replace("_", "")
        .replace("`", "")
        .replace("[", "")
        .replace("]", "")
        .replace("\\", "")
    )


def link_suffix(url: str) -> str:
    """A clickable 🔗 link to append after an item, or '' if no URL.

    Uses a separate icon (not the item name) as the link text so a messy
    assignment title can never break the Markdown link.
    """
    return f" [🔗]({url})" if url else ""


def escape_md(text: str) -> str:
    """Escape special chars for Telegram Markdown v1: _ * ` ["""
    return (
        text
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("`", "\\`")
        .replace("[", "\\[")
    )


def send_telegram(bot_token: str, chat_id: str, text: str,
                  parse_mode: str = "Markdown") -> bool:
    """Send a Telegram message, chunking if over 4000 chars.

    Returns True if all chunks sent successfully.
    """
    if not bot_token or not chat_id:
        print("[TELEGRAM] Missing credentials — skipping.", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=10)
            r.raise_for_status()
        except Exception as e:
            # A2: If Markdown formatting caused a parse error, retry as plain text.
            if parse_mode != "":
                print(f"[TELEGRAM] Markdown send failed ({e}), retrying as plain text.",
                      file=sys.stderr)
                plain_payload = {**payload, "text": strip_md(chunk), "parse_mode": ""}
                try:
                    r2 = requests.post(url, json=plain_payload, timeout=10)
                    r2.raise_for_status()
                except Exception as e2:
                    print(f"[TELEGRAM] Plain-text retry also failed: {e2}", file=sys.stderr)
                    return False
            else:
                print(f"[TELEGRAM] Send failed: {e}", file=sys.stderr)
                return False

    return True
