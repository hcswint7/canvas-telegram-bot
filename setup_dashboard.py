import os
import sys
from dotenv import load_dotenv, set_key
from notion_client import Client

def main():
    load_dotenv()
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")
    env_file = ".env"

    if not notion_token or not database_id:
        print("Missing credentials.")
        sys.exit(1)

    notion = Client(auth=notion_token)

    print("Creating the Command Center Wrapper Page...")

    # Create the page inside the database (the user will drag it out)
    try:
        new_page = notion.pages.create(
            parent={"database_id": database_id},
            icon={"type": "emoji", "emoji": "🌌"},
            cover={"type": "external", "external": {"url": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop"}},
            properties={
                "Name": {
                    "title": [{"text": {"content": "🌌 [DRAG TO SIDEBAR] Command Center"}}]
                }
            },
            children=[
                {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [{"text": {"content": "STEP 1: Drag this page out of the database and into your Notion sidebar so it becomes a standalone Dashboard page!\nSTEP 2: Click below, type '/linked database' and select your Canvas_API database!"}}],
                        "icon": {"emoji": "🚨"},
                        "color": "blue_background"
                    }
                },
                {
                    "object": "block",
                    "type": "divider",
                    "divider": {}
                },
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"text": {"content": "📊 Workload Analytics"}}]
                    }
                },
                # We will create two placeholder image blocks.
                {
                    "object": "block",
                    "type": "image",
                    "image": {
                        "type": "external",
                        "external": {"url": "https://quickchart.io/chart?c={type:'bar',data:{labels:['Loading...'],datasets:[{data:[1]}]}}"}
                    }
                },
                {
                    "object": "block",
                    "type": "image",
                    "image": {
                        "type": "external",
                        "external": {"url": "https://quickchart.io/chart?c={type:'radar',data:{labels:['Loading...'],datasets:[{data:[1]}]}}"}
                    }
                },
                {
                    "object": "block",
                    "type": "divider",
                    "divider": {}
                },
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"text": {"content": "📋 Live Tasks (Link Below)"}}]
                    }
                }
            ]
        )
        page_id = new_page["id"]
        print(f"Created Dashboard Page: {page_id}")

        # Now we need to retrieve the blocks to find the image block IDs
        blocks = notion.blocks.children.list(block_id=page_id)
        image_block_ids = [b["id"] for b in blocks.get("results", []) if b["type"] == "image"]

        if len(image_block_ids) >= 2:
            bar_chart_id = image_block_ids[0]
            radar_chart_id = image_block_ids[1]
            print(f"Bar Chart Block ID: {bar_chart_id}")
            print(f"Radar Chart Block ID: {radar_chart_id}")

            # Save to .env
            set_key(env_file, "NOTION_DASHBOARD_BAR_BLOCK_ID", bar_chart_id)
            set_key(env_file, "NOTION_DASHBOARD_RADAR_BLOCK_ID", radar_chart_id)
            print("Successfully saved block IDs to .env for the exporter to update!")
        else:
            print("Could not find the image blocks.")

    except Exception as e:
        print(f"Error creating dashboard: {e}")

if __name__ == "__main__":
    main()
