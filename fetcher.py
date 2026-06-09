import os
import sys
import json
import imaplib
import email
from email.header import decode_header
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
                assignments = course.get_assignments(order_by="due_at")
                for a in assignments:
                    due_str = getattr(a, "due_at", None)
                    if not due_str:
                        continue
                    try:
                        due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if not (window_start <= due_dt <= window_end):
                        continue
                    c_info["assignments"].append({
                        "id": getattr(a, "id", None),
                        "name": getattr(a, "name", "Unnamed Assignment"),
                        "due_at": due_str,
                        "points_possible": getattr(a, "points_possible", None),
                        "has_submitted": getattr(a, "has_submitted_submissions", False),
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

def get_gmail_data():
    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    
    if not user or not password:
        log("Gmail credentials missing.")
        return {"error": "Missing Gmail Credentials"}
        
    try:
        # Connect to server
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.select("inbox")
        
        # Fetch emails from last 3 days
        date_since = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{date_since}")')
        
        email_data = []
        if status == "OK" and messages[0]:
            # limit to top 20 latest to avoid long processing
            msg_nums = messages[0].split()[-20:]
            for num in msg_nums:
                res, msg_data = mail.fetch(num, '(RFC822)')
                if res == "OK":
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            # Decode subject
                            subject, encoding = decode_header(msg.get("Subject", ""))[0]
                            if isinstance(subject, bytes):
                                try:
                                    subject = subject.decode(encoding if encoding else "utf-8")
                                except:
                                    subject = subject.decode("utf-8", errors="ignore")
                                    
                            from_ = msg.get("From", "")
                            date_ = msg.get("Date", "")
                            
                            # Optional: Filter for .edu or canvas
                            if "jccc.edu" in from_.lower() or "canvas" in from_.lower():
                                # Get body text
                                body = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        if part.get_content_type() == "text/plain":
                                            try:
                                                body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                                                break
                                            except:
                                                pass
                                else:
                                    try:
                                        body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
                                    except:
                                        pass
                                        
                                email_data.append({
                                    "from": from_,
                                    "subject": subject,
                                    "date": date_,
                                    "body": body[:500] # truncate to avoid huge payload
                                })
                                
        mail.logout()
        return {"emails": email_data}
    except Exception as e:
        log(f"Gmail IMAP Error: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    load_dotenv()
    
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "canvas": get_canvas_data(),
        "gmail": get_gmail_data()
    }
    
    # Strictly output JSON to stdout
    print(json.dumps(output, indent=2))
