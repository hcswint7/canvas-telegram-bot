import os
import sys
import json
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIResponseError

def log(msg):
    print(f"[EXPORTER] {msg}", file=sys.stderr)

# Gallery cover images. Notion shows a page's cover as the card image in a
# gallery view. We cycle through a small fixed set (stable Unsplash CDN URLs),
# picked deterministically by title so each assignment keeps the same image.
COVER_IMAGES = [
    "https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=1200&q=80",  # books
    "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=1200&q=80",  # notebook
    "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=1200&q=80",  # study
    "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?w=1200&q=80",  # library
    "https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=1200&q=80",  # desk
]


def cover_url_for(title: str) -> str:
    """Deterministic image URL for a page, chosen by title."""
    idx = sum(bytearray((title or "").encode("utf-8"))) % len(COVER_IMAGES)
    return COVER_IMAGES[idx]


def cover_for(title: str) -> dict:
    """Deterministic external-image page cover, chosen by title."""
    return {"type": "external", "external": {"url": cover_url_for(title)}}

def send_telegram_message(bot_token, chat_id, text):
    from telegram_utils import send_telegram
    ok = send_telegram(bot_token, chat_id, text)
    if ok:
        log("Telegram message sent successfully.")
    else:
        log("Failed to send Telegram message.")

def get_or_create_course(notion, courses_db_id, course_name):
    if not courses_db_id:
        return None
        
    try:
        # Query Courses database for matching title
        query_res = notion.databases.query(
            database_id=courses_db_id,
            filter={
                "property": "Course Name",
                "title": {
                    "equals": course_name
                }
            }
        )
        results = query_res.get("results", [])
        if results:
            log(f"Course '{course_name}' found in database.")
            return results[0]["id"]
            
        # If not found, create it
        log(f"Course '{course_name}' not found. Creating new course entry...")
        new_course = notion.pages.create(
            parent={"database_id": courses_db_id},
            properties={
                "Course Name": {
                    "title": [
                        { "text": { "content": course_name } }
                    ]
                }
            }
        )
        return new_course["id"]
    except Exception as e:
        log(f"Error in course resolution: {e}")
        return None

def add_exam_or_quiz(notion, exams_db_id, course_page_id, exam_title, due_date):
    if not exams_db_id:
        return
        
    try:
        # Check if already exists
        query_res = notion.databases.query(
            database_id=exams_db_id,
            filter={
                "property": "Test Name",
                "title": {
                    "equals": exam_title
                }
            }
        )
        if query_res.get("results", []):
            log(f"Exam/Quiz '{exam_title}' already exists in Exams database.")
            return
            
        properties = {
            "Test Name": {
                "title": [
                    { "text": { "content": exam_title } }
                ]
            },
            "Status": {
                "select": { "name": "Not Started" }
            }
        }
        
        if due_date:
            properties["Date"] = {
                "date": { "start": due_date }
            }
            
        if course_page_id:
            properties["Course"] = {
                "relation": [ { "id": course_page_id } ]
            }
            
        notion.pages.create(
            parent={"database_id": exams_db_id},
            properties=properties
        )
        log(f"Added Exam/Quiz '{exam_title}' to Exams database.")
    except Exception as e:
        log(f"Error adding Exam/Quiz: {e}")

def schedule_master_event(notion, schedule_db_id, course_page_id, event_title, event_date, event_type):
    if not schedule_db_id or not event_date:
        return
        
    try:
        # Check if already exists
        query_res = notion.databases.query(
            database_id=schedule_db_id,
            filter={
                "property": "Event Name",
                "title": {
                    "equals": event_title
                }
            }
        )
        if query_res.get("results", []):
            return
            
        properties = {
            "Event Name": {
                "title": [
                    { "text": { "content": event_title } }
                ]
            },
            "Type": {
                "select": { "name": event_type }
            },
            "Date & Time": {
                "date": { "start": event_date }
            },
            "Completed": { "checkbox": False }
        }
        
        if course_page_id:
            properties["Course"] = {
                "relation": [ { "id": course_page_id } ]
            }
            
        notion.pages.create(
            parent={"database_id": schedule_db_id},
            properties=properties
        )
        log(f"Scheduled Master Event '{event_title}' ({event_type}) for {event_date}.")
    except Exception as e:
        log(f"Error scheduling event: {e}")

def build_chart_urls(tasks):
    """Compute (bar_url, radar_url) QuickChart.io image URLs from tasks."""
    course_counts = {}
    day_counts = {}
    for t in tasks:
        course = t.get("course", "Unknown")
        course_counts[course] = course_counts.get(course, 0) + 1

        due = t.get("due_date")
        if due:
            day_counts[due] = day_counts.get(due, 0) + 1

    import urllib.parse
    radar_labels = list(course_counts.keys())
    radar_data = list(course_counts.values())
    radar_config = f"{{type:'radar',data:{{labels:{radar_labels},datasets:[{{label:'Tasks',data:{radar_data},backgroundColor:'rgba(55,65,81,0.1)',borderColor:'rgb(30,41,59)',pointBackgroundColor:'rgb(30,41,59)',pointBorderColor:'#fff',borderWidth:2}}]}},options:{{legend:{{labels:{{fontColor:'#374151',fontSize:11}}}},scale:{{pointLabels:{{fontColor:'#374151',fontSize:12}},ticks:{{fontColor:'#374151',backdropColor:'transparent',beginAtZero:true,stepSize:1}},gridLines:{{color:'rgba(209,213,219,0.7)'}},angleLines:{{color:'rgba(209,213,219,0.7)'}}}}}}}}"
    radar_url = "https://quickchart.io/chart.png?bkg=white&w=360&h=200&c=" + urllib.parse.quote(radar_config)

    bar_labels = sorted(list(day_counts.keys()))
    bar_data = [day_counts[d] for d in bar_labels]
    bar_config = f"{{type:'bar',data:{{labels:{bar_labels},datasets:[{{label:'Tasks Due',data:{bar_data},backgroundColor:'rgba(55,65,81,0.85)',borderColor:'rgb(30,41,59)',borderWidth:2,borderRadius:3}}]}},options:{{legend:{{labels:{{fontColor:'#374151',fontSize:11}}}},scales:{{yAxes:[{{ticks:{{fontColor:'#374151',beginAtZero:true,stepSize:1}},gridLines:{{color:'rgba(209,213,219,0.7)'}}}}],xAxes:[{{ticks:{{fontColor:'#374151'}},gridLines:{{color:'rgba(209,213,219,0.7)'}}}}]}}}}}}"
    bar_url = "https://quickchart.io/chart.png?bkg=white&w=480&h=200&c=" + urllib.parse.quote(bar_config)
    return bar_url, radar_url


def _image_block(url):
    return {"object": "block", "type": "image",
            "image": {"type": "external", "external": {"url": url}}}


def update_dashboard_graphs(notion_token, tasks):
    if not notion_token:
        return

    bar_url, radar_url = build_chart_urls(tasks)

    notion = Client(auth=notion_token)
    bar_block_id = os.getenv("NOTION_DASHBOARD_BAR_BLOCK_ID")
    radar_block_id = os.getenv("NOTION_DASHBOARD_RADAR_BLOCK_ID")
    page_id = os.getenv("NOTION_DASHBOARD_PAGE_ID")

    def _try_update(block_id, url, name):
        if not block_id:
            return False
        try:
            notion.blocks.update(block_id=block_id, image={"external": {"url": url}})
            log(f"Updated {name} on Dashboard.")
            return True
        except Exception as e:
            log(f"Could not update {name} block {block_id}: {e}")
            return False

    bar_ok = _try_update(bar_block_id, bar_url, "Bar Chart")
    radar_ok = _try_update(radar_block_id, radar_url, "Radar Chart")

    # Self-heal: if a chart block is missing/archived and we know the dashboard
    # page, recreate it and log the new id so it can be put in env/secrets.
    if (not bar_ok or not radar_ok) and page_id:
        to_add = []
        if not bar_ok:
            to_add.append(("BAR", _image_block(bar_url)))
        if not radar_ok:
            to_add.append(("RADAR", _image_block(radar_url)))
        try:
            res = notion.blocks.children.append(block_id=page_id,
                                                children=[b for _, b in to_add])
            for (kind, _), block in zip(to_add, res.get("results", [])):
                log(f"RECREATED {kind} chart block — set "
                    f"NOTION_DASHBOARD_{kind}_BLOCK_ID={block['id']}")
        except Exception as e:
            log(f"Could not recreate dashboard chart blocks on page {page_id}: {e}")

def update_notion_database(notion_token, database_id, tasks):
    if not notion_token or not database_id:
        log("Missing Notion credentials. Skipping dashboard update.")
        return
        
    notion = Client(auth=notion_token)
    
    # Load optional relational database IDs
    courses_db_id = os.getenv("NOTION_COURSES_DB_ID")
    schedule_db_id = os.getenv("NOTION_SCHEDULE_DB_ID")
    exams_db_id = os.getenv("NOTION_EXAMS_DB_ID")
    
    try:
        # Step 1: Query existing tasks to avoid duplicates
        existing_tasks = {}
        has_more = True
        next_cursor = None
        
        while has_more:
            query_payload = {"database_id": database_id}
            if next_cursor:
                query_payload["start_cursor"] = next_cursor
                
            results = notion.databases.query(**query_payload)
            for page in results.get("results", []):
                props = page.get("properties", {})
                title_prop = None
                for k, v in props.items():
                    if v.get("type") == "title":
                        title_prop = v["title"]
                        break
                        
                if title_prop and len(title_prop) > 0:
                    title_text = title_prop[0].get("plain_text", "")
                    existing_tasks[title_text] = page["id"]
                    
            has_more = results.get("has_more", False)
            next_cursor = results.get("next_cursor", None)
            
        log(f"Found {len(existing_tasks)} existing tasks in Notion.")
        
        # Step 2: Insert or Update tasks
        for task in tasks:
            title = task.get("title", "Untitled Task")
            course_name = task.get("course", "")
            due_date = task.get("due_date", None)
            status = task.get("status", "To Do")
            checklist = task.get("checklist", "")
            url = task.get("url")
            
            # Resolve Course Page ID relation if database exists
            course_page_id = None
            if courses_db_id and course_name:
                course_page_id = get_or_create_course(notion, courses_db_id, course_name)
                
            # Construct properties
            properties = {
                "Name": {
                    "title": [
                        {
                            "text": {"content": title}
                        }
                    ]
                }
            }
            
            # Use relation or select fallback for Course
            if course_page_id:
                properties["Course"] = {
                    "relation": [ { "id": course_page_id } ]
                }
            elif course_name:
                # Fallback to old select property if new Courses DB is not used
                properties["Course"] = {
                    "select": {"name": course_name}
                }
                
            if due_date:
                properties["Due Date"] = {
                    "date": {"start": due_date}
                }
            if status:
                properties["Status"] = {
                    "select": {"name": status}
                }

            # Direct, clickable link to the Canvas assignment (DB already has a
            # "Canvas URL" url property — populate it so the link shows on cards).
            if url:
                properties["Canvas URL"] = {"url": url}

            # Handle exams, quizzes, and tests
            is_exam = any(keyword in title.lower() for keyword in ["exam", "test", "quiz", "midterm", "final exam"])
            
            if is_exam and exams_db_id:
                add_exam_or_quiz(notion, exams_db_id, course_page_id, title, due_date)
                
            # Handle schedule events (Auto-schedule Study Blocks)
            if schedule_db_id and due_date:
                # Parse date
                try:
                    due_dt = datetime.strptime(due_date[:10], "%Y-%m-%d")
                    # Schedule exam event on due date
                    if is_exam:
                        schedule_master_event(notion, schedule_db_id, course_page_id, f"📝 EXAM: {title}", due_date[:10], "Exam")
                        
                        # Auto-schedule study blocks 1 & 2 days prior
                        study_day_1 = (due_dt - timedelta(days=2)).strftime("%Y-%m-%d")
                        study_day_2 = (due_dt - timedelta(days=1)).strftime("%Y-%m-%d")
                        schedule_master_event(notion, schedule_db_id, course_page_id, f"🧠 Prep study for {title} (1/2)", study_day_1, "Study Block")
                        schedule_master_event(notion, schedule_db_id, course_page_id, f"🧠 Final review for {title} (2/2)", study_day_2, "Study Block")
                    else:
                        # Standard task: Schedule study session 1 day before due date
                        study_day = (due_dt - timedelta(days=1)).strftime("%Y-%m-%d")
                        schedule_master_event(notion, schedule_db_id, course_page_id, f"📚 Study for {title}", study_day, "Study Block")
                except Exception as e:
                    log(f"Error parsing date for scheduling: {e}")
            
            page_id = None
            if title in existing_tasks:
                page_id = existing_tasks[title]
                if checklist:
                    properties["AI Checklist"] = {
                        "rich_text": [
                            {"text": {"content": checklist[:2000]}}
                        ]
                    }
                log(f"Updating existing task: {title}")
                notion.pages.update(page_id=page_id, properties=properties,
                                    cover=cover_for(title))
            else:
                log(f"Creating new task: {title}")
                if checklist:
                    properties["AI Checklist"] = {
                        "rich_text": [
                            {"text": {"content": checklist[:2000]}}
                        ]
                    }
                
                # Append blocks for the checklist if it exists
                children = []
                # Image FIRST so the gallery (card preview = page-content-first)
                # shows it as the card art.
                children.append(_image_block(cover_url_for(title)))
                course_text = course_name if course_name else "General"
                due_text = due_date if due_date else "No Due Date"
                children.append({
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [{"type": "text", "text": {"content": f"{course_text}  ·  Due {due_text}"}, "annotations": {"bold": True}}],
                        "icon": {"emoji": "📅"},
                        "color": "gray_background"
                    }
                })

                # Direct link back to the Canvas assignment.
                if url:
                    children.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{
                                "type": "text",
                                "text": {"content": "🔗 Open in Canvas", "link": {"url": url}},
                            }]
                        }
                    })

                if checklist:
                    children.append({
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": "Action Items"}}]
                        }
                    })
                    children.append({
                        "object": "block",
                        "type": "divider",
                        "divider": {}
                    })
                    import re
                    for line in checklist.split('\n'):
                        line = line.strip()
                        if line and "AI Study Plan:" not in line:
                            # Strip leading numbers, dashes, or bullets
                            clean_line = re.sub(r'^(\d+\.|-|\*)\s+', '', line)
                            children.append({
                                "object": "block",
                                "type": "to_do",
                                "to_do": {
                                    "rich_text": [{"type": "text", "text": {"content": clean_line[:2000]}}]
                                }
                            })
                            
                notion.pages.create(
                    parent={"database_id": database_id},
                    properties=properties,
                    children=children[:100],
                    cover=cover_for(title)
                )
                
    except APIResponseError as e:
        log(f"Notion API Error: {e}")
    except Exception as e:
        log(f"Unexpected error updating Notion: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        log("Usage: python exporter.py <path_to_payload_json>")
        sys.exit(1)
        
    payload_path = sys.argv[1]
    if not os.path.exists(payload_path):
        log(f"Payload file not found: {payload_path}")
        sys.exit(1)
        
    try:
        with open(payload_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        log(f"Failed to parse payload JSON: {e}")
        sys.exit(1)
        
    load_dotenv()
    
    # Process Telegram
    telegram_msg = data.get("telegram_message")
    if telegram_msg:
        send_telegram_message(
            os.getenv("TELEGRAM_BOT_TOKEN"),
            os.getenv("TELEGRAM_CHAT_ID"),
            telegram_msg
        )
        
    # Process Notion
    notion_tasks = data.get("notion_tasks", [])
    if notion_tasks:
        update_notion_database(
            os.getenv("NOTION_TOKEN"),
            os.getenv("NOTION_DATABASE_ID"),
            notion_tasks
        )
        update_dashboard_graphs(
            os.getenv("NOTION_TOKEN"),
            notion_tasks
        )
        
    log("Export complete.")
