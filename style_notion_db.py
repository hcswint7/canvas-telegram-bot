import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

notion_token = os.getenv("NOTION_TOKEN")
database_id = os.getenv("NOTION_DATABASE_ID")

notion = Client(auth=notion_token)

# High-tech cover image from Unsplash
cover_url = "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?q=80&w=2070&auto=format&fit=crop"

try:
    notion.databases.update(
        database_id=database_id,
        cover={
            "type": "external",
            "external": {
                "url": cover_url
            }
        },
        icon={
            "type": "emoji",
            "emoji": "⚡"
        },
        description=[
            {
                "type": "text",
                "text": {
                    "content": "COMMAND CENTER /// "
                },
                "annotations": {
                    "bold": True,
                    "color": "blue"
                }
            },
            {
                "type": "text",
                "text": {
                    "content": "LIVE CANVAS SYNC ACTIVE"
                },
                "annotations": {
                    "code": True,
                    "color": "green_background"
                }
            }
        ]
    )
    print("Successfully styled the database.")
except Exception as e:
    print(f"Error updating database styling: {e}")
