"""
Japan scrapers: SUUMO, HOME'S, CHINTAI, Apartment Japan.
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from rental_scraper.config import SITE_MAP
from rental_scraper.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _yen_to_float(text: str) -> Optional[float]:
    """Convert Japanese price strings: '8.5万円' → 85000, '85,000円' → 85000."""
    text = text.strip()
    # man-en (万円)
    m = re.search(r"([\d.]+)\s*万円?", text)
    if m:
        return float(m.group(1)) * 10_000
    # plain number with optional commas
    cleaned = re.sub(r"[^\d]", "", text)
    return float(cleaned) if cleaned else None


def _parse_floor(text: str) -> Optional[int]:
    m = re.search(r"(\d+)階", text)
    return int(m.group(1)) if m else None


def _parse_age(text: str) -> Optional[int]:
    """Extract construction year: '築10年' or '2010年築' → 2014 or 2010."""
    m = re.search(r"(\d{4})年築", text)
    if m:
        return int(m.group(1))
    m = re.search(r"築(\d+)年", text)
    if m:
        import datetime
        return datetime.date.today().year - int(m.group(1))
    return None


# ── SUUMO ─────────────────────────────────────────────────────────────────────

class SuumoScraper(BaseScraper):
    """
    Scrapes SUUMO rental listings.
    Structure: each <li class="cassetteitem"> contains multiple room rows
    inside <table class="cassetteitem_other">.
    """

    def __init__(self):
        super().__init__(SITE_MAP["suumo"])
        self._search_urls = [
            # Tokyo – popular wards
            "https://suumo.jp/chintai/tokyo/sc_shinjuku/?ar=030&bs=040&ta=13&cb=0.0&ct=9999999&mb=0&mt=9999999&et=9999999&cn=9999999&shkr1=03&shkr2=03&shkr3=03&shkr4=03",
            "https://suumo.jp/chintai/tokyo/sc_shibuya/?ar=030&bs=040&ta=13&cb=0.0&ct=9999999&mb=0&mt=9999999&et=9999999&cn=9999999&shkr1=03&shkr2=03&shkr3=03&shkr4=03",
            "https://suumo.jp/chintai/tokyo/sc_minato/?ar=030&bs=040&ta=13&cb=0.0&ct=9999999&mb=0&mt=9999999&et=9999999&cn=9999999&shkr1=03&shkr2=03&shkr3=03&shkr4=03",
        ]

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        all_listings: List[Dict] = []
        async with async_playwright() as pw:
            await self.start(pw)
            try:
                for base_url in self._search_urls:
                    page = await self._new_page()
                    for page_num in range(1, self.config.max_pages + 1):
                        url = base_url if page_num == 1 else f"{base_url}&page={page_num}"
                        ok = await self._goto(page, url)
                        if not ok:
                            break
                        await self._scroll_to_bottom(page)
                        listings = await self._parse_page(page)
                        if not listings:
                            break
                        all_listings.extend(listings)
                        logger.info("[suumo] page %d → %d listings (total %d)", page_num, len(listings), len(all_listings))
                        # Check for next-page link
                        next_btn = await page.query_selector("a.pagination-parts[rel='next'], .pagination a.is-next")
                        if not next_btn:
                            break
                    await page.close()
            finally:
                await self.stop()
        return all_listings

    async def _parse_page(self, page) -> List[Dict]:
        results = []
        items = await page.query_selector_all("li.cassetteitem")
        for item in items:
            try:
                # Building-level info
                name_el = await item.query_selector(".cassetteitem_content-title")
                building_name = (await name_el.inner_text()).strip() if name_el else ""

                addr_el = await item.query_selector(".cassetteitem_content-adress")
                address = (await addr_el.inner_text()).strip() if addr_el else ""

                nearest_el = await item.query_selector(".cassetteitem_content-transport")
                station = (await nearest_el.inner_text()).strip() if nearest_el else ""

                # Each row = one room in the building
                rows = await item.query_selector_all("tbody tr.js-cassette_link")
                for row in rows:
                    try:
                        listing = await self._parse_room_row(row, building_name, address, station)
                        if listing:
                            results.append(listing)
                    except Exception as e:
                        logger.debug("[suumo] row parse error: %s", e)
            except Exception as e:
                logger.debug("[suumo] item parse error: %s", e)
        return results

    async def _parse_room_row(self, row, building_name: str, address: str, station: str) -> Optional[Dict]:
        # Floor
        floor_el = await row.query_selector("td:nth-child(3)")
        floor_text = (await floor_el.inner_text()).strip() if floor_el else ""

        # Age
        age_el = await row.query_selector("td:nth-child(4)")
        age_text = (await age_el.inner_text()).strip() if age_el else ""

        # Room type
        madori_el = await row.query_selector(".cassetteitem_madori")
        madori = (await madori_el.inner_text()).strip() if madori_el else ""

        # Size
        menseki_el = await row.query_selector(".cassetteitem_menseki")
        menseki_text = (await menseki_el.inner_text()).strip() if menseki_el else ""
        size_sqm = self.parse_sqm(menseki_text)

        # Price (rent)
        price_el = await row.query_selector(".cassetteitem_price--rent")
        price_text = (await price_el.inner_text()).strip() if price_el else ""
        price_local = _yen_to_float(price_text)

        # Detail URL
        link_el = await row.query_selector("a.js-cassette_link_href")
        href = await link_el.get_attribute("href") if link_el else ""
        url = f"https://suumo.jp{href}" if href and href.startswith("/") else href

        # Listing ID from URL
        lid_match = re.search(r"bc=(\d+)", url)
        listing_id = lid_match.group(1) if lid_match else None

        price_usd = self.to_usd(price_local)
        ppsqm = self.price_per_sqm_usd(price_usd, size_sqm)

        # Derive district from address (remove 東京都)
        district = re.sub(r"東京都", "", address).split("　")[0].strip()

        return {
            "site_id": self.site_id,
            "country": self.config.country,
            "listing_id": listing_id,
            "url": url,
            "title": f"{building_name} {madori}".strip(),
            "price_local": price_local,
            "currency": self.config.currency,
            "price_usd": price_usd,
            "size_sqm": size_sqm,
            "price_per_sqm_usd": ppsqm,
            "location": address,
            "city": "Tokyo",
            "district": district,
            "property_type": "apartment",
            "year_built": _parse_age(age_text),
            "floor": _parse_floor(floor_text),
            "amenities": [station] if station else [],
            "raw_data": {
                "building": building_name,
                "address": address,
                "station": station,
                "madori": madori,
                "menseki": menseki_text,
                "floor_text": floor_text,
                "age_text": age_text,
            },
        }


# ── HOME'S ────────────────────────────────────────────────────────────────────

class HomesScraper(BaseScraper):
    """
    Scrapes HOME'S (homes.co.jp) rental listings.
    Listing cards use .mod-mergeBuilding--rent containers.
    """

    def __init__(self):
        super().__init__(SITE_MAP["homes"])
        self._search_urls = [
            "https://www.homes.co.jp/chintai/tokyo/shinjuku-city/list/?searchPattern=1",
            "https://www.homes.co.jp/chintai/tokyo/shibuya-city/list/?searchPattern=1",
            "https://www.homes.co.jp/chintai/tokyo/minato-city/list/?searchPattern=1",
        ]

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        all_listings: List[Dict] = []
        async with async_playwright() as pw:
            await self.start(pw)
            try:
                for base_url in self._search_urls:
                    page = await self._new_page()
                    for page_num in range(1, self.config.max_pages + 1):
                        url = base_url if page_num == 1 else base_url + f"&pn={page_num}"
                        ok = await self._goto(page, url)
                        if not ok:
                            break
                        await self._scroll_to_bottom(page)
                        listings = await self._parse_page(page)
                        if not listings:
                            break
                        all_listings.extend(listings)
                        logger.info("[homes] page %d → %d listings", page_num, len(listings))
                        next_btn = await page.query_selector("a.pagination__next, a[rel='next']")
                        if not next_btn:
                            break
                    await page.close()
            finally:
                await self.stop()
        return all_listings

    async def _parse_page(self, page) -> List[Dict]:
        results = []
        items = await page.query_selector_all(".mod-mergeBuilding--rent, .listItem")
        for item in items:
            try:
                listing = await self._parse_item(item)
                if listing:
                    results.append(listing)
            except Exception as e:
                logger.debug("[homes] item error: %s", e)
        return results

    async def _parse_item(self, item) -> Optional[Dict]:
        name_el = await item.query_selector(".bukkenName, .mod-mergeBuilding__title")
        title = (await name_el.inner_text()).strip() if name_el else ""

        addr_el = await item.query_selector(".bukkenAddress, .mod-mergeBuilding__address")
        address = (await addr_el.inner_text()).strip() if addr_el else ""

        price_el = await item.query_selector(".priceLabel, .mod-mergeBuilding__price")
        price_text = (await price_el.inner_text()).strip() if price_el else ""
        price_local = _yen_to_float(price_text)

        size_el = await item.query_selector(".mensekiLabel, .mod-mergeBuilding__menseki")
        size_text = (await size_el.inner_text()).strip() if size_el else ""
        size_sqm = self.parse_sqm(size_text)

        madori_el = await item.query_selector(".madoriLabel, .mod-mergeBuilding__madori")
        madori = (await madori_el.inner_text()).strip() if madori_el else ""

        link_el = await item.query_selector("a[href]")
        href = await link_el.get_attribute("href") if link_el else ""
        url = f"https://www.homes.co.jp{href}" if href and href.startswith("/") else href

        lid_match = re.search(r"/(\d+)/", url)
        listing_id = lid_match.group(1) if lid_match else None

        price_usd = self.to_usd(price_local)
        ppsqm = self.price_per_sqm_usd(price_usd, size_sqm)
        district = re.sub(r"東京都", "", address).split()[0] if address else ""

        return {
            "site_id": self.site_id,
            "country": self.config.country,
            "listing_id": listing_id,
            "url": url,
            "title": f"{title} {madori}".strip(),
            "price_local": price_local,
            "currency": self.config.currency,
            "price_usd": price_usd,
            "size_sqm": size_sqm,
            "price_per_sqm_usd": ppsqm,
            "location": address,
            "city": "Tokyo",
            "district": district,
            "property_type": "apartment",
            "raw_data": {"address": address, "madori": madori, "size_text": size_text},
        }


# ── CHINTAI ───────────────────────────────────────────────────────────────────

class ChintaiScraper(BaseScraper):
    """
    Scrapes CHINTAI (chintai.net) rental listings.
    """

    def __init__(self):
        super().__init__(SITE_MAP["chintai"])
        self._search_urls = [
            "https://www.chintai.net/tokyo/shinjuku-city/",
            "https://www.chintai.net/tokyo/shibuya-city/",
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
                        logger.info("[chintai] page %d → %d listings", page_num, len(listings))
                        next_btn = await page.query_selector("a.pagination-next, a[aria-label='Next']")
                        if not next_btn:
                            break
                    await page.close()
            finally:
                await self.stop()
        return all_listings

    async def _parse_page(self, page) -> List[Dict]:
        results = []
        items = await page.query_selector_all(".section_list_box, article.property-card")
        for item in items:
            try:
                listing = await self._parse_item(item)
                if listing:
                    results.append(listing)
            except Exception as e:
                logger.debug("[chintai] error: %s", e)
        return results

    async def _parse_item(self, item) -> Optional[Dict]:
        title_el = await item.query_selector("h2, .property-name, .bukken-name")
        title = (await title_el.inner_text()).strip() if title_el else ""

        price_el = await item.query_selector(".price, .chinryo, .rent-price")
        price_text = (await price_el.inner_text()).strip() if price_el else ""
        price_local = _yen_to_float(price_text)

        size_el = await item.query_selector(".menseki, .floor-plan-area, .size")
        size_text = (await size_el.inner_text()).strip() if size_el else ""
        size_sqm = self.parse_sqm(size_text)

        addr_el = await item.query_selector(".address, .location, .access")
        address = (await addr_el.inner_text()).strip() if addr_el else ""

        link_el = await item.query_selector("a[href]")
        href = await link_el.get_attribute("href") if link_el else ""
        url = f"https://www.chintai.net{href}" if href and href.startswith("/") else href

        lid_match = re.search(r"/(\d+)/?$", url)
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
            "city": "Tokyo",
            "property_type": "apartment",
            "raw_data": {"address": address, "size_text": size_text},
        }


# ── Apartment Japan ───────────────────────────────────────────────────────────

class ApartmentJapanScraper(BaseScraper):
    """
    Scrapes Apartment Japan – English-language expat portal.
    """

    def __init__(self):
        super().__init__(SITE_MAP["apartment_japan"])
        self._search_url = "https://www.apartmentjapan.com/en/search?type=apartment&city=tokyo&sort=newest"

    async def fetch_listings(self) -> List[Dict[str, Any]]:
        all_listings: List[Dict] = []
        async with async_playwright() as pw:
            await self.start(pw)
            try:
                page = await self._new_page()
                for page_num in range(1, self.config.max_pages + 1):
                    url = self._search_url if page_num == 1 else f"{self._search_url}&page={page_num}"
                    ok = await self._goto(page, url)
                    if not ok:
                        break
                    await self._scroll_to_bottom(page)
                    listings = await self._parse_page(page)
                    if not listings:
                        break
                    all_listings.extend(listings)
                    logger.info("[apartment_japan] page %d → %d listings", page_num, len(listings))
                    next_btn = await page.query_selector("a.next, a[rel='next']")
                    if not next_btn:
                        break
                await page.close()
            finally:
                await self.stop()
        return all_listings

    async def _parse_page(self, page) -> List[Dict]:
        results = []
        items = await page.query_selector_all(".property-listing, .listing-card, article.property")
        for item in items:
            try:
                listing = await self._parse_item(item)
                if listing:
                    results.append(listing)
            except Exception as e:
                logger.debug("[apartment_japan] error: %s", e)
        return results

    async def _parse_item(self, item) -> Optional[Dict]:
        title_el = await item.query_selector("h2, h3, .property-title, .listing-title")
        title = (await title_el.inner_text()).strip() if title_el else ""

        # English price (e.g. "¥120,000/mo" or "$800/month")
        price_el = await item.query_selector(".price, .rent, .monthly-rent")
        price_text = (await price_el.inner_text()).strip() if price_el else ""

        # Handle USD prices directly
        if "$" in price_text or "USD" in price_text.upper():
            usd_m = re.search(r"[\d,]+", price_text.replace(",", ""))
            price_usd = float(usd_m.group()) if usd_m else None
            price_local = price_usd * self.config.__class__  # not used
            currency = "USD"
        else:
            price_local = _yen_to_float(price_text)
            currency = "JPY"
            price_usd = self.to_usd(price_local, "JPY")

        size_el = await item.query_selector(".size, .area, .sqm, .floor-space")
        size_text = (await size_el.inner_text()).strip() if size_el else ""
        size_sqm = self.parse_sqm(size_text)

        addr_el = await item.query_selector(".location, .address, .area-name")
        address = (await addr_el.inner_text()).strip() if addr_el else ""

        link_el = await item.query_selector("a[href]")
        href = await link_el.get_attribute("href") if link_el else ""
        url = href if href.startswith("http") else f"https://www.apartmentjapan.com{href}"

        lid_match = re.search(r"/(\d+)/?", url)
        listing_id = lid_match.group(1) if lid_match else None

        if price_usd and size_sqm:
            ppsqm = round(price_usd / size_sqm, 4)
        else:
            ppsqm = None

        return {
            "site_id": self.site_id,
            "country": self.config.country,
            "listing_id": listing_id,
            "url": url,
            "title": title,
            "price_local": price_local if currency == "JPY" else price_usd,
            "currency": currency,
            "price_usd": price_usd,
            "size_sqm": size_sqm,
            "price_per_sqm_usd": ppsqm,
            "location": address,
            "city": "Tokyo",
            "property_type": "apartment",
            "raw_data": {"address": address, "size_text": size_text, "price_text": price_text},
        }
