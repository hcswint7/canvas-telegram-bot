"""
organize_notes.py — weekly tidy-up of Course Notes pages.

For each chapter-note page it reads the "✍️ Notes" section (freeform bullets)
and COPIES — never moves or edits — anything that looks like a term/definition
into the "🔑 Key Terms" table, and anything that looks like an example into a
"💡 Examples" section. The Notes section is left exactly as written.

Lightweight + free: pure heuristics (no LLM/API key), reuses notion-client.
Idempotent: dedupes against terms/examples already present, so running it every
week only ever adds genuinely new items.

Run:  python organize_notes.py            # organize all notes
      python organize_notes.py --dry-run  # report only, write nothing

Needs env: NOTION_TOKEN, NOTION_NOTES_DB_ID (the Course Notes database id).
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from notion_client import Client

TERM_SEPARATORS = (" — ", " – ", " - ", ": ", " = ")

# Generic words that are never a real term (avoid "Definition: ...", etc.).
TERM_BLACKLIST = {
    "definition", "def", "example", "examples", "ex", "note", "notes",
    "summary", "prompt", "prompts", "term", "terms", "concept", "concepts",
    "main idea", "supporting detail", "idea", "key term", "key terms",
}
# Lowercase sentence-starters / verbs — a "term" beginning with one of these is
# almost always a sentence fragment, not a real term.
STOP_STARTS = {
    "the", "a", "an", "if", "this", "these", "that", "those", "when", "due",
    "it", "there", "each", "both", "every", "involves", "structures",
    "created", "today", "authorities", "made", "concerns", "where", "which",
    "his", "her", "their", "they", "we", "you", "i",
}


def log(msg):
    print(f"[ORGANIZE] {msg}", file=sys.stderr)


def rt_text(rich):
    return "".join(x.get("plain_text", "") for x in (rich or []))


def list_children(notion, block_id):
    out, cursor = [], None
    while True:
        resp = notion.blocks.children.list(block_id=block_id, start_cursor=cursor) if cursor \
            else notion.blocks.children.list(block_id=block_id)
        out.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return out


def classify(line: str):
    """Return ('term',(term,defn)) | ('example',text) | None for one note line.

    Conservative on purpose: only high-confidence "Term: definition" lines and
    explicitly-flagged examples are pulled, so the student's notes never get
    polluted with sentence fragments. Missing a few > inventing junk.
    """
    l = line.strip().lstrip("-*•").strip()
    if len(l) < 5:
        return None
    low = l.lower()
    # Examples: only when explicitly flagged at the start or by a clear marker.
    if (low.startswith(("ex.", "ex:", "e.g.", "eg."))
            or "for example" in low or "for instance" in low or "e.g." in low):
        return ("example", l)
    # Terms: one explicit separator, short Title-case head, real definition.
    for sep in TERM_SEPARATORS:
        if sep in l:
            term, defn = l.split(sep, 1)
            term, defn = term.strip(), defn.strip()
            words = term.split()
            if not (1 <= len(words) <= 4) or len(defn) < 8:
                return None
            if term.lower() in TERM_BLACKLIST or words[0].lower() in STOP_STARTS:
                return None
            if not term[0].isalpha() or not term[0].isupper():
                return None
            if term.endswith((",", ".", "?", ";", ":")):
                return None
            return ("term", (term, defn))
    return None


def collect_notes_lines(blocks):
    """Plain-text lines under the '✍️ Notes' heading, up to the next H1 section."""
    lines, in_notes = [], False
    for b in blocks:
        t = b["type"]
        if t == "heading_1":
            txt = rt_text(b["heading_1"]["rich_text"]).lower()
            if "notes" in txt and "self" not in txt:   # the Notes section
                in_notes = True
                continue
            if in_notes:                                # next H1 ends Notes
                break
        if in_notes and t in ("bulleted_list_item", "numbered_list_item",
                              "paragraph", "to_do"):
            lines.append(rt_text(b[t]["rich_text"]))
    return [ln for ln in lines if ln.strip()]


def find_table(blocks):
    for b in blocks:
        if b["type"] == "table":
            return b["id"], b["table"].get("table_width", 2)
    return None, 0


def existing_terms(notion, table_id):
    terms = set()
    for row in list_children(notion, table_id):
        if row["type"] == "table_row":
            cells = row["table_row"]["cells"]
            if cells:
                terms.add(rt_text(cells[0]).strip().lower())
    return terms


def find_examples_section(blocks):
    """Return (heading_present, set_of_existing_example_texts)."""
    present, in_ex, texts = False, False, set()
    for b in blocks:
        t = b["type"]
        if t in ("heading_1", "heading_2"):
            htxt = rt_text(b[t]["rich_text"]).lower()
            if "example" in htxt:
                present, in_ex = True, True
                continue
            if in_ex:
                in_ex = False
        if in_ex and t == "bulleted_list_item":
            texts.add(rt_text(b["bulleted_list_item"]["rich_text"]).strip().lower())
    return present, texts


def cell(text):
    return [{"type": "text", "text": {"content": text[:1800]}}]


def organize_page(notion, page, dry_run):
    pid = page["id"]
    title = ""
    for v in page["properties"].values():
        if v.get("type") == "title" and v.get("title"):
            title = v["title"][0].get("plain_text", "")
            break
    if "template" in title.lower():
        return (0, 0)

    blocks = list_children(notion, pid)
    note_lines = collect_notes_lines(blocks)
    if not note_lines:
        return (0, 0)

    table_id, width = find_table(blocks)
    have_terms = existing_terms(notion, table_id) if table_id else set()
    ex_present, have_ex = find_examples_section(blocks)

    new_terms, new_examples = [], []
    seen_t, seen_e = set(), set()
    for ln in note_lines:
        c = classify(ln)
        if not c:
            continue
        if c[0] == "term":
            term, defn = c[1]
            key = term.lower()
            if key not in have_terms and key not in seen_t:
                seen_t.add(key)
                new_terms.append((term, defn))
        else:
            txt = c[1]
            key = txt.lower()
            if key not in have_ex and key not in seen_e:
                seen_e.add(key)
                new_examples.append(txt)

    if dry_run:
        if new_terms or new_examples:
            log(f"[dry] {title[:40]!r}: +{len(new_terms)} terms, +{len(new_examples)} examples")
        return (len(new_terms), len(new_examples))

    # Append new term rows to the Key Terms table (fallback: bullets).
    if new_terms:
        if table_id:
            children = [{"object": "block", "type": "table_row",
                         "table_row": {"cells": [cell(t), cell(d)] +
                                       [cell("")] * max(0, width - 2)}}
                        for t, d in new_terms]
            notion.blocks.children.append(block_id=table_id, children=children)
        else:
            kids = [{"object": "block", "type": "heading_1",
                     "heading_1": {"rich_text": cell("🔑 Key Terms")}}]
            kids += [{"object": "block", "type": "bulleted_list_item",
                      "bulleted_list_item": {"rich_text": cell(f"{t} — {d}")}}
                     for t, d in new_terms]
            notion.blocks.children.append(block_id=pid, children=kids)

    # Append new examples under a "💡 Examples" section (create heading once).
    if new_examples:
        kids = []
        if not ex_present:
            kids.append({"object": "block", "type": "heading_1",
                         "heading_1": {"rich_text": cell("💡 Examples")}})
        kids += [{"object": "block", "type": "bulleted_list_item",
                  "bulleted_list_item": {"rich_text": cell(x)}} for x in new_examples]
        notion.blocks.children.append(block_id=pid, children=kids)

    if new_terms or new_examples:
        log(f"{title[:40]!r}: +{len(new_terms)} terms, +{len(new_examples)} examples")
    return (len(new_terms), len(new_examples))


def main():
    ap = argparse.ArgumentParser(description="Weekly Course Notes organizer")
    ap.add_argument("--dry-run", action="store_true", help="Report only; write nothing")
    args = ap.parse_args()

    load_dotenv()
    token = os.getenv("NOTION_TOKEN")
    db_id = os.getenv("NOTION_NOTES_DB_ID")
    if not token or not db_id:
        log("Missing NOTION_TOKEN or NOTION_NOTES_DB_ID.")
        sys.exit(1)

    notion = Client(auth=token)
    pages, cursor = [], None
    while True:
        resp = notion.databases.query(database_id=db_id, start_cursor=cursor) if cursor \
            else notion.databases.query(database_id=db_id)
        pages.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    tot_t = tot_e = 0
    for p in pages:
        try:
            t, e = organize_page(notion, p, args.dry_run)
            tot_t += t
            tot_e += e
        except Exception as ex:
            log(f"Error on a page: {ex}")
    verb = "Would add" if args.dry_run else "Added"
    log(f"Done. {verb} {tot_t} terms, {tot_e} examples across {len(pages)} notes.")


if __name__ == "__main__":
    main()
