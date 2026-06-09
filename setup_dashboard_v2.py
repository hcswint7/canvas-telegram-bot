import os
import sys
from dotenv import load_dotenv, set_key
from notion_client import Client

def main():
    load_dotenv()
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")
    env_file = ".env"

    notion = Client(auth=notion_token)

    try:
        new_page = notion.pages.create(
            parent={"database_id": database_id},
            icon={"type": "emoji", "emoji": "🔮"},
            cover={"type": "external", "external": {"url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=2564&auto=format&fit=crop"}},
            properties={
                "Name": {
                    "title": [{"text": {"content": "🌌 [DRAG TO SIDEBAR] Command Center V2"}}]
                }
            },
            children=[
                {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [{"type": "text", "text": {"content": "Welcome to your upgraded Command Center. Drag this page out to your sidebar! \nType '/linked database' below to embed your tasks."}, "annotations": {"bold": True, "color": "blue"}}],
                        "icon": {"emoji": "✨"},
                        "color": "blue_background"
                    }
                },
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"text": {"content": "📊 Workload Analytics"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "column_list",
                    "column_list": {
                        "children": [
                            {
                                "object": "block",
                                "type": "column",
                                "column": {
                                    "children": [
                                        {
                                            "object": "block",
                                            "type": "heading_3",
                                            "heading_3": { "rich_text": [{"text": {"content": "📅 7-Day Timeline"}}], "color": "purple_background" }
                                        },
                                        {
                                            "object": "block",
                                            "type": "image",
                                            "image": {
                                                "type": "external",
                                                "external": {"url": "https://quickchart.io/chart?c={type:'bar',data:{labels:['Loading...'],datasets:[{data:[1]}]}}"}
                                            }
                                        }
                                    ]
                                }
                            },
                            {
                                "object": "block",
                                "type": "column",
                                "column": {
                                    "children": [
                                        {
                                            "object": "block",
                                            "type": "heading_3",
                                            "heading_3": { "rich_text": [{"text": {"content": "🎯 Course Radar"}}], "color": "pink_background" }
                                        },
                                        {
                                            "object": "block",
                                            "type": "image",
                                            "image": {
                                                "type": "external",
                                                "external": {"url": "https://quickchart.io/chart?c={type:'radar',data:{labels:['Loading...'],datasets:[{data:[1]}]}}"}
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
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
                        "rich_text": [{"text": {"content": "📋 Live Tasks"}}]
                    }
                }
            ]
        )
        page_id = new_page["id"]
        print(f"Created Dashboard Page: {page_id}")
        
        blocks_req = notion.blocks.children.list(block_id=page_id)
        column_list_id = None
        for b in blocks_req.get("results", []):
            if b["type"] == "column_list":
                column_list_id = b["id"]
                break
                
        if column_list_id:
            cols_req = notion.blocks.children.list(block_id=column_list_id)
            cols = cols_req.get("results", [])
            
            left_col_id = cols[0]["id"]
            left_children = notion.blocks.children.list(block_id=left_col_id).get("results", [])
            bar_chart_id = [b["id"] for b in left_children if b["type"] == "image"][0]
            
            right_col_id = cols[1]["id"]
            right_children = notion.blocks.children.list(block_id=right_col_id).get("results", [])
            radar_chart_id = [b["id"] for b in right_children if b["type"] == "image"][0]

            print(f"Bar Chart Block ID: {bar_chart_id}")
            print(f"Radar Chart Block ID: {radar_chart_id}")

            set_key(env_file, "NOTION_DASHBOARD_BAR_BLOCK_ID", bar_chart_id)
            set_key(env_file, "NOTION_DASHBOARD_RADAR_BLOCK_ID", radar_chart_id)
            print("Successfully saved V2 block IDs to .env!")
        else:
            print("Could not find column list.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
