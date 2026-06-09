import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

notion_token = os.getenv("NOTION_TOKEN")
database_id = os.getenv("NOTION_DATABASE_ID")

print("DEBUG: Notion Token length:", len(notion_token) if notion_token else "None")
print("DEBUG: Database ID length:", len(database_id) if database_id else "None")

notion = Client(auth=notion_token)

try:
    db = notion.databases.retrieve(database_id=database_id)
    print("SUCCESS: Database Title:", db.get("title", [{}])[0].get("plain_text", "Untitled"))
except Exception as e:
    print("FAILED:", e)
