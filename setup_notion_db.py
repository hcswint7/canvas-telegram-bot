import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

notion_token = os.getenv("NOTION_TOKEN")
database_id = os.getenv("NOTION_DATABASE_ID")

notion = Client(auth=notion_token)

# We will try to add the properties. 
# Note: 'status' properties sometimes require advanced setup, so if it fails, we will modify exporter to use 'select' instead.
properties_to_add = {
    "Course": {"select": {}},
    "Due Date": {"date": {}},
    "Status": {"select": {}},
    "AI Checklist": {"rich_text": {}}
}

try:
    # Notion API doesn't easily allow creating a status property via API without defining all states and groups.
    # We will try adding just the simple ones first.
    notion.databases.update(
        database_id=database_id,
        properties=properties_to_add
    )
    print("Successfully added Course, Due Date, and AI Checklist columns.")
except Exception as e:
    print(f"Error updating database: {e}")
