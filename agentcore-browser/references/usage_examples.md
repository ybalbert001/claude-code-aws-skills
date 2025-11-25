# AgentCore Browser Usage Examples

Complete examples demonstrating common browser automation workflows.

## Example 1: Basic Web Browsing

```python
from scripts.browser_session_manager import BrowserSessionManager
from scripts.browser_tool import BrowserTool

# Initialize session
manager = BrowserSessionManager(aws_region="us-east-1")
session = manager.init_browser_session(session_timeout_seconds=600)

if session["success"]:
    # Create tool
    tool = BrowserTool(
        session_id=session["session_id"],
        ws_url=session["ws_url"],
        ws_headers=session["ws_headers"]
    )

    try:
        # Browse URL
        result = tool.browse_url_sync("https://www.example.com")
        print(f"Title: {result['title']}")
        print(f"Content: {result['content'][:200]}...")
    finally:
        tool.cleanup_sync()
        manager.close_browser_session(session["session_id"])
```

## Example 2: Web Search

```python
# Initialize and create tool (same as above)
tool = BrowserTool(session_id, ws_url, ws_headers)

# Search the web
results = tool.search_web_sync(query="AWS AgentCore documentation")

for result in results['results']:
    print(f"- {result['title']}")
    print(f"  {result['url']}")
    print(f"  {result['snippet']}\n")
```

## Example 3: Extract Structured Content

```python
# Extract headings, links, images, and text
content = tool.extract_content_sync(url="https://www.example.com")

if content["success"]:
    print(f"Title: {content['content']['title']}")
    print(f"Headings: {len(content['content']['headings'])}")
    print(f"Links: {len(content['content']['links'])}")
    print(f"Images: {len(content['content']['images'])}")
    print(f"Text: {content['content']['text_content'][:300]}...")
```

## Example 4: Fill Form

```python
import json

form_data = {
    "username": "user@example.com",
    "password": "secure_password",
    "remember": "true"
}

result = tool.fill_form_sync(
    url="https://example.com/login",
    form_data=json.dumps(form_data),
    wait_time=2
)

print(f"Filled fields: {result['filled_fields']}")
if result['errors']:
    print(f"Errors: {result['errors']}")
```

## Example 5: Execute JavaScript

```python
script = """
return {
    title: document.title,
    url: window.location.href,
    linkCount: document.querySelectorAll('a').length,
    imageCount: document.querySelectorAll('img').length
};
"""

result = tool.execute_script_sync(
    url="https://www.example.com",
    script=script
)

print(f"Page info: {result['result']}")
```

## Example 6: Complete Workflow (Search → Visit → Extract)

```python
manager = BrowserSessionManager(aws_region="us-east-1")
session = manager.init_browser_session(session_timeout_seconds=600)

if session["success"]:
    tool = BrowserTool(
        session_id=session["session_id"],
        ws_url=session["ws_url"],
        ws_headers=session["ws_headers"]
    )

    try:
        # Step 1: Search
        search_results = tool.search_web_sync(query="Python asyncio tutorial")
        print(f"Found {len(search_results['results'])} results")

        # Step 2: Visit top results
        for i, result in enumerate(search_results['results'][:3], 1):
            print(f"\n{i}. Visiting: {result['title']}")

            # Browse the URL
            browse_result = tool.browse_url_sync(url=result['url'], wait_time=2)

            if browse_result["success"]:
                print(f"   Page loaded: {browse_result['title']}")

                # Step 3: Extract content
                content = tool.extract_content_sync(wait_time=1)
                if content["success"]:
                    headings = content["content"]["headings"]
                    print(f"   Found {len(headings)} headings")

    finally:
        tool.cleanup_sync()
        manager.close_browser_session(session["session_id"])
```

## Error Handling Pattern

```python
result = tool.browse_url_sync(url="https://example.com")

if result['success']:
    # Process successful result
    print(f"Success: {result['title']}")
else:
    # Handle error
    print(f"Error: {result['error']}")
    print(f"Status: {result['status']}")
```

## Session Management Best Practices

```python
# Always use try-finally to ensure cleanup
manager = BrowserSessionManager(aws_region="us-east-1")
session = manager.init_browser_session(session_timeout_seconds=600)

if not session["success"]:
    print(f"Failed to create session: {session['status']}")
    exit(1)

session_id = session["session_id"]
print(f"Live View: {session['live_view_url']}")  # Watch browser activity

try:
    tool = BrowserTool(
        session_id=session_id,
        ws_url=session["ws_url"],
        ws_headers=session["ws_headers"]
    )

    # Perform operations
    # ...

finally:
    # Always cleanup
    if tool:
        tool.cleanup_sync()
    manager.close_browser_session(session_id)
```
