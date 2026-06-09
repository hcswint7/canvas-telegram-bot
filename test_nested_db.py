import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

notion_token = os.getenv("NOTION_TOKEN")
database_id = os.getenv("NOTION_DATABASE_ID")

notion = Client(auth=notion_token)

try:
    print("Testing automatic nested workspace creation...")
    # Step 1: Create a row (page) inside the existing Tasks database
    nested_page = notion.pages.create(
        parent={"database_id": database_id},
        properties={
            "Name": {
                "title": [
                    { "text": { "content": "🌌 Academic Workspace Hub (System)" } }
                ]
            }
        }
    )
    nested_page_id = nested_page["id"]
    print(f"Created page inside database. Page ID: {nested_page_id}")
    
    # Step 2: Try to create a database inside this page
    test_db = notion.databases.create(
        parent={"type": "page_id", "page_id": nested_page_id},
        title=[ { "type": "text", "text": { "content": "Test Nested Database" } } ],
        properties={
            "Name": { "title": {} }
        }
    )
    print(f"Successfully created nested database! ID: {test_db['id']}")
    
    # Clean up (archive the page)
    notion.pages.update(page_id=nested_page_id, archived=True)
    print("Cleaned up test page.")
except Exception as e:
    print("Failed nested creation test:", e)
