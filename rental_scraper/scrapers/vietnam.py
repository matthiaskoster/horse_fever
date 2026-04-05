"""
Vietnam scrapers: Batdongsan, Chotot, Muaban, Living in Vietnam.
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from rental_scraper.config import SITE_MAP
from rental_scraper.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _vnd_to_float(text: str) -> Optional[float]:
    """Convert VND strings: '15 triệu/tháng' → 15_000_000, '500,000,000' → 500000000."""
    text = text.strip().lower()
    # triệu = million
    m = re.search(r"([\d.,]+)\s*tri[eệ]u", text)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000_000
    # tỷ = billion
    m = re.search(r"([\d.,]+)\s*t[yỷ]", text)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000_000_000
    # plain digits
    cleaned = re.sub(r"[^\d]", "", text)
    return float(cleaned) if cleaned else None


def _parse_sqm_vn(text: str) -> Optional[float]:
    """Vietnamese sqm: '50m²', '50 m2'."""
    m = re.search(r"([\d]+\.?[\d]*)\s*m[²2]", text, re.IGNORECASE)
    return float(m.group(1)) if m else None


# ── Batdongsan ────────────────────────────────────────────────────────────────

class BatdongsanScraper(BaseScraper):
    """
    Scrapes batdongsan.com.vn – Vietnam's largest property portal.
    Listing cards: .re__card-full or .js__card
    """

    def __init__(self):
        super().__init__(SITE_MAP["batdongsan"])
        self._search_urls = [
            "https://batdongsan.com.vn/cho-thue-can-ho-chung-cu-ha-noi",
            "https://batdongsan.com.vn/cho-thue-can-ho-chung-cu-tp-hcm",
        ]

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        all_listings: List[Dict] = []
        async with async_playwright() as pw:
            await self.start(pw)
            try:
                for base_url in self._search_urls:
                    city = "Hanoi" if "ha-noi" in base_url else "Ho Chi Minh City"
                    page = await self._new_page()
                    for page_num in range(1, self.config.max_pages + 1):
                        url = base_url if page_num == 1 else f"{base_url}/p{page_num}"
                        ok = await self._goto(page, url)
                        if not ok:
                            break
                        await self._scroll_to_bottom(page)
                        listings = await self._parse_page(page, city)
                        if not listings:
                            break
                        all_listings.extend(listings)
                        logger.info("[batdongsan] %s p%d → %d listings", city, page_num, len(listings))
                        next_el = await page.query_selector("a.re__pagination-icon--next, a[data-page='next']")
                        if not next_el:
                            break
                    await page.close()
            finally:
                await self.stop()
        return all_listings

    async def _parse_page(self, page, city: str) -> List[Dict]:
        results = []
        items = await page.query_selector_all(".re__card-full, article.js__card")
        for item in items:
            try:
                listing = await self._parse_item(item, city)
                if listing:
                    results.append(listing)
            except Exception as e:
                logger.debug("[batdongsan] error: %s", e)
        return results

    async def _parse_item(self, item, city: str) -> Optional[Dict]:
        title_el = await item.query_selector(".re__card-title, h3")
        title = (await title_el.inner_text()).strip() if title_el else ""

        price_el = await item.query_selector(".re__card-config-price, .price")
        price_text = (await price_el.inner_text()).strip() if price_el else ""
        price_local = _vnd_to_float(price_text)

        size_el = await item.query_selector(".re__card-config-area, .area")
        size_text = (await size_el.inner_text()).strip() if size_el else ""
        size_sqm = _parse_sqm_vn(size_text) or self.parse_sqm(size_text)

        addr_el = await item.query_selector(".re__card-location, .location")
        address = (await addr_el.inner_text()).strip() if addr_el else ""

        link_el = await item.query_selector("a[href]")
        href = await link_el.get_attribute("href") if link_el else ""
        url = href if href.startswith("http") else f"https://batdongsan.com.vn{href}"

        lid_match = re.search(r"-(\d+)\.html", url) or re.search(r"/(\d+)/?$", url)
        listing_id = lid_match.group(1) if lid_match else None

        # View count as popularity signal (if shown)
        views_el = await item.query_selector(".re__card-stat-view, .view-count")
        views_text = (await views_el.inner_text()).strip() if views_el else ""
        views = self.parse_int(views_text)
        popularity = min(views / 1000.0, 1.0) if views else None

        price_usd = self.to_usd(price_local)
        ppsqm = self.price_per_sqm_usd(price_usd, size_sqm)

        return {
            "site_id": self.site_id,
            "country": self.config.country,
            "listing_id": listing_id,
            "url": url,
            "title": title,
            "price_local": price_local,
            "currency": self.config.currency,
            "price_usd": price_usd,
            "size_sqm": size_sqm,
            "price_per_sqm_usd": ppsqm,
            "location": address,
            "city": city,
            "property_type": "apartment",
            "popularity_score": popularity,
            "raw_data": {"address": address, "price_text": price_text, "size_text": size_text},
        }


# ── Chotot ────────────────────────────────────────────────────────────────────

class ChototScraper(BaseScraper):
    """
    Scrapes cho.tot.vn – broad Vietnamese classifieds.
    Uses JSON API: /v2/public/products?...
    """

    def __init__(self):
        super().__init__(SITE_MAP["chotot"])
        # Chotot exposes a public API; prefer it over HTML scraping
        self._api_url = "https://gateway.chotot.com/v2/public/ad-listing?cg=1000&rgn=93&o={offset}&st=u,s&limit=20"
        self._html_url = "https://cho.tot.vn/mua-ban-bat-dong-san?cg=1000&rgn=93"

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        all_listings: List[Dict] = []
        async with async_playwright() as pw:
            await self.start(pw)
            try:
                page = await self._new_page()
                for page_num in range(self.config.max_pages):
                    offset = page_num * 20
                    # Try API first via fetch()
                    api_url = self._api_url.format(offset=offset)
                    ok = await self._goto(page, self._html_url if page_num == 0 else f"{self._html_url}&page={page_num+1}")
                    if not ok:
                        break
                    await self._scroll_to_bottom(page)
                    listings = await self._parse_page(page)
                    if not listings:
                        break
                    all_listings.extend(listings)
                    logger.info("[chotot] p%d → %d listings", page_num + 1, len(listings))
            finally:
                await self.stop()
        return all_listings

    async def _parse_page(self, page) -> List[Dict]:
        results = []
        items = await page.query_selector_all("article.aditem-main, .aditem, li[data-adid]")
        for item in items:
            try:
                listing = await self._parse_item(item)
                if listing:
                    results.append(listing)
            except Exception as e:
                logger.debug("[chotot] error: %s", e)
        return results

    async def _parse_item(self, item) -> Optional[Dict]:
        title_el = await item.query_selector("h2, .title, .aditem-title")
        title = (await title_el.inner_text()).strip() if title_el else ""

        price_el = await item.query_selector(".price, .aditem-price, [class*='price']")
        price_text = (await price_el.inner_text()).strip() if price_el else ""
        price_local = _vnd_to_float(price_text)

        size_el = await item.query_selector(".area, .aditem-area, [class*='area']")
        size_text = (await size_el.inner_text()).strip() if size_el else ""
        size_sqm = _parse_sqm_vn(size_text)

        addr_el = await item.query_selector(".location, .aditem-location, [class*='location']")
        address = (await addr_el.inner_text()).strip() if addr_el else ""

        link_el = await item.query_selector("a[href]")
        href = await link_el.get_attribute("href") if link_el else ""
        url = href if href.startswith("http") else f"https://cho.tot.vn{href}"

        lid_match = re.search(r"/(\d+)\.htm", url) or re.search(r"adid=(\d+)", url)
        listing_id = lid_match.group(1) if lid_match else None

        price_usd = self.to_usd(price_local)
        ppsqm = self.price_per_sqm_usd(price_usd, size_sqm)

        return {
            "site_id": self.site_id,
            "country": self.config.country,
            "listing_id": listing_id,
            "url": url,
            "title": title,
            "price_local": price_local,
            "currency": self.config.currency,
            "price_usd": price_usd,
            "size_sqm": size_sqm,
            "price_per_sqm_usd": ppsqm,
            "location": address,
            "city": "Ho Chi Minh City",
            "property_type": "apartment",
            "raw_data": {"price_text": price_text, "size_text": size_text},
        }


# ── Muaban ────────────────────────────────────────────────────────────────────

class MuabanScraper(BaseScraper):
    """
    Scrapes muaban.net – Vietnamese general classifieds.
    """

    def __init__(self):
        super().__init__(SITE_MAP["muaban"])
        self._search_urls = [
            "https://muaban.net/bat-dong-san/cho-thue-can-ho",
            "https://muaban.net/bat-dong-san/cho-thue-nha",
        ]

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        all_listings: List[Dict] = []
        async with async_playwright() as pw:
            await self.start(pw)
            try:
                for base_url in self._search_urls:
                    page = await self._new_page()
                    for page_num in range(1, self.config.max_pages + 1):
                        url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
                        ok = await self._goto(page, url)
                        if not ok:
                            break
                        await self._scroll_to_bottom(page)
                        listings = await self._parse_page(page)
                        if not listings:
                            break
                        all_listings.extend(listings)
                        logger.info("[muaban] p%d → %d listings", page_num, len(listings))
                        next_btn = await page.query_selector("a.next-page, a[rel='next']")
                        if not next_btn:
                            break
                    await page.close()
            finally:
                await self.stop()
        return all_listings

    async def _parse_page(self, page) -> List[Dict]:
        results = []
        items = await page.query_selector_all(".ad-item, .item-listing, article.post")
        for item in items:
            try:
                listing = await self._parse_item(item)
                if listing:
                    results.append(listing)
            except Exception as e:
                logger.debug("[muaban] error: %s", e)
        return results

    async def _parse_item(self, item) -> Optional[Dict]:
        title_el = await item.query_selector("h2, h3, .title")
        title = (await title_el.inner_text()).strip() if title_el else ""

        price_el = await item.query_selector(".price, .gia")
        price_text = (await price_el.inner_text()).strip() if price_el else ""
        price_local = _vnd_to_float(price_text)

        size_el = await item.query_selector(".area, .dien-tich")
        size_text = (await size_el.inner_text()).strip() if size_el else ""
        size_sqm = _parse_sqm_vn(size_text)

        addr_el = await item.query_selector(".location, .dia-chi, .address")
        address = (await addr_el.inner_text()).strip() if addr_el else ""

        link_el = await item.query_selector("a[href]")
        href = await link_el.get_attribute("href") if link_el else ""
        url = href if href.startswith("http") else f"https://muaban.net{href}"

        lid_match = re.search(r"-(\d+)/?$", url)
        listing_id = lid_match.group(1) if lid_match else None

        price_usd = self.to_usd(price_local)
        ppsqm = self.price_per_sqm_usd(price_usd, size_sqm)

        return {
            "site_id": self.site_id,
            "country": self.config.country,
            "listing_id": listing_id,
            "url": url,
            "title": title,
            "price_local": price_local,
            "currency": self.config.currency,
            "price_usd": price_usd,
            "size_sqm": size_sqm,
            "price_per_sqm_usd": ppsqm,
            "location": address,
            "city": "Ho Chi Minh City",
            "property_type": "apartment",
            "raw_data": {"price_text": price_text, "size_text": size_text},
        }


# ── Living in Vietnam ─────────────────────────────────────────────────────────

class LivingInVietnamScraper(BaseScraper):
    """
    Scrapes livinginvietnam.com – expat-oriented English rental portal.
    Prices typically in USD.
    """

    def __init__(self):
        super().__init__(SITE_MAP["living_in_vietnam"])
        self._search_url = "https://www.livinginvietnam.com/properties/for-rent/"

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        all_listings: List[Dict] = []
        async with async_playwright() as pw:
            await self.start(pw)
            try:
                page = await self._new_page()
                for page_num in range(1, self.config.max_pages + 1):
                    url = self._search_url if page_num == 1 else f"{self._search_url}page/{page_num}/"
                    ok = await self._goto(page, url)
                    if not ok:
                        break
                    await self._scroll_to_bottom(page)
                    listings = await self._parse_page(page)
                    if not listings:
                        break
                    all_listings.extend(listings)
                    logger.info("[living_in_vietnam] p%d → %d listings", page_num, len(listings))
                    next_btn = await page.query_selector("a.next, a[rel='next'], .pagination-next")
                    if not next_btn:
                        break
                await page.close()
            finally:
                await self.stop()
        return all_listings

    async def _parse_page(self, page) -> List[Dict]:
        results = []
        items = await page.query_selector_all("article.property, .listing-item, .property-card")
        for item in items:
            try:
                listing = await self._parse_item(item)
                if listing:
                    results.append(listing)
            except Exception as e:
                logger.debug("[living_in_vietnam] error: %s", e)
        return results

    async def _parse_item(self, item) -> Optional[Dict]:
        title_el = await item.query_selector("h2, h3, .property-title")
        title = (await title_el.inner_text()).strip() if title_el else ""

        price_el = await item.query_selector(".price, .rent-price, .monthly-rent")
        price_text = (await price_el.inner_text()).strip() if price_el else ""

        # Prices are USD
        usd_m = re.search(r"[\d,]+", price_text.replace(",", ""))
        price_usd = float(usd_m.group()) if usd_m else None
        price_local = price_usd  # site quotes in USD

        size_el = await item.query_selector(".area, .size, .sqm, [class*='area']")
        size_text = (await size_el.inner_text()).strip() if size_el else ""
        size_sqm = self.parse_sqm(size_text)

        bedrooms_el = await item.query_selector(".bedrooms, .beds, [class*='bed']")
        bedrooms_text = (await bedrooms_el.inner_text()).strip() if bedrooms_el else ""
        bedrooms = self.parse_int(bedrooms_text)

        addr_el = await item.query_selector(".location, .address, .district")
        address = (await addr_el.inner_text()).strip() if addr_el else ""

        link_el = await item.query_selector("a[href]")
        href = await link_el.get_attribute("href") if link_el else ""
        url = href if href.startswith("http") else f"https://www.livinginvietnam.com{href}"

        lid_match = re.search(r"/([^/]+)/?$", url)
        listing_id = lid_match.group(1) if lid_match else None

        ppsqm = self.price_per_sqm_usd(price_usd, size_sqm)

        return {
            "site_id": self.site_id,
            "country": self.config.country,
            "listing_id": listing_id,
            "url": url,
            "title": title,
            "price_local": price_local,
            "currency": "USD",
            "price_usd": price_usd,
            "size_sqm": size_sqm,
            "price_per_sqm_usd": ppsqm,
            "bedrooms": bedrooms,
            "location": address,
            "city": "Ho Chi Minh City",
            "property_type": "apartment",
            "raw_data": {"price_text": price_text, "size_text": size_text},
        }
