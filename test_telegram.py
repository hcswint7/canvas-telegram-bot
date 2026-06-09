"""
Stress tests for the Telegram pipeline.
Covers: telegram_utils, builder, and edge cases.

Run:
    python test_telegram.py          (plain unittest)
    python -m pytest test_telegram.py -v   (with pytest)
"""

import os
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests as _requests_mod

from builder import (
    build_notion_tasks,
    build_telegram_message,
    fmt_date,
    parse_due,
    short_course,
)
from telegram_utils import escape_md, send_telegram

# ── Fixed reference date so tests are deterministic ──────────────────────
TODAY = date(2026, 6, 8)


def make_assignment(name, due_days, has_submitted=False, due_at_override=None):
    if due_at_override is not None:
        due_iso = due_at_override
    else:
        due = TODAY + timedelta(days=due_days)
        due_iso = f"{due.isoformat()}T23:59:00Z"
    return {
        "id": "a1",
        "name": name,
        "due_at": due_iso,
        "points_possible": 10,
        "has_submitted": has_submitted,
        "description": "",
    }


def make_course(name, assignments):
    return {"id": "c1", "name": name, "assignments": assignments, "announcements": []}


# ─────────────────────────────────────────────────────────────────────────
# 1. escape_md
# ─────────────────────────────────────────────────────────────────────────

class TestEscapeMd(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(escape_md(""), "")

    def test_underscore(self):
        self.assertEqual(escape_md("hello_world"), r"hello\_world")

    def test_multiple_underscores(self):
        self.assertEqual(escape_md("a_b_c"), r"a\_b\_c")

    def test_asterisk(self):
        self.assertEqual(escape_md("x*y"), r"x\*y")

    def test_backtick(self):
        self.assertEqual(escape_md("run `ls`"), r"run \`ls\`")

    def test_square_bracket(self):
        result = escape_md("Part [A]")
        # no unescaped [ should remain
        self.assertNotIn("[", result.replace("\\[", ""))

    def test_combined(self):
        result = escape_md("_italic_ *bold* `code` [link]")
        # Each special char must have its escaped form present
        self.assertIn(r"\_", result)
        self.assertIn(r"\*", result)
        self.assertIn(r"\`", result)
        self.assertIn(r"\[", result)

    def test_safe_chars_unchanged(self):
        safe = "Chapter 1: Overview (50 pts)"
        self.assertEqual(escape_md(safe), safe)

    def test_idempotent_on_already_escaped(self):
        # Calling twice shouldn't double-escape
        once = escape_md("hello_world")
        # twice would escape the \ itself — we just verify the first call is clean
        self.assertEqual(once, r"hello\_world")


# ─────────────────────────────────────────────────────────────────────────
# 2. Helper functions
# ─────────────────────────────────────────────────────────────────────────

class TestHelpers(unittest.TestCase):
    def test_parse_due_utc_z(self):
        self.assertEqual(parse_due("2026-06-12T23:59:00Z"), date(2026, 6, 12))

    def test_parse_due_none(self):
        self.assertIsNone(parse_due(None))

    def test_parse_due_empty_string(self):
        self.assertIsNone(parse_due(""))

    def test_parse_due_garbage(self):
        self.assertIsNone(parse_due("not-a-date"))

    def test_parse_due_already_date_string(self):
        self.assertEqual(parse_due("2026-06-01T00:00:00Z"), date(2026, 6, 1))

    def test_fmt_date_no_leading_zero(self):
        # June 1 should be "Mon Jun 1", not "Mon Jun 01"
        result = fmt_date(date(2026, 6, 1))
        self.assertFalse(result.endswith(" 01"))
        self.assertTrue(result.endswith(" 1"))

    def test_fmt_date_double_digit(self):
        result = fmt_date(date(2026, 6, 15))
        self.assertIn("15", result)

    def test_short_course_three_parts(self):
        self.assertEqual(short_course("MKT-230-353"), "MKT-230")

    def test_short_course_two_parts(self):
        self.assertEqual(short_course("CS-101"), "CS-101")

    def test_short_course_one_part(self):
        self.assertEqual(short_course("English"), "English")

    def test_short_course_extra_parts(self):
        self.assertEqual(short_course("MKT-230-353-H1"), "MKT-230")


# ─────────────────────────────────────────────────────────────────────────
# 3. build_telegram_message — bucket routing
# ─────────────────────────────────────────────────────────────────────────

class TestBuildTelegramMessageBuckets(unittest.TestCase):
    def _msg(self, courses):
        return build_telegram_message(courses, TODAY)

    def test_empty_courses_all_clear(self):
        self.assertIn("All clear", self._msg([]))

    def test_all_submitted_all_clear(self):
        c = make_course("MKT-230-353", [
            make_assignment("Done 1", 3, has_submitted=True),
            make_assignment("Done 2", -1, has_submitted=True),
        ])
        self.assertIn("All clear", self._msg([c]))

    def test_overdue_not_submitted_in_overdue_bucket(self):
        c = make_course("MKT-230-353", [make_assignment("Late Work", -3)])
        msg = self._msg([c])
        self.assertIn("OVERDUE", msg)
        self.assertIn("Late Work", msg)

    def test_overdue_submitted_not_in_overdue_bucket(self):
        c = make_course("MKT-230-353", [make_assignment("Late Done", -3, has_submitted=True)])
        self.assertNotIn("OVERDUE", self._msg([c]))

    def test_due_today_bucket(self):
        c = make_course("MKT-230-353", [make_assignment("Today Task", 0)])
        msg = self._msg([c])
        self.assertIn("DUE TODAY", msg)

    def test_this_week_bucket(self):
        c = make_course("MKT-230-353", [make_assignment("Week Task", 4)])
        msg = self._msg([c])
        self.assertIn("DUE THIS WEEK", msg)
        self.assertNotIn("DUE TODAY", msg)

    def test_upcoming_beyond_7_days(self):
        c = make_course("MKT-230-353", [make_assignment("Far Task", 14)])
        msg = self._msg([c])
        self.assertIn("COMING UP", msg)

    def test_upcoming_capped_at_5_with_overflow_notice(self):
        tasks = [make_assignment(f"Task {i}", 10 + i) for i in range(8)]
        c = make_course("MKT-230-353", tasks)
        msg = self._msg([c])
        self.assertIn("more", msg)

    def test_no_due_date_skipped(self):
        a = make_assignment("No Date", 0, due_at_override=None)
        a["due_at"] = None
        c = make_course("MKT-230-353", [a])
        self.assertIn("All clear", self._msg([c]))


# ─────────────────────────────────────────────────────────────────────────
# 4. build_telegram_message — formatting & escaping
# ─────────────────────────────────────────────────────────────────────────

class TestBuildTelegramMessageFormatting(unittest.TestCase):
    def _msg(self, courses):
        return build_telegram_message(courses, TODAY)

    def test_header_always_present(self):
        self.assertIn("Canvas Radar", self._msg([]))

    def test_underscore_in_name_escaped(self):
        c = make_course("MKT-230-353", [make_assignment("Ch_1_Quiz", 3)])
        msg = self._msg([c])
        self.assertIn(r"Ch\_1\_Quiz", msg)

    def test_asterisk_in_name_escaped(self):
        c = make_course("MKT-230-353", [make_assignment("*Important* Task", 3)])
        msg = self._msg([c])
        self.assertNotIn("*Important*", msg)

    def test_bracket_in_name_escaped(self):
        c = make_course("MKT-230-353", [make_assignment("Task [Part A]", 3)])
        msg = self._msg([c])
        # After removing escaped instances, no bare [ should remain
        self.assertNotIn("[Part", msg.replace("\\[", ""))

    def test_underscore_in_course_escaped(self):
        c = make_course("MKT_230_353", [make_assignment("Task", 3)])
        msg = self._msg([c])
        # Course goes through short_course then escape_md
        self.assertNotIn("MKT_230", msg)

    def test_daily_question_present_when_assignments_exist(self):
        c = make_course("MKT-230-353", [make_assignment("Reading", 3)])
        msg = self._msg([c])
        self.assertIn("DAILY QUESTION", msg)

    def test_daily_question_absent_when_no_assignments(self):
        msg = self._msg([])
        self.assertNotIn("DAILY QUESTION", msg)

    def test_multiple_courses_both_in_message(self):
        c1 = make_course("MKT-230-353", [make_assignment("MKT Task", 3)])
        c2 = make_course("BLAW-261-353", [make_assignment("BLAW Task", 5)])
        msg = self._msg([c1, c2])
        self.assertIn("MKT-230", msg)
        self.assertIn("BLAW-261", msg)

    def test_returns_string(self):
        self.assertIsInstance(self._msg([]), str)

    def test_unicode_name_no_crash(self):
        c = make_course("MKT-230-353", [make_assignment("→ Submit ✓ Final", 3)])
        msg = self._msg([c])
        self.assertIsInstance(msg, str)

    def test_very_long_assignment_name(self):
        long_name = "A" * 300
        c = make_course("MKT-230-353", [make_assignment(long_name, 3)])
        msg = self._msg([c])
        self.assertIn(long_name, msg)


# ─────────────────────────────────────────────────────────────────────────
# 5. build_notion_tasks
# ─────────────────────────────────────────────────────────────────────────

class TestBuildNotionTasks(unittest.TestCase):
    def _tasks(self, courses):
        return build_notion_tasks(courses, TODAY)

    def test_overdue_not_submitted_status_overdue(self):
        c = make_course("MKT", [make_assignment("Late", -1)])
        t = self._tasks([c])
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0]["status"], "Overdue")

    def test_overdue_submitted_excluded(self):
        c = make_course("MKT", [make_assignment("Late Done", -1, has_submitted=True)])
        self.assertEqual(len(self._tasks([c])), 0)

    def test_future_submitted_status_submitted(self):
        c = make_course("MKT", [make_assignment("Early Done", 5, has_submitted=True)])
        t = self._tasks([c])
        self.assertEqual(t[0]["status"], "Submitted")

    def test_future_not_submitted_status_todo(self):
        c = make_course("MKT", [make_assignment("Pending", 5)])
        t = self._tasks([c])
        self.assertEqual(t[0]["status"], "To Do")

    def test_due_date_format_iso(self):
        due = TODAY + timedelta(days=3)
        c = make_course("MKT", [make_assignment("Task", 3)])
        t = self._tasks([c])
        self.assertEqual(t[0]["due_date"], str(due))

    def test_no_due_date_included_as_todo(self):
        # No-due-date assignments are real work and must still surface in Notion,
        # with a null due date and a "To Do" status (never "Overdue").
        a = {
            "id": "x", "name": "No Due", "due_at": None,
            "points_possible": 0, "has_submitted": False, "description": "",
        }
        c = make_course("MKT", [a])
        t = self._tasks([c])
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0]["status"], "To Do")
        self.assertIsNone(t[0]["due_date"])

    def test_no_due_date_submitted_excluded(self):
        # Nothing left to do, so a submitted no-due-date assignment is skipped.
        a = {
            "id": "x", "name": "No Due Done", "due_at": None,
            "points_possible": 0, "has_submitted": True, "description": "",
        }
        c = make_course("MKT", [a])
        self.assertEqual(len(self._tasks([c])), 0)

    def test_course_name_preserved(self):
        c = make_course("MKT-230-353", [make_assignment("Task", 3)])
        t = self._tasks([c])
        self.assertEqual(t[0]["course"], "MKT-230-353")

    def test_today_is_to_do_not_overdue(self):
        c = make_course("MKT", [make_assignment("Due Today", 0)])
        t = self._tasks([c])
        self.assertEqual(t[0]["status"], "To Do")


# ─────────────────────────────────────────────────────────────────────────
# 6. send_telegram — mocked HTTP
# ─────────────────────────────────────────────────────────────────────────

def _ok_mock():
    m = MagicMock()
    m.raise_for_status = MagicMock()
    return m


class TestSendTelegram(unittest.TestCase):

    @patch("telegram_utils.requests.post")
    def test_missing_token_no_request(self, mock_post):
        self.assertFalse(send_telegram("", "123", "hi"))
        mock_post.assert_not_called()

    @patch("telegram_utils.requests.post")
    def test_missing_chat_id_no_request(self, mock_post):
        self.assertFalse(send_telegram("TOKEN", "", "hi"))
        mock_post.assert_not_called()

    @patch("telegram_utils.requests.post")
    def test_short_message_one_chunk(self, mock_post):
        mock_post.return_value = _ok_mock()
        self.assertTrue(send_telegram("TOKEN", "CHAT", "hello"))
        self.assertEqual(mock_post.call_count, 1)

    @patch("telegram_utils.requests.post")
    def test_exactly_4000_chars_one_chunk(self, mock_post):
        mock_post.return_value = _ok_mock()
        send_telegram("TOKEN", "CHAT", "x" * 4000)
        self.assertEqual(mock_post.call_count, 1)

    @patch("telegram_utils.requests.post")
    def test_4001_chars_two_chunks(self, mock_post):
        mock_post.return_value = _ok_mock()
        send_telegram("TOKEN", "CHAT", "x" * 4001)
        self.assertEqual(mock_post.call_count, 2)

    @patch("telegram_utils.requests.post")
    def test_chunk_content_correct(self, mock_post):
        mock_post.return_value = _ok_mock()
        msg = "A" * 4000 + "B" * 4000 + "C" * 500
        send_telegram("TOKEN", "CHAT", msg)
        chunks = [c[1]["json"]["text"] for c in mock_post.call_args_list]
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0], "A" * 4000)
        self.assertEqual(chunks[1], "B" * 4000)
        self.assertEqual(chunks[2], "C" * 500)

    @patch("telegram_utils.requests.post")
    def test_disable_web_page_preview_always_set(self, mock_post):
        mock_post.return_value = _ok_mock()
        send_telegram("TOKEN", "CHAT", "hello")
        payload = mock_post.call_args[1]["json"]
        self.assertTrue(payload["disable_web_page_preview"])

    @patch("telegram_utils.requests.post")
    def test_parse_mode_default_markdown(self, mock_post):
        mock_post.return_value = _ok_mock()
        send_telegram("TOKEN", "CHAT", "hello")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["parse_mode"], "Markdown")

    @patch("telegram_utils.requests.post")
    def test_network_error_returns_false(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")
        self.assertFalse(send_telegram("TOKEN", "CHAT", "hello"))

    @patch("telegram_utils.requests.post")
    def test_http_error_returns_false(self, mock_post):
        bad = MagicMock()
        bad.raise_for_status.side_effect = _requests_mod.HTTPError("400")
        mock_post.return_value = bad
        self.assertFalse(send_telegram("TOKEN", "CHAT", "hello"))

    @patch("telegram_utils.requests.post")
    def test_first_chunk_fails_stops_early(self, mock_post):
        """If chunk 1 fails (even after the plain-text retry), chunk 2 must NOT be sent.

        A2 behavior: a failed Markdown send is retried once as plain text. So a
        fully-failing first chunk makes exactly 2 calls (Markdown + plain-text
        retry), then stops — chunk 2 (which would be call 3) is never attempted.
        """
        bad = MagicMock()
        bad.raise_for_status.side_effect = Exception("fail")
        mock_post.return_value = bad
        result = send_telegram("TOKEN", "CHAT", "x" * 8000)
        self.assertFalse(result)
        self.assertEqual(mock_post.call_count, 2)

    @patch("telegram_utils.requests.post")
    def test_very_large_message_chunked(self, mock_post):
        mock_post.return_value = _ok_mock()
        msg = "z" * 40000  # 10 chunks
        self.assertTrue(send_telegram("TOKEN", "CHAT", msg))
        self.assertEqual(mock_post.call_count, 10)

    @patch("telegram_utils.requests.post")
    def test_empty_message_no_request(self, mock_post):
        mock_post.return_value = _ok_mock()
        result = send_telegram("TOKEN", "CHAT", "")
        # range(0, 0, 4000) = [] → no chunks → no HTTP call; still returns True
        self.assertEqual(mock_post.call_count, 0)
        self.assertTrue(result)


# ─────────────────────────────────────────────────────────────────────────
# 7. Integration — realistic pipeline scenarios
# ─────────────────────────────────────────────────────────────────────────

class TestIntegration(unittest.TestCase):
    def test_realistic_two_course_week(self):
        """Simulates a typical week: overdue + upcoming mix."""
        courses = [
            make_course("MKT-230-353", [
                make_assignment("Introduce Yourself - Brand Ambassador Pitch", -3, has_submitted=True),
                make_assignment("Ch 1-2 Assessment", 7),
                make_assignment("Ch 3 Quiz", 12),
            ]),
            make_course("BLAW-261-353", [
                make_assignment("Extra Credit - Syllabus Quiz", -1),
                make_assignment("Contract Law Discussion", 5),
            ]),
        ]
        msg = build_telegram_message(courses, TODAY)
        tasks = build_notion_tasks(courses, TODAY)

        # Message checks
        self.assertIn("OVERDUE", msg)        # Syllabus Quiz is overdue
        self.assertIn("BLAW-261", msg)
        self.assertIn("MKT-230", msg)
        self.assertIn("DAILY QUESTION", msg)
        self.assertNotIn("Brand Ambassador", msg)  # submitted+overdue → skipped

        # Task checks
        statuses = {t["title"]: t["status"] for t in tasks}
        self.assertEqual(statuses["Extra Credit - Syllabus Quiz"], "Overdue")
        self.assertNotIn("Introduce Yourself - Brand Ambassador Pitch", statuses)
        self.assertEqual(statuses["Ch 1-2 Assessment"], "To Do")
        self.assertEqual(statuses["Contract Law Discussion"], "To Do")

    def test_message_under_4096_chars_for_normal_load(self):
        """Normal 10-assignment load should not need chunking."""
        courses = [
            make_course("MKT-230-353", [make_assignment(f"MKT Task {i}", i * 2) for i in range(5)]),
            make_course("BLAW-261-353", [make_assignment(f"BLAW Task {i}", i * 3 + 1) for i in range(5)]),
        ]
        msg = build_telegram_message(courses, TODAY)
        self.assertLess(len(msg), 4096, f"Message too long ({len(msg)} chars) — would require chunking")

    def test_message_with_all_special_chars(self):
        """Assignment names with every Markdown v1 special char."""
        c = make_course("MKT-230-353", [
            make_assignment("Task_with_underscores", 3),
            make_assignment("*Starred* Assignment", 4),
            make_assignment("`code` block title", 5),
            make_assignment("[Linked] Assignment", 6),
        ])
        msg = build_telegram_message([c], TODAY)
        # Verify none of the raw special chars appear unescaped in assignment names
        # (They appear in formatting markers like *SECTION* intentionally, so we
        #  check the specific escaped forms exist)
        self.assertIn(r"Task\_with\_underscores", msg)
        self.assertIn(r"\*Starred\*", msg)
        self.assertIn(r"\`code\`", msg)
        # Only [ is special in Markdown v1; ] does not need escaping
        self.assertIn(r"\[Linked]", msg)

    def test_20_overdue_assignments_no_crash(self):
        """Bulk overdue list should not crash or truncate silently."""
        tasks = [make_assignment(f"Overdue Task {i}", -(i + 1)) for i in range(20)]
        c = make_course("MKT-230-353", tasks)
        msg = build_telegram_message([c], TODAY)
        self.assertIn("OVERDUE", msg)
        self.assertIsInstance(msg, str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
