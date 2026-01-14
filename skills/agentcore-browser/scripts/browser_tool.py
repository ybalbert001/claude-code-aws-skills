"""
AgentCore Browser Tool

Provides browser automation capabilities using Playwright with AWS AgentCore Browser.
Session info passed directly without ParameterStore dependency.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional

import nest_asyncio
from playwright.async_api import async_playwright

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BrowserTool:
    """Browser automation tool using Playwright and AWS AgentCore Browser."""

    def __init__(self, session_id: str, ws_url: str, ws_headers: Dict[str, str], aws_region: str = "us-east-1"):
        """
        Initialize browser tool with session information.

        Args:
            session_id: Browser session ID
            ws_url: WebSocket connection URL
            ws_headers: WebSocket connection headers
            aws_region: AWS region
        """
        self.session_id = session_id
        self.ws_url = ws_url
        self.ws_headers = ws_headers
        self.aws_region = aws_region
        self._browser = None
        self._page = None
        self._playwright = None
        self._initialized = False

    async def _ensure_connected(self):
        """Ensure browser connection is established."""
        if self._initialized and self._page:
            return

        try:
            logger.info("Initializing browser connection...")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                endpoint_url=self.ws_url,
                headers=self.ws_headers
            )
            context = self._browser.contexts[0]
            self._page = context.pages[0]
            self._initialized = True
            logger.info("Browser connection established")
        except Exception as e:
            logger.error(f"Failed to connect to browser: {e}")
            await self._cleanup()
            raise

    async def _cleanup(self):
        """Clean up browser resources."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
        finally:
            self._browser = None
            self._page = None
            self._playwright = None
            self._initialized = False

    async def browse_url(self, url: str, wait_time: int = 3) -> Dict[str, Any]:
        """Navigate to URL and extract basic content."""
        try:
            await self._ensure_connected()
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(wait_time)

            title = await self._page.title()
            current_url = self._page.url
            content = await self._page.inner_text("body")

            if len(content) > 5000:
                content = content[:5000] + "... [Content truncated]"

            return {
                "success": True,
                "title": title,
                "url": current_url,
                "content": content,
                "status": "Page loaded successfully"
            }
        except Exception as e:
            logger.error(f"Error browsing URL {url}: {e}")
            return {"success": False, "error": str(e), "status": "Error occurred while browsing"}

    async def search_web(self, query: str, wait_time: int = 3) -> Dict[str, Any]:
        """Perform Google search and extract results."""
        try:
            await self._ensure_connected()
            await self._page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)

            search_box = self._page.locator('input[name="q"]')
            await search_box.wait_for(state="visible", timeout=60000)
            await search_box.fill(query, timeout=10000)
            await search_box.press("Enter")
            await self._page.wait_for_selector('div.g', timeout=10000)
            await asyncio.sleep(wait_time)

            results = []
            search_results = await self._page.locator('div.g').all()

            for result in search_results[:10]:
                try:
                    title_element = result.locator('h3').first
                    link_element = result.locator('a').first
                    snippet_element = result.locator('span').first

                    if await title_element.count() > 0 and await link_element.count() > 0:
                        title = await title_element.inner_text()
                        url = await link_element.get_attribute('href')
                        snippet = await snippet_element.inner_text() if await snippet_element.count() > 0 else ''
                        results.append({"title": title, "url": url, "snippet": snippet})
                except:
                    continue

            return {
                "success": True,
                "query": query,
                "results": results,
                "status": f"Found {len(results)} search results"
            }
        except Exception as e:
            logger.error(f"Error searching web: {e}")
            return {"success": False, "error": str(e), "status": "Error occurred during search"}

    async def extract_content(self, url: Optional[str] = None, wait_time: int = 3) -> Dict[str, Any]:
        """Extract structured content from current page or navigate to URL first."""
        try:
            await self._ensure_connected()

            if url:
                await self._page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(wait_time)

            content = {
                "title": await self._page.title(),
                "url": self._page.url,
                "headings": [],
                "links": [],
                "images": [],
                "text_content": ""
            }

            for i in range(1, 7):
                headings = await self._page.locator(f'h{i}').all()
                for heading in headings:
                    try:
                        text = (await heading.inner_text()).strip()
                        if text:
                            content["headings"].append({"level": i, "text": text})
                    except:
                        continue

            links = (await self._page.locator('a[href]').all())[:20]
            for link in links:
                try:
                    text = (await link.inner_text()).strip()
                    href = await link.get_attribute('href')
                    if text and href:
                        content["links"].append({"text": text, "url": href})
                except:
                    continue

            images = (await self._page.locator('img[src]').all())[:10]
            for img in images:
                try:
                    src = await img.get_attribute('src')
                    alt = await img.get_attribute('alt') or ''
                    if src:
                        content["images"].append({"src": src, "alt": alt})
                except:
                    continue

            text_content = await self._page.inner_text('body')
            if len(text_content) > 3000:
                text_content = text_content[:3000] + '... [Content truncated]'
            content["text_content"] = text_content

            return {"success": True, "content": content, "status": "Content extracted successfully"}
        except Exception as e:
            logger.error(f"Error extracting content: {e}")
            return {"success": False, "error": str(e), "status": "Error occurred while extracting content"}

    async def fill_form(self, url: Optional[str] = None, form_data: str = "{}", wait_time: int = 3) -> Dict[str, Any]:
        """Fill form fields on current page or navigate to URL first."""
        try:
            await self._ensure_connected()

            try:
                form_fields = json.loads(form_data)
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"Invalid JSON format: {str(e)}", "status": "JSON parsing error"}

            if url:
                await self._page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(wait_time)

            filled_fields = []
            errors = []

            for field_name, field_value in form_fields.items():
                try:
                    selectors = [
                        f"input[name='{field_name}']", f"input[id='{field_name}']",
                        f"textarea[name='{field_name}']", f"textarea[id='{field_name}']",
                        f"select[name='{field_name}']", f"select[id='{field_name}']"
                    ]

                    field_found = False
                    for selector in selectors:
                        try:
                            element = self._page.locator(selector)
                            if await element.count() > 0:
                                await element.fill(str(field_value))
                                filled_fields.append(field_name)
                                field_found = True
                                break
                        except:
                            continue

                    if not field_found:
                        errors.append(f"Field '{field_name}' not found")
                except Exception as e:
                    errors.append(f"Error filling field '{field_name}': {str(e)}")

            return {
                "success": len(filled_fields) > 0,
                "filled_fields": filled_fields,
                "errors": errors,
                "status": f"Filled {len(filled_fields)} fields, {len(errors)} errors"
            }
        except Exception as e:
            logger.error(f"Error filling form: {e}")
            return {"success": False, "error": str(e), "status": "Error occurred while filling form"}

    async def execute_script(self, url: Optional[str] = None, script: str = "", wait_time: int = 3) -> Dict[str, Any]:
        """Execute JavaScript code on current page or navigate to URL first."""
        try:
            await self._ensure_connected()

            if url:
                await self._page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(wait_time)

            result = await self._page.evaluate(script)
            return {"success": True, "result": result, "status": "Script executed successfully"}
        except Exception as e:
            logger.error(f"Error executing script: {e}")
            return {"success": False, "error": str(e), "status": "Error occurred while executing script"}

    # Synchronous wrappers
    def browse_url_sync(self, url: str, wait_time: int = 3) -> Dict[str, Any]:
        return asyncio.run(self.browse_url(url, wait_time))

    def search_web_sync(self, query: str, wait_time: int = 3) -> Dict[str, Any]:
        return asyncio.run(self.search_web(query, wait_time))

    def extract_content_sync(self, url: Optional[str] = None, wait_time: int = 3) -> Dict[str, Any]:
        return asyncio.run(self.extract_content(url, wait_time))

    def fill_form_sync(self, url: Optional[str] = None, form_data: str = "{}", wait_time: int = 3) -> Dict[str, Any]:
        return asyncio.run(self.fill_form(url, form_data, wait_time))

    def execute_script_sync(self, url: Optional[str] = None, script: str = "", wait_time: int = 3) -> Dict[str, Any]:
        return asyncio.run(self.execute_script(url, script, wait_time))

    def cleanup_sync(self):
        asyncio.run(self._cleanup())
