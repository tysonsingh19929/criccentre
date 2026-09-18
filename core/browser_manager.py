import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth

class BrowserManager:
    """
    Manages Playwright browser instance with isolated contexts per request,
    built-in stealth configurations, realistic user agents, viewport sizes,
    and anti-bot protection avoidance.
    """
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certificate-errors",
                "--ignore-certificate-errors-spki-list",
            ]
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def create_isolated_context(self) -> BrowserContext:
        if not self._browser:
            raise RuntimeError("BrowserManager instance is not active.")
        context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="Europe/London"
        )
        return context

    async def fetch_page_content(self, url: str, wait_selector: Optional[str] = None, delay_secs: float = 2.0) -> str:
        """
        Navigates to URL in an isolated stealth context, waits for domcontentloaded,
        waits for selector, and returns rendered HTML.
        """
        context = await self.create_isolated_context()
        page = await context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=20000)
                except Exception:
                    pass
            if delay_secs > 0:
                await page.wait_for_timeout(int(delay_secs * 1000))
            return await page.content()
        finally:
            await page.close()
            await context.close()
