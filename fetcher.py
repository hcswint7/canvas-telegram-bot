import os
import sys
import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from canvasapi import Canvas
from canvasapi.exceptions import CanvasException

# Ensure all debug logging goes to stderr so stdout is strictly JSON
def log(msg):
    print(f"[FETCHER] {msg}", file=sys.stderr)

LOOKBACK_DAYS = 7    # include recently overdue assignments
LOOKAHEAD_DAYS = 90  # include assignments due within the next N days (~3 months)


def get_canvas_data():
    url = os.getenv("CANVAS_API_URL")
    token = os.getenv("CANVAS_API_TOKEN")

    if not url or not token:
        log("Canvas credentials missing.")
        return {"error": "Missing Canvas Credentials"}

    try:
        canvas = Canvas(url, token)
        me = canvas.get_current_user()
        log(f"Authenticated to Canvas as {me.name}")

        # Get active courses
        courses = canvas.get_courses(enrollment_state="active")

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=LOOKBACK_DAYS)
        window_end   = now + timedelta(days=LOOKAHEAD_DAYS)
        log(f"Assignment window: {window_start.date()} → {window_end.date()}")

        course_data = []
        for course in courses:
            # Some courses might not have a name or are restricted
            if not hasattr(course, 'name'):
                continue

            c_info = {
                "id": course.id,
                "name": course.name,
                "assignments": [],
                "announcements": []
            }

            log(f"Fetching assignments for {course.name}...")
            try:
                # No bucket filter — let Canvas return all assignments, then
                # restrict to the rolling window in Python for full date control.
                # include=["submission"] attaches THIS user's own submission so we
                # can tell if *they* submitted (has_submitted_submissions is a
                # course-wide teacher field and falsely marks work submitted).
                assignments = course.get_assignments(order_by="due_at", include=["submission"])
                for a in assignments:
                    due_str = getattr(a, "due_at", None)
                    if due_str:
                        # Dated assignment: keep only if it falls in the rolling window.
                        try:
                            due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                        except ValueError:
                            # Unparseable date string — treat like "no due date" rather
                            # than silently dropping a real assignment.
                            due_str = None
                        else:
                            if not (window_start <= due_dt <= window_end):
                                continue
                    # Did the CURRENT user submit? Use their own submission record:
                    # submitted_at is set once they hand it in; "graded" covers
                    # teacher-graded no-submission items. Anything else = not done.
                    sub = getattr(a, "submission", None) or {}
                    has_submitted = bool(sub.get("submitted_at")) or \
                        sub.get("workflow_state") in ("submitted", "graded", "pending_review")
                    # No due date (or unparseable): still real work the student must
                    # see, so surface it with due_at=None instead of dropping it.
                    c_info["assignments"].append({
                        "id": getattr(a, "id", None),
                        "name": getattr(a, "name", "Unnamed Assignment"),
                        "due_at": due_str,
                        "points_possible": getattr(a, "points_possible", None),
                        "has_submitted": has_submitted,
                        "description": getattr(a, "description", "")
                    })
                log(f"  → {len(c_info['assignments'])} assignments in window")
            except Exception as e:
                log(f"Could not fetch assignments for {course.name}: {e}")
                
            # Fetch recent announcements (last 14 days)
            try:
                two_weeks_ago = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
                # context_codes requires format like course_1234
                announcements = canvas.get_announcements(context_codes=[f"course_{course.id}"], start_date=two_weeks_ago)
                for ann in announcements:
                    c_info["announcements"].append({
                        "id": getattr(ann, "id", None),
                        "title": getattr(ann, "title", "No Title"),
                        "posted_at": getattr(ann, "posted_at", None),
                        "message": getattr(ann, "message", "")
                    })
            except Exception as e:
                log(f"Could not fetch announcements for {course.name}: {e}")
                
            course_data.append(c_info)
            
        return {"courses": course_data}
    except CanvasException as e:
        log(f"Canvas API Error: {e}")
        return {"error": str(e)}
    except Exception as e:
        log(f"Unexpected Canvas Error: {e}")
        return {"error": str(e)}

def get_canvas_inbox(limit=5):
    """Read the student's own Canvas inbox (Conversations API).

    Replaces the old Gmail/IMAP check — same Canvas messages, straight from
    the source, using the Canvas token we already have (no Gmail app password
    or 2FA needed). Returns the most recent conversations, newest first.
    """
    url = os.getenv("CANVAS_API_URL")
    token = os.getenv("CANVAS_API_TOKEN")

    if not url or not token:
        log("Canvas credentials missing.")
        return {"error": "Missing Canvas Credentials"}

    try:
        canvas = Canvas(url, token)
        # get_conversations() returns most-recent-first; stop after `limit`
        # so we don't page through the entire mailbox.
        messages = []
        for conv in canvas.get_conversations():
            messages.append({
                "subject": getattr(conv, "subject", None) or "(no subject)",
                "last_message": (getattr(conv, "last_message", "") or "")[:300],
                "last_message_at": getattr(conv, "last_message_at", None),
                "unread": getattr(conv, "workflow_state", "") == "unread",
            })
            if len(messages) >= limit:
                break
        return {"messages": messages}
    except CanvasException as e:
        log(f"Canvas inbox API error: {e}")
        return {"error": str(e)}
    except Exception as e:
        log(f"Unexpected Canvas inbox error: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    load_dotenv()

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "canvas": get_canvas_data(),
        "inbox": get_canvas_inbox()
    }
    
    # Strictly output JSON to stdout
    print(json.dumps(output, indent=2))
