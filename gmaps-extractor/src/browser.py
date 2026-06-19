import asyncio
import random

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

class BrowserPool:
    def __init__(self, n_workers: int = 1, headless: bool = True, locale: str = "id-ID"):
        self.n_workers = n_workers
        self.headless = headless
        self.locale = locale
        self._playwright = None
        self._browser: Browser | None = None
        self._contexts: list[BrowserContext] = []
        self._pages: list[Page] = []

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[f"--lang={self.locale}"],
        )
        # each worker gets its own context (separate cookies/session, shared browser process)
        for i in range(self.n_workers):
            w = 1280 + random.randint(-50, 50)
            h = 900 + random.randint(-30, 30)
            ctx = await self._browser.new_context(
                locale=self.locale,
                viewport={"width": w, "height": h},
            )
            page = await ctx.new_page()
            self._contexts.append(ctx)
            self._pages.append(page)
        return self

    def get_page(self, worker_id: int) -> Page:
        return self._pages[worker_id]

    async def close(self):
        for ctx in self._contexts:
            try:
                await ctx.close()
            except Exception:
                pass
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *exc):
        await self.close()


async def random_delay(min_s: float = 1.0, max_s: float = 3.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_scroll(page: Page, selector: str, n_scrolls: int | None = None):
    """Scroll a feed element with variable speed to look natural."""
    scrolls = n_scrolls or random.randint(3, 5)
    for _ in range(scrolls):
        distance = random.randint(600, 1000)
        await page.evaluate(
            f'document.querySelector(\'{selector}\')?.scrollBy(0, {distance})'
        )
        await asyncio.sleep(random.uniform(0.6, 1.5))


async def check_captcha(page: Page, headed: bool = False, worker_id: int = 0) -> bool:
    """Return True if captcha is detected. In headed mode with low workers, prompt on stderr."""
    title = await page.title()
    url = page.url
    is_captcha = "sorry" in url or "captcha" in title.lower() or "unusual traffic" in title.lower()

    if not is_captcha:
        return False

    if headed:
        print(f"\n[CAPTCHA] Worker {worker_id}: Solve in browser, then press Enter...", flush=True)
        await asyncio.get_event_loop().run_in_executor(None, input)
        await asyncio.sleep(2)
        return False

    print(f"[CAPTCHA] Worker {worker_id}: captcha detected, skipping task", flush=True)
    return True
