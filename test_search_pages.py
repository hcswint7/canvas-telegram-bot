import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

notion_token = os.getenv("NOTION_TOKEN")
notion = Client(auth=notion_token)

try:
    logins = notion.search(filter={"value": "page", "property": "object"})
    results = logins.get("results", [])
    
    print("Found potential parent pages (not inside databases):")
    count = 0
    for page in results:
        parent_type = page.get("parent", {}).get("type")
        if parent_type != "database_id":
            # Extract title safely
            properties = page.get("properties", {})
            title_text = "Untitled"
            # In Notion API, search results properties depend on if it is a database row or page.
            # Page titles are in the 'title' property inside properties for pages.
            for k, v in properties.items():
                if v.get("type") == "title":
                    title_prop = v["title"]
                    if title_prop:
                        title_text = title_prop[0].get("plain_text", "Untitled")
                    break
            
            # Print title safely avoiding emoji encoding errors in Windows terminal
            safe_title = title_text.encode('ascii', 'ignore').decode('ascii')
            print(f"  - Page Title: '{safe_title}', ID: {page['id']}, Parent Type: {parent_type}")
            count += 1
            
    print(f"Total non-database pages: {count}")
except Exception as e:
    print("Error:", e)
