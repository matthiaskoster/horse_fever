"""
Base scraper class.

Uses Playwright for browser automation and implements:
- Configurable request delays (rate limiting)
- Exponential-backoff retries
- Random user-agent rotation
- Result normalisation helpers
"""
import asyncio
import logging
import random
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PWTimeout

from rental_scraper.config import EXCHANGE_RATES, SiteConfig

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

VIEWPORT_SIZES = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 800},
]


class BaseScraper(ABC):
    """Abstract base for all site scrapers."""

    def __init__(self, config: SiteConfig):
        self.config = config
        self.site_id = config.site_id
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._last_request: float = 0.0

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self, playwright) -> None:
        self._browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport=random.choice(VIEWPORT_SIZES),
            locale="en-US",
            timezone_id="Asia/Tokyo",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        # Mask automation signals
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        logger.info("[%s] Browser started", self.site_id)

    async def stop(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        logger.info("[%s] Browser stopped", self.site_id)

    # ── Core helpers ─────────────────────────────────────────────────────────

    async def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        wait = self.config.request_delay + random.uniform(0.5, 1.5) - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    async def _new_page(self) -> Page:
        page = await self._context.new_page()
        # Abort image/font/media requests to speed up scraping
        await page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ("image", "media", "font")
            else route.continue_(),
        )
        return page

    async def _goto(self, page: Page, url: str, retries: int = 3) -> bool:
        """Navigate with exponential backoff on failure."""
        await self._rate_limit()
        for attempt in range(retries):
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                if response and response.status < 400:
                    return True
                logger.warning("[%s] HTTP %s for %s", self.site_id, response.status if response else "?", url)
            except PWTimeout:
                logger.warning("[%s] Timeout on %s (attempt %d/%d)", self.site_id, url, attempt + 1, retries)
            except Exception as exc:
                logger.warning("[%s] Error on %s: %s", self.site_id, url, exc)
            if attempt < retries - 1:
                backoff = 2 ** (attempt + 1) + random.uniform(0, 1)
                await asyncio.sleep(backoff)
        return False

    async def _scroll_to_bottom(self, page: Page) -> None:
        """Scroll incrementally to trigger lazy-loading."""
        prev_height = 0
        for _ in range(10):
            height = await page.evaluate("document.body.scrollHeight")
            if height == prev_height:
                break
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.8)
            prev_height = height

    async def _safe_text(self, page: Page, selector: str, default: str = "") -> str:
        try:
            el = await page.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()
        except Exception:
            pass
        return default

    async def _safe_attr(self, page: Page, selector: str, attr: str, default: str = "") -> str:
        try:
            el = await page.query_selector(selector)
            if el:
                val = await el.get_attribute(attr)
                return (val or "").strip()
        except Exception:
            pass
        return default

    # ── Number / unit parsers ────────────────────────────────────────────────

    @staticmethod
    def parse_price(text: str) -> Optional[float]:
        """Extract numeric price from a string (handles commas, ¥, ₫, ฿, etc.)."""
        text = re.sub(r"[^\d.,]", "", text.replace(",", "").replace(".", ""))
        # Japanese man-en (万円) units are handled by site scraper before calling this
        try:
            return float(text) if text else None
        except ValueError:
            return None

    @staticmethod
    def parse_sqm(text: str) -> Optional[float]:
        """Extract sqm value from strings like '52.5m²', '50㎡', '50 sqm'."""
        m = re.search(r"([\d]+\.?[\d]*)\s*(?:m²|㎡|sqm|sq\.?\s*m)", text, re.IGNORECASE)
        if m:
            return float(m.group(1))
        return None

    @staticmethod
    def parse_int(text: str) -> Optional[int]:
        m = re.search(r"\d+", text)
        return int(m.group()) if m else None

    def to_usd(self, amount: Optional[float], currency: Optional[str] = None) -> Optional[float]:
        if amount is None:
            return None
        rate = EXCHANGE_RATES.get(currency or self.config.currency, 1.0)
        return round(amount / rate, 2)

    def price_per_sqm_usd(self, price_usd: Optional[float], size_sqm: Optional[float]) -> Optional[float]:
        if price_usd and size_sqm and size_sqm > 0:
            return round(price_usd / size_sqm, 4)
        return None

    # ── Abstract interface ───────────────────────────────────────────────────

    @abstractmethod
    async def fetch_listings(self) -> List[Dict[str, Any]]:
        """
        Scrape and return a list of normalised listing dicts.
        Each dict should contain at minimum:
            site_id, country, url, title, price_local, currency,
            price_usd, size_sqm, price_per_sqm_usd, city
        """
        ...
