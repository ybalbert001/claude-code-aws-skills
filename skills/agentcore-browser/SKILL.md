---
name: agentcore-browser
description: Toolkit for interacting with web browsers using AWS AgentCore Browser service. Provides capabilities for browser session management, web navigation, content extraction, form filling, web searching, and JavaScript execution. Use when users need to automate web interactions, scrape web content, perform automated testing, or interact with web applications programmatically.
---

# AgentCore Browser

Browser automation toolkit using AWS AgentCore Browser service with Playwright. Enables programmatic web interactions without requiring local browser installations.

## Prerequisites

- AWS credentials configured
- AWS region with AgentCore Browser service access (default: us-east-1)
- IAM permissions for AgentCore Browser service
- Python dependencies: Install via `pip install -r requirements.txt && playwright install chromium`

## Core Capabilities

### 1. Session Management
- **init_browser_session**: Initialize AWS AgentCore browser session, returns session credentials
- **close_browser_session**: Close session and cleanup resources

### 2. Web Navigation
- **browse_url**: Navigate to URL and extract page content (title, text)
- **extract_content**: Extract structured content (headings, links, images, full text)

### 3. Web Search
- **search_web**: Perform Google searches, extract top 10 results with titles, URLs, snippets

### 4. Form Interaction
- **fill_form**: Automatically fill form fields using multiple selector strategies

### 5. JavaScript Execution
- **execute_script**: Execute custom JavaScript code on web pages, return results

## Quick Start

```python
from scripts.browser_session_manager import BrowserSessionManager
from scripts.browser_tool import BrowserTool

# 1. Initialize session
manager = BrowserSessionManager(aws_region="us-east-1")
session = manager.init_browser_session(session_timeout_seconds=600)

# 2. Create tool with session credentials
tool = BrowserTool(
    session_id=session["session_id"],
    ws_url=session["ws_url"],
    ws_headers=session["ws_headers"]
)

# 3. Use tool
result = tool.browse_url_sync("https://example.com")
print(result["title"])

# 4. Cleanup
tool.cleanup_sync()
manager.close_browser_session(session["session_id"])
```

## Workflow Pattern

All operations follow this pattern:

1. **Initialize session** → Get session credentials (session_id, ws_url, ws_headers)
2. **Create tool** → Pass credentials to BrowserTool
3. **Perform operations** → Use `*_sync()` methods for synchronous calls
4. **Cleanup** → Always call `cleanup_sync()` and `close_browser_session()`

**Important**: Always use try-finally to ensure cleanup:

```python
session = manager.init_browser_session(session_timeout_seconds=600)
tool = BrowserTool(session["session_id"], session["ws_url"], session["ws_headers"])

try:
    # Operations here
    pass
finally:
    tool.cleanup_sync()
    manager.close_browser_session(session["session_id"])
```

## Common Tasks

### Search and Visit Results

```python
# Search
results = tool.search_web_sync(query="AWS documentation")

# Visit first result
if results['success'] and results['results']:
    first_url = results['results'][0]['url']
    content = tool.browse_url_sync(url=first_url, wait_time=3)
    print(content['title'])
```

### Extract Structured Data

```python
# Get headings, links, images
content = tool.extract_content_sync(url="https://example.com")

for heading in content['content']['headings']:
    print(f"H{heading['level']}: {heading['text']}")

for link in content['content']['links']:
    print(f"{link['text']}: {link['url']}")
```

### Fill and Submit Forms

```python
import json

form_data = {"username": "user@example.com", "password": "pass123"}
result = tool.fill_form_sync(
    url="https://example.com/login",
    form_data=json.dumps(form_data)
)

print(f"Filled: {result['filled_fields']}")
print(f"Errors: {result['errors']}")
```

### Execute Custom JavaScript

```python
script = "return {title: document.title, links: document.querySelectorAll('a').length};"
result = tool.execute_script_sync(url="https://example.com", script=script)
print(result['result'])
```

## API Reference

### BrowserSessionManager

**init_browser_session(session_timeout_seconds=None)**
- Returns: `{success, status, session_id, ws_url, ws_headers, live_view_url, aws_region}`
- Note: Store all returned values for creating BrowserTool

**close_browser_session(session_id)**
- Returns: `{success, status, session_id}`

### BrowserTool

**browse_url_sync(url, wait_time=3)**
- Returns: `{success, title, url, content, status}`
- Content truncated to 5000 chars

**search_web_sync(query, wait_time=3)**
- Returns: `{success, query, results[], status}`
- Results: `[{title, url, snippet}, ...]` (max 10)

**extract_content_sync(url=None, wait_time=3)**
- Returns: `{success, content{title, url, headings[], links[], images[], text_content}, status}`
- Headings: `[{level, text}, ...]`
- Links: max 20
- Images: max 10
- Text: truncated to 3000 chars

**fill_form_sync(url=None, form_data="{}", wait_time=3)**
- form_data: JSON string of field names/values
- Returns: `{success, filled_fields[], errors[], status}`
- Tries multiple selectors: name, id for input/textarea/select

**execute_script_sync(url=None, script="", wait_time=3)**
- Returns: `{success, result, status}`

**cleanup_sync()**
- Always call before closing session

## Error Handling

All methods return `{success: bool, ...}`. Always check success field:

```python
result = tool.browse_url_sync("https://example.com")
if result['success']:
    # Process result
else:
    print(f"Error: {result['error']}")
```

## Best Practices

1. **Session reuse**: Reuse session for multiple operations
2. **Always cleanup**: Use try-finally pattern
3. **Monitor live view**: Use `live_view_url` to watch browser (expires in 300s)
4. **Wait times**: Adjust `wait_time` parameter for slow-loading pages
5. **Content limits**: Large content auto-truncated to prevent memory issues

## Advanced Examples

For complete workflow examples including search → visit → extract patterns, see [references/usage_examples.md](references/usage_examples.md)

## Troubleshooting

**"Failed to connect to browser"**
- Verify AWS credentials and region
- Check IAM permissions for AgentCore Browser
- Ensure network connectivity

**"Element not found" in form filling**
- Increase wait_time parameter
- Check page has fully loaded
- Verify field names/IDs match page elements

**"Session not found"**
- Session may have expired (check timeout)
- Ensure session was initialized successfully
- Verify session_id is correct

## Resources

- Scripts: `browser_session_manager.py`, `browser_tool.py`
- Dependencies: `requirements.txt`
- Examples: `references/usage_examples.md`
