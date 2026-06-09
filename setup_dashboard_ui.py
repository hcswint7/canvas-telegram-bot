import os
import sys
from dotenv import load_dotenv
from notion_client import Client

def log(msg):
    print(f"[UI_SETUP] {msg}", file=sys.stderr)

def make_link_text(plain_text, url):
    return {
        "type": "text",
        "text": {
            "content": plain_text,
            "link": { "url": url }
        },
        "annotations": { "bold": True, "underline": True }
    }

def main():
    load_dotenv()
    
    notion_token = os.getenv("NOTION_TOKEN")
    tasks_db_id = os.getenv("NOTION_DATABASE_ID")
    parent_page_id = os.getenv("NOTION_PARENT_PAGE_ID")
    
    courses_db_id = os.getenv("NOTION_COURSES_DB_ID")
    schedule_db_id = os.getenv("NOTION_SCHEDULE_DB_ID")
    pipeline_db_id = os.getenv("NOTION_PIPELINE_DB_ID")
    kb_db_id = os.getenv("NOTION_KB_DB_ID")
    exams_db_id = os.getenv("NOTION_EXAMS_DB_ID")
    
    if not notion_token:
        log("Error: NOTION_TOKEN is missing in .env")
        sys.exit(1)
        
    notion = Client(auth=notion_token)
    
    # Check what parent page to write to
    if not parent_page_id:
        # Fallback to tasks parent
        try:
            tasks_db = notion.databases.retrieve(database_id=tasks_db_id)
            parent_type = tasks_db.get("parent", {}).get("type")
            if parent_type == "page_id":
                parent_page_id = tasks_db["parent"]["page_id"]
            else:
                log("Error: Tasks database parent is not a page and NOTION_PARENT_PAGE_ID is not set in .env.")
                sys.exit(1)
        except Exception as e:
            log(f"Error fetching tasks parent: {e}")
            sys.exit(1)
            
    log(f"Appending dashboard UI blocks to parent page: {parent_page_id}")
    
    # Helper to clean ID
    def format_url(db_id):
        if not db_id:
            return "https://notion.so"
        clean = db_id.replace("-", "")
        return f"https://notion.so/{clean}"
        
    tasks_url = format_url(tasks_db_id)
    courses_url = format_url(courses_db_id)
    schedule_url = format_url(schedule_db_id)
    pipeline_url = format_url(pipeline_db_id)
    kb_url = format_url(kb_db_id)
    exams_url = format_url(exams_db_id)
    
    # Build the block child structure
    blocks = [
        # 1. Dashboard Header Callout
        {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": "⚡ ACADEMIC COMMAND CENTER ⚡\n"
                        },
                        "annotations": {
                            "bold": True,
                            "code": False,
                            "color": "default"
                        }
                    },
                    {
                        "type": "text",
                        "text": {
                            "content": "LIVE CANVAS SYNC ACTIVE /// CRON SCHEDULED AT 1:45 PM CT EVERYDAY"
                        },
                        "annotations": {
                            "code": True,
                            "color": "green_background"
                        }
                    }
                ],
                "icon": {
                    "type": "emoji",
                    "emoji": "⚡"
                },
                "color": "gray_background"
            }
        },
        # 2. Spacer
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": { "rich_text": [] }
        },
        # 3. Dynamic Navigation Header
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": "🧠 Navigation & Control Panel"
                        }
                    }
                ]
            }
        },
        # 4. 3-Column Triad
        {
            "object": "block",
            "type": "column_list",
            "column_list": {},
            "children": [
                # Column 1 (The Mind)
                {
                    "object": "block",
                    "type": "column",
                    "column": {},
                    "children": [
                        {
                            "object": "block",
                            "type": "callout",
                            "callout": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": "🧠 THE MIND\n"
                                        },
                                        "annotations": { "bold": True }
                                    },
                                    make_link_text("📚 Courses Registry\n", courses_url),
                                    make_link_text("📓 Knowledge Base\n", kb_url),
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": "Active study vault, spaced repetitions, and professor contact details."
                                        },
                                        "annotations": { "italic": True, "color": "gray" }
                                    }
                                ],
                                "icon": { "type": "emoji", "emoji": "🧠" },
                                "color": "blue_background"
                            }
                        }
                    ]
                },
                # Column 2 (The Pulse)
                {
                    "object": "block",
                    "type": "column",
                    "column": {},
                    "children": [
                        {
                            "object": "block",
                            "type": "callout",
                            "callout": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": "🌿 THE PULSE\n"
                                        },
                                        "annotations": { "bold": True }
                                    },
                                    make_link_text("⏳ Master Schedule\n", schedule_url),
                                    make_link_text("📝 Exams & Quizzes\n", exams_url),
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": "Class timetables, focus study sessions, and exam confidence matrix."
                                        },
                                        "annotations": { "italic": True, "color": "gray" }
                                    }
                                ],
                                "icon": { "type": "emoji", "emoji": "🌿" },
                                "color": "green_background"
                            }
                        }
                    ]
                },
                # Column 3 (The Flow)
                {
                    "object": "block",
                    "type": "column",
                    "column": {},
                    "children": [
                        {
                            "object": "block",
                            "type": "callout",
                            "callout": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": "🚀 THE FLOW\n"
                                        },
                                        "annotations": { "bold": True }
                                    },
                                    make_link_text("🚀 Project Pipeline\n", pipeline_url),
                                    make_link_text("📋 Active Task Board\n", tasks_url),
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": "Multi-stage assignments, milestone progress bars, and daily tasks."
                                        },
                                        "annotations": { "italic": True, "color": "gray" }
                                    }
                                ],
                                "icon": { "type": "emoji", "emoji": "🚀" },
                                "color": "orange_background"
                            }
                        }
                    ]
                }
            ]
        },
        # 5. Spacer
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": { "rich_text": [] }
        },
        # 6. Section Divider
        {
            "object": "block",
            "type": "divider",
            "divider": {}
        }
    ]
    
    try:
        notion.blocks.children.append(
            block_id=parent_page_id,
            children=blocks
        )
        log("Successfully rendered homepage layout on Notion page!")
    except Exception as e:
        log(f"Error rendering homepage layout: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
