"""
Thailand scrapers: DDproperty, Hipflat, Thai Apartment.
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from rental_scraper.config import SITE_MAP
from rental_scraper.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _thb_to_float(text: str) -> Optional[float]:
    """Convert THB price strings: '฿25,000/mo' → 25000."""
    text = text.strip()
    cleaned = re.sub(r"[^\d]", "", text)
    return float(cleaned) if cleaned else None


def _parse_bedrooms_th(text: str) -> Optional[int]:
    m = re.search(r"(\d+)\s*(?:bed|BR|bedroom)", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    if re.search(r"studio", text, re.IGNORECASE):
        return 0
    return None


# ── DDproperty ────────────────────────────────────────────────────────────────

class DDpropertyScraper(BaseScraper):
    """
    Scrapes DDproperty (ddproperty.com) – English/Thai portal.
    Listing cards: [data-automation-id='listing-card'] or .listing-card
    """

    def __init__(self):
        super().__init__(SITE_MAP["ddproperty"])
        self._search_urls = [
            "https://www.ddproperty.com/en/property-for-rent?market=residential&freetext=Bangkok&listing_type=rent&property_type_code%5B%5D=CONDO",
            "https://www.ddproperty.com/en/property-for-rent?market=residential&freetext=Chiang+Mai&listing_type=rent&property_type_code%5B%5D=CONDO",
        ]

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        all_listings: List[Dict] = []
        async with async_playwright() as pw:
            await self.start(pw)
            try:
                for base_url in self._search_urls:
                    city = "Bangkok" if "Bangkok" in base_url else "Chiang Mai"
                    page = await self._new_page()
                    for page_num in range(1, self.config.max_pages + 1):
                        url = base_url if page_num == 1 else f"{base_url}&page={page_num}"
                        ok = await self._goto(page, url)
                        if not ok:
                            break
                        # DDproperty is JS-heavy; wait for card elements
                        try:
                            await page.wait_for_selector(
                                "[data-automation-id='listing-card'], .listing-card, article.listing",
                                timeout=15_000,
                            )
                        except Exception:
                            pass
                        await self._scroll_to_bottom(page)
                        listings = await self._parse_page(page, city)
                        if not listings:
                            break
                        all_listings.extend(listings)
                        logger.info("[ddproperty] %s p%d → %d listings", city, page_num, len(listings))
                        next_btn = await page.query_selector("a[data-automation-id='pagination-next'], a.btn-next, a[rel='next']")
                        if not next_btn:
                            break
                    await page.close()
            finally:
                await self.stop()
        return all_listings

    async def _parse_page(self, page, city: str) -> List[Dict]:
        results = []
        selectors = [
            "[data-automation-id='listing-card']",
            ".listing-card",
            "article.listing",
            ".property-card",
        ]
        items = []
        for sel in selectors:
            items = await page.query_selector_all(sel)
            if items:
                break
        for item in items:
            try:
                listing = await self._parse_item(item, city)
                if listing:
                    results.append(listing)
            except Exception as e:
                logger.debug("[ddproperty] error: %s", e)
        return results

    async def _parse_item(self, item, city: str) -> Optional[Dict]:
        title_el = await item.query_selector("[data-automation-id='listing-title'], .listing-title, h2, h3")
        title = (await title_el.inner_text()).strip() if title_el else ""

        price_el = await item.query_selector("[data-automation-id='listing-price'], .price, .listing-price")
        price_text = (await price_el.inner_text()).strip() if price_el else ""
        price_local = _thb_to_float(price_text)

        size_el = await item.query_selector("[data-automation-id='listing-floorarea'], .floor-area, .size, [class*='area']")
        size_text = (await size_el.inner_text()).strip() if size_el else ""
        size_sqm = self.parse_sqm(size_text)

        beds_el = await item.query_selector("[data-automation-id='listing-bed'], .bedroom-count, [class*='bed']")
        beds_text = (await beds_el.inner_text()).strip() if beds_el else ""
        bedrooms = _parse_bedrooms_th(beds_text) if beds_text else self.parse_int(beds_text)

        addr_el = await item.query_selector("[data-automation-id='listing-location'], .listing-location, .location")
        address = (await addr_el.inner_text()).strip() if addr_el else ""

        link_el = await item.query_selector("a[href]")
        href = await link_el.get_attribute("href") if link_el else ""
        url = href if href.startswith("http") else f"https://www.ddproperty.com{href}"

        lid_match = re.search(r"-(\d+)\.html", url) or re.search(r"/(\d+)/?$", url)
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
            "bedrooms": bedrooms,
            "location": address,
            "city": city,
            "district": address.split(",")[0].strip() if address else "",
            "property_type": "condo",
            "raw_data": {"price_text": price_text, "size_text": size_text, "address": address},
        }


# ── Hipflat ───────────────────────────────────────────────────────────────────

class HipflatScraper(BaseScraper):
    """
    Scrapes Hipflat – English Thailand property portal.
    """

    def __init__(self):
        super().__init__(SITE_MAP["hipflat"])
        self._search_urls = [
            "https://www.hipflat.com/en/search?listing_type=rent&location=Bangkok&property_types=condo",
            "https://www.hipflat.com/en/search?listing_type=rent&location=Chiang+Mai&property_types=condo",
        ]

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        all_listings: List[Dict] = []
        async with async_playwright() as pw:
            await self.start(pw)
            try:
                for base_url in self._search_urls:
                    city = "Bangkok" if "Bangkok" in base_url else "Chiang Mai"
                    page = await self._new_page()
                    for page_num in range(1, self.config.max_pages + 1):
                        url = base_url if page_num == 1 else f"{base_url}&page={page_num}"
                        ok = await self._goto(page, url)
                        if not ok:
                            break
                        try:
                            await page.wait_for_selector(".listing-card, .property-card, article", timeout=15_000)
                        except Exception:
                            pass
                        await self._scroll_to_bottom(page)
                        listings = await self._parse_page(page, city)
                        if not listings:
                            break
                        all_listings.extend(listings)
                        logger.info("[hipflat] %s p%d → %d listings", city, page_num, len(listings))
                        next_btn = await page.query_selector("a.pagination-next, a[rel='next'], button[aria-label='Next']")
                        if not next_btn:
                            break
                    await page.close()
            finally:
                await self.stop()
        return all_listings

    async def _parse_page(self, page, city: str) -> List[Dict]:
        results = []
        items = await page.query_selector_all(".listing-card, .property-card, article.unit-listing")
        for item in items:
            try:
                listing = await self._parse_item(item, city)
                if listing:
                    results.append(listing)
            except Exception as e:
                logger.debug("[hipflat] error: %s", e)
        return results

    async def _parse_item(self, item, city: str) -> Optional[Dict]:
        title_el = await item.query_selector("h2, h3, .listing-title, .property-name")
        title = (await title_el.inner_text()).strip() if title_el else ""

        price_el = await item.query_selector(".price, .listing-price, .rent-amount")
        price_text = (await price_el.inner_text()).strip() if price_el else ""
        price_local = _thb_to_float(price_text)

        size_el = await item.query_selector(".area, .size, .sqm-size, [class*='area']")
        size_text = (await size_el.inner_text()).strip() if size_el else ""
        size_sqm = self.parse_sqm(size_text)

        beds_el = await item.query_selector(".bedrooms, .beds, [class*='bed']")
        beds_text = (await beds_el.inner_text()).strip() if beds_el else ""
        bedrooms = _parse_bedrooms_th(beds_text)

        addr_el = await item.query_selector(".location, .address, .neighbourhood")
        address = (await addr_el.inner_text()).strip() if addr_el else ""

        link_el = await item.query_selector("a[href]")
        href = await link_el.get_attribute("href") if link_el else ""
        url = href if href.startswith("http") else f"https://www.hipflat.com{href}"

        lid_match = re.search(r"/([a-z0-9-]+)/?$", url)
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
            "bedrooms": bedrooms,
            "location": address,
            "city": city,
            "property_type": "condo",
            "raw_data": {"price_text": price_text, "size_text": size_text},
        }


# ── Thai Apartment ────────────────────────────────────────────────────────────

class ThaiApartmentScraper(BaseScraper):
    """
    Scrapes thai-apartment.com – rental-focused Thai portal.
    """

    def __init__(self):
        super().__init__(SITE_MAP["thai_apartment"])
        self._search_url = "https://www.thai-apartment.com/apartments-for-rent/bangkok"

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        all_listings: List[Dict] = []
        async with async_playwright() as pw:
            await self.start(pw)
            try:
                page = await self._new_page()
                for page_num in range(1, self.config.max_pages + 1):
                    url = self._search_url if page_num == 1 else f"{self._search_url}?page={page_num}"
                    ok = await self._goto(page, url)
                    if not ok:
                        break
                    await self._scroll_to_bottom(page)
                    listings = await self._parse_page(page)
                    if not listings:
                        break
                    all_listings.extend(listings)
                    logger.info("[thai_apartment] p%d → %d listings", page_num, len(listings))
                    next_btn = await page.query_selector("a.next, a[rel='next'], .pagination a:last-child")
                    if not next_btn:
                        break
                await page.close()
            finally:
                await self.stop()
        return all_listings

    async def _parse_page(self, page) -> List[Dict]:
        results = []
        items = await page.query_selector_all(".property-item, .apt-listing, article.apartment")
        for item in items:
            try:
                listing = await self._parse_item(item)
                if listing:
                    results.append(listing)
            except Exception as e:
                logger.debug("[thai_apartment] error: %s", e)
        return results

    async def _parse_item(self, item) -> Optional[Dict]:
        title_el = await item.query_selector("h2, h3, .property-name, .apt-name")
        title = (await title_el.inner_text()).strip() if title_el else ""

        price_el = await item.query_selector(".price, .rent, .monthly-price")
        price_text = (await price_el.inner_text()).strip() if price_el else ""
        price_local = _thb_to_float(price_text)

        size_el = await item.query_selector(".area, .size, [class*='sqm'], [class*='area']")
        size_text = (await size_el.inner_text()).strip() if size_el else ""
        size_sqm = self.parse_sqm(size_text)

        addr_el = await item.query_selector(".address, .location, .district")
        address = (await addr_el.inner_text()).strip() if addr_el else ""

        link_el = await item.query_selector("a[href]")
        href = await link_el.get_attribute("href") if link_el else ""
        url = href if href.startswith("http") else f"https://www.thai-apartment.com{href}"

        lid_match = re.search(r"/([^/]+)/?$", url)
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
            "city": "Bangkok",
            "property_type": "apartment",
            "raw_data": {"price_text": price_text, "size_text": size_text},
        }
