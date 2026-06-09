import os
import sys
import subprocess
from dotenv import load_dotenv
from notion_client import Client

def main():
    load_dotenv()
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")
    
    if not notion_token or not database_id:
        print("Missing credentials in .env")
        sys.exit(1)
        
    notion = Client(auth=notion_token)

    # 1. Archive existing pages to allow fresh re-export with nice blocks
    print("Archiving existing tasks to allow fresh formatting...")
    try:
        has_more = True
        next_cursor = None
        while has_more:
            query = {"database_id": database_id}
            if next_cursor:
                query["start_cursor"] = next_cursor
            results = notion.databases.query(**query)
            for page in results.get("results", []):
                notion.pages.update(page_id=page["id"], archived=True)
            has_more = results.get("has_more", False)
            next_cursor = results.get("next_cursor", None)
        print("Done archiving.")
    except Exception as e:
        print(f"Error archiving: {e}")

    # 2. Update Database Properties for aesthetics
    print("Styling database properties (Colors and Tags)...")
    try:
        notion.databases.update(
            database_id=database_id,
            properties={
                "Status": {
                    "select": {
                        "options": [
                            {"name": "To Do", "color": "red"},
                            {"name": "In Progress", "color": "yellow"},
                            {"name": "Completed", "color": "green"}
                        ]
                    }
                },
                "Course": {
                    "select": {
                        "options": [
                            {"name": "MKT-230-353", "color": "blue"},
                            {"name": "BLAW-261-353", "color": "purple"}
                        ]
                    }
                }
            }
        )
        print("Properties styled successfully.")
    except Exception as e:
        print(f"Error styling properties: {e}")

    # 3. Re-run exporter to generate fresh tasks with interactive to-do blocks
    print("Re-running exporter to generate fresh tasks with interactive to-do blocks...")
    subprocess.run([sys.executable, "exporter.py", "export_payload.json"])
    print("Re-formatting complete! Check your Notion.")

if __name__ == "__main__":
    main()
