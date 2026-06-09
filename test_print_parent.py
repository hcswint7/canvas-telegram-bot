import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

notion_token = os.getenv("NOTION_TOKEN")
database_id = os.getenv("NOTION_DATABASE_ID")

notion = Client(auth=notion_token)

try:
    db = notion.databases.retrieve(database_id=database_id)
    print("Exact Parent Object:", db.get("parent"))
except Exception as e:
    print("Error:", e)
