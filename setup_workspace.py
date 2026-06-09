import os
import sys
import time
from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIResponseError

def log(msg):
    print(f"[SETUP] {msg}", file=sys.stderr)

def main():
    load_dotenv()
    
    notion_token = os.getenv("NOTION_TOKEN")
    tasks_db_id = os.getenv("NOTION_DATABASE_ID")
    parent_page_id = os.getenv("NOTION_PARENT_PAGE_ID")
    
    if not notion_token:
        log("Error: NOTION_TOKEN is missing in .env")
        sys.exit(1)
        
    if not tasks_db_id:
        log("Error: NOTION_DATABASE_ID is missing in .env")
        sys.exit(1)
        
    notion = Client(auth=notion_token)
    
    # Step 1: Validate connection and fetch parent page
    log("Validating Notion connection...")
    try:
        tasks_db = notion.databases.retrieve(database_id=tasks_db_id)
        log(f"Successfully connected to Notion. Tasks Database: '{tasks_db.get('title', [{}])[0].get('plain_text', 'Tasks')}'")
    except APIResponseError as e:
        log(f"Notion API Authentication Failure: {e}")
        log("Please check if your NOTION_TOKEN is valid and the integration is shared with the database.")
        sys.exit(1)
        
    # Get parent page ID
    parent_type = tasks_db.get("parent", {}).get("type")
    if parent_type == "page_id":
        detected_parent_id = tasks_db["parent"]["page_id"]
        log(f"Detected parent page ID: {detected_parent_id}")
    else:
        detected_parent_id = None
        log("Parent of Tasks Database is not a page (likely workspace root).")
        
    # Determine the parent to use
    final_parent_id = parent_page_id or detected_parent_id
    if not final_parent_id:
        log("CRITICAL ERROR: No parent page ID found.")
        log("Since the Tasks Database is at the workspace root, the Notion API cannot create sibling databases directly.")
        log("Please create a regular Page in Notion, share the integration with it, and add 'NOTION_PARENT_PAGE_ID=<page_id>' to your .env file.")
        sys.exit(1)
        
    log(f"Using parent page ID: {final_parent_id} for new databases.")
    
    # Step 2: Upgrade properties of the existing Tasks Database
    log("Upgrading Tasks Database properties...")
    tasks_properties = {
        "Priority": {
            "select": {
                "options": [
                    { "name": "High ⚡", "color": "red" },
                    { "name": "Medium 🔋", "color": "yellow" },
                    { "name": "Low 🪫", "color": "blue" }
                ]
            }
        },
        "Estimated Time": { "number": { "format": "number" } },
        "Energy Level": {
            "select": {
                "options": [
                    { "name": "High Focus", "color": "red" },
                    { "name": "Medium", "color": "yellow" },
                    { "name": "Low Energy", "color": "blue" }
                ]
            }
        }
    }
    
    try:
        notion.databases.update(database_id=tasks_db_id, properties=tasks_properties)
        log("Tasks Database properties upgraded successfully.")
    except Exception as e:
        log(f"Warning: Failed to upgrade Tasks database properties: {e}")
        
    created_db_ids = {}
    
    # Step 3: Create Courses Database
    log("Creating Courses Database...")
    courses_schema = {
        "parent": { "type": "page_id", "page_id": final_parent_id },
        "icon": { "type": "emoji", "emoji": "🏫" },
        "title": [ { "type": "text", "text": { "content": "Courses" } } ],
        "properties": {
            "Course Name": { "title": {} },
            "Course Code": { "rich_text": {} },
            "Professor": { "rich_text": {} },
            "Professor Email": { "rich_text": {} },
            "Office Hours": { "rich_text": {} },
            "Grade Target": { "number": { "format": "percent" } },
            "Current Grade": { "number": { "format": "percent" } },
            "Syllabus Link": { "url": {} }
        }
    }
    
    try:
        courses_db = notion.databases.create(**courses_schema)
        created_db_ids["Courses"] = courses_db["id"]
        log(f"Successfully created Courses Database! ID: {courses_db['id']}")
    except Exception as e:
        log(f"CRITICAL ERROR creating Courses Database: {e}")
        sys.exit(1)
        
    time.sleep(0.5) # Prevent rate limits
    
    # Step 4: Create Master Schedule Database
    log("Creating Master Schedule Database...")
    schedule_schema = {
        "parent": { "type": "page_id", "page_id": final_parent_id },
        "icon": { "type": "emoji", "emoji": "⏳" },
        "title": [ { "type": "text", "text": { "content": "Master Schedule" } } ],
        "properties": {
            "Event Name": { "title": {} },
            "Type": {
                "select": {
                    "options": [
                        { "name": "Class", "color": "blue" },
                        { "name": "Exam", "color": "red" },
                        { "name": "Study Block", "color": "green" },
                        { "name": "Quiz", "color": "orange" },
                        { "name": "Review", "color": "purple" }
                    ]
                }
            },
            "Date & Time": { "date": {} },
            "Location": { "rich_text": {} },
            "Energy Level": {
                "select": {
                    "options": [
                        { "name": "High Focus", "color": "red" },
                        { "name": "Medium", "color": "yellow" },
                        { "name": "Low Energy", "color": "blue" }
                    ]
                }
            },
            "Completed": { "checkbox": {} }
        }
    }
    
    try:
        schedule_db = notion.databases.create(**schedule_schema)
        created_db_ids["Schedule"] = schedule_db["id"]
        log(f"Successfully created Master Schedule Database! ID: {schedule_db['id']}")
    except Exception as e:
        log(f"CRITICAL ERROR creating Master Schedule Database: {e}")
        sys.exit(1)
        
    time.sleep(0.5)
    
    # Step 5: Create Project Pipeline Database
    log("Creating Project Pipeline Database...")
    pipeline_schema = {
        "parent": { "type": "page_id", "page_id": final_parent_id },
        "icon": { "type": "emoji", "emoji": "🚀" },
        "title": [ { "type": "text", "text": { "content": "Project Pipeline" } } ],
        "properties": {
            "Project Name": { "title": {} },
            "Status": {
                "select": {
                    "options": [
                        { "name": "Not Started", "color": "gray" },
                        { "name": "Research", "color": "blue" },
                        { "name": "Outline", "color": "purple" },
                        { "name": "Drafting", "color": "yellow" },
                        { "name": "Polish", "color": "orange" },
                        { "name": "Completed", "color": "green" }
                    ]
                }
            },
            "Final Due Date": { "date": {} },
            "Project Weight": { "number": { "format": "percent" } },
            "Progress": { "number": { "format": "percent" } }
        }
    }
    
    try:
        pipeline_db = notion.databases.create(**pipeline_schema)
        created_db_ids["Pipeline"] = pipeline_db["id"]
        log(f"Successfully created Project Pipeline Database! ID: {pipeline_db['id']}")
    except Exception as e:
        log(f"CRITICAL ERROR creating Project Pipeline Database: {e}")
        sys.exit(1)
        
    time.sleep(0.5)
    
    # Step 6: Create Knowledge Base Database
    log("Creating Knowledge Base Database...")
    kb_schema = {
        "parent": { "type": "page_id", "page_id": final_parent_id },
        "icon": { "type": "emoji", "emoji": "🧠" },
        "title": [ { "type": "text", "text": { "content": "Knowledge Base" } } ],
        "properties": {
            "Topic Name": { "title": {} },
            "Status": {
                "select": {
                    "options": [
                        { "name": "To Review", "color": "red" },
                        { "name": "Reviewing", "color": "yellow" },
                        { "name": "Mastered", "color": "green" }
                    ]
                }
            },
            "Last Reviewed": { "date": {} },
            "Interval Days": { "number": { "format": "number" } },
            "Recall Rating": {
                "select": {
                    "options": [
                        { "name": "1 - Poor", "color": "red" },
                        { "name": "3 - Medium", "color": "yellow" },
                        { "name": "5 - Perfect", "color": "green" }
                    ]
                }
            },
            "Source URL": { "url": {} }
        }
    }
    
    try:
        kb_db = notion.databases.create(**kb_schema)
        created_db_ids["KnowledgeBase"] = kb_db["id"]
        log(f"Successfully created Knowledge Base Database! ID: {kb_db['id']}")
    except Exception as e:
        log(f"CRITICAL ERROR creating Knowledge Base Database: {e}")
        sys.exit(1)
        
    time.sleep(0.5)
    
    # Step 7: Create Exams & Quizzes Database
    log("Creating Exams & Quizzes Database...")
    exams_schema = {
        "parent": { "type": "page_id", "page_id": final_parent_id },
        "icon": { "type": "emoji", "emoji": "📝" },
        "title": [ { "type": "text", "text": { "content": "Exams & Quizzes" } } ],
        "properties": {
            "Test Name": { "title": {} },
            "Date": { "date": {} },
            "Status": {
                "select": {
                    "options": [
                        { "name": "Not Started", "color": "red" },
                        { "name": "Studying", "color": "yellow" },
                        { "name": "Ready", "color": "green" },
                        { "name": "Completed", "color": "gray" }
                    ]
                }
            },
            "Score": { "number": { "format": "percent" } },
            "Weight": { "number": { "format": "percent" } },
            "Confidence Level": {
                "select": {
                    "options": [
                        { "name": "Red 🔴", "color": "red" },
                        { "name": "Yellow 🟡", "color": "yellow" },
                        { "name": "Green 🟢", "color": "green" }
                    ]
                }
            }
        }
    }
    
    try:
        exams_db = notion.databases.create(**exams_schema)
        created_db_ids["Exams"] = exams_db["id"]
        log(f"Successfully created Exams & Quizzes Database! ID: {exams_db['id']}")
    except Exception as e:
        log(f"CRITICAL ERROR creating Exams & Quizzes Database: {e}")
        sys.exit(1)
        
    time.sleep(0.5)
    
    # Step 8: Create Relations and Links
    log("Establishing relations between databases...")
    
    # 1. Link Tasks to Courses
    try:
        notion.databases.update(
            database_id=tasks_db_id,
            properties={
                "Course": {
                    "relation": {
                        "database_id": created_db_ids["Courses"],
                        "type": "single_property"
                    }
                }
            }
        )
        log("Linked Tasks -> Courses.")
    except Exception as e:
        log(f"Error linking Tasks -> Courses: {e}")
        
    time.sleep(0.5)
        
    # 2. Link Tasks to Project Pipeline (Dual relation)
    try:
        notion.databases.update(
            database_id=tasks_db_id,
            properties={
                "Project": {
                    "relation": {
                        "database_id": created_db_ids["Pipeline"],
                        "type": "dual_property",
                        "dual_property": { "synced_property_name": "Tasks" }
                    }
                }
            }
        )
        log("Linked Tasks <-> Project Pipeline.")
    except Exception as e:
        log(f"Error linking Tasks <-> Project Pipeline: {e}")
        
    time.sleep(0.5)
        
    # 3. Link Master Schedule to Courses
    try:
        notion.databases.update(
            database_id=created_db_ids["Schedule"],
            properties={
                "Course": {
                    "relation": {
                        "database_id": created_db_ids["Courses"],
                        "type": "single_property"
                    }
                }
            }
        )
        log("Linked Master Schedule -> Courses.")
    except Exception as e:
        log(f"Error linking Master Schedule -> Courses: {e}")
        
    time.sleep(0.5)
        
    # 4. Link Knowledge Base to Courses
    try:
        notion.databases.update(
            database_id=created_db_ids["KnowledgeBase"],
            properties={
                "Course": {
                    "relation": {
                        "database_id": created_db_ids["Courses"],
                        "type": "single_property"
                    }
                }
            }
        )
        log("Linked Knowledge Base -> Courses.")
    except Exception as e:
        log(f"Error linking Knowledge Base -> Courses: {e}")
        
    time.sleep(0.5)
        
    # 5. Link Exams to Courses
    try:
        notion.databases.update(
            database_id=created_db_ids["Exams"],
            properties={
                "Course": {
                    "relation": {
                        "database_id": created_db_ids["Courses"],
                        "type": "single_property"
                    }
                }
            }
        )
        log("Linked Exams -> Courses.")
    except Exception as e:
        log(f"Error linking Exams -> Courses: {e}")
        
    log("\n" + "="*40)
    log("DATABASE CREATION COMPLETE!")
    log(f"Courses Database ID: {created_db_ids['Courses']}")
    log(f"Master Schedule ID: {created_db_ids['Schedule']}")
    log(f"Project Pipeline ID: {created_db_ids['Pipeline']}")
    log(f"Knowledge Base ID: {created_db_ids['KnowledgeBase']}")
    log(f"Exams & Quizzes ID: {created_db_ids['Exams']}")
    log("="*40)
    
    # Save IDs to .env file for the exporter to access
    try:
        with open(".env", "a") as f:
            f.write(f"\n# New Relational Database IDs\n")
            f.write(f"NOTION_COURSES_DB_ID={created_db_ids['Courses']}\n")
            f.write(f"NOTION_SCHEDULE_DB_ID={created_db_ids['Schedule']}\n")
            f.write(f"NOTION_PIPELINE_DB_ID={created_db_ids['Pipeline']}\n")
            f.write(f"NOTION_KB_DB_ID={created_db_ids['KnowledgeBase']}\n")
            f.write(f"NOTION_EXAMS_DB_ID={created_db_ids['Exams']}\n")
        log("Successfully appended new Database IDs to .env file.")
    except Exception as e:
        log(f"Error writing to .env: {e}")

if __name__ == "__main__":
    main()
