"""
Site registry and global configuration for the rental scraper system.
"""
from dataclasses import dataclass, field
from typing import List, Optional


# Currency exchange rates to USD (approximate)
EXCHANGE_RATES = {
    "JPY": 150.0,
    "VND": 24000.0,
    "THB": 35.0,
    "USD": 1.0,
}


@dataclass
class SiteConfig:
    site_id: str
    country: str
    name: str
    base_url: str
    category: str
    local_or_expat: str       # "local", "expat", "local+expat"
    english_friendly: str     # "friendly", "partial", "limited"
    scale: str                # "large", "very_large", "moderate"
    currency: str
    priority: int             # 1 = highest; used to schedule scraping order
    popular_url: str          # URL for popular/featured/newest listings
    notes: str = ""
    request_delay: float = 2.0   # seconds between requests
    max_pages: int = 5


SITES: List[SiteConfig] = [
    # ── Japan ────────────────────────────────────────────────────────────────
    SiteConfig(
        site_id="suumo",
        country="Japan",
        name="SUUMO",
        base_url="https://suumo.jp",
        category="main rental portal",
        local_or_expat="local",
        english_friendly="limited",
        scale="very_large",
        currency="JPY",
        priority=1,
        popular_url="https://suumo.jp/chintai/tokyo/sc_shinjuku/?ar=030&bs=040&ta=13&cb=0.0&ct=9999999&mb=0&mt=9999999&et=9999999&cn=9999999&shkr1=03&shkr2=03&shkr3=03&shkr4=03",
        notes="Japan's biggest rental search site. Best first stop.",
        request_delay=3.0,
    ),
    SiteConfig(
        site_id="homes",
        country="Japan",
        name="HOME'S",
        base_url="https://www.homes.co.jp",
        category="main rental portal",
        local_or_expat="local",
        english_friendly="limited",
        scale="very_large",
        currency="JPY",
        priority=2,
        popular_url="https://www.homes.co.jp/chintai/tokyo/list/?searchPattern=1",
        notes="Strong national coverage.",
        request_delay=3.0,
    ),
    SiteConfig(
        site_id="chintai",
        country="Japan",
        name="CHINTAI",
        base_url="https://www.chintai.net",
        category="main rental portal",
        local_or_expat="local",
        english_friendly="limited",
        scale="large",
        currency="JPY",
        priority=3,
        popular_url="https://www.chintai.net/tokyo/",
        notes="Useful backup to SUUMO.",
        request_delay=2.5,
    ),
    SiteConfig(
        site_id="apartment_japan",
        country="Japan",
        name="Apartment Japan",
        base_url="https://www.apartmentjapan.com",
        category="expat/booking portal",
        local_or_expat="expat",
        english_friendly="friendly",
        scale="small",
        currency="JPY",
        priority=4,
        popular_url="https://www.apartmentjapan.com/en/search?type=apartment&city=tokyo",
        notes="More foreigner-friendly; English interface.",
        request_delay=2.0,
    ),
    # ── Vietnam ──────────────────────────────────────────────────────────────
    SiteConfig(
        site_id="batdongsan",
        country="Vietnam",
        name="Batdongsan",
        base_url="https://batdongsan.com.vn",
        category="main property portal",
        local_or_expat="local",
        english_friendly="limited",
        scale="very_large",
        currency="VND",
        priority=5,
        popular_url="https://batdongsan.com.vn/cho-thue-can-ho-chung-cu",
        notes="Popular among locals for rentals and sales.",
        request_delay=2.5,
    ),
    SiteConfig(
        site_id="chotot",
        country="Vietnam",
        name="Chotot",
        base_url="https://cho.tot.vn",
        category="classifieds marketplace",
        local_or_expat="local",
        english_friendly="partial",
        scale="very_large",
        currency="VND",
        priority=6,
        popular_url="https://cho.tot.vn/mua-ban-bat-dong-san?cg=1000&rgn=93&o=1",
        notes="Broad classifieds; direct-owner listings.",
        request_delay=2.0,
    ),
    SiteConfig(
        site_id="muaban",
        country="Vietnam",
        name="Muaban",
        base_url="https://muaban.net",
        category="classifieds marketplace",
        local_or_expat="local",
        english_friendly="limited",
        scale="large",
        currency="VND",
        priority=7,
        popular_url="https://muaban.net/bat-dong-san/cho-thue-can-ho",
        notes="General classifieds; complement to Batdongsan.",
        request_delay=2.0,
    ),
    SiteConfig(
        site_id="living_in_vietnam",
        country="Vietnam",
        name="Living in Vietnam",
        base_url="https://www.livinginvietnam.com",
        category="expat/rental service",
        local_or_expat="expat",
        english_friendly="friendly",
        scale="small",
        currency="USD",
        priority=8,
        popular_url="https://www.livinginvietnam.com/properties/for-rent/",
        notes="Expat-oriented; English interface.",
        request_delay=2.0,
    ),
    # ── Thailand ─────────────────────────────────────────────────────────────
    SiteConfig(
        site_id="ddproperty",
        country="Thailand",
        name="DDproperty",
        base_url="https://www.ddproperty.com",
        category="main property portal",
        local_or_expat="local+expat",
        english_friendly="friendly",
        scale="very_large",
        currency="THB",
        priority=9,
        popular_url="https://www.ddproperty.com/en/property-for-rent?market=residential&freetext=Bangkok&listing_type=rent",
        notes="Largest Thai portal; good English interface.",
        request_delay=2.5,
    ),
    SiteConfig(
        site_id="hipflat",
        country="Thailand",
        name="Hipflat",
        base_url="https://www.hipflat.com",
        category="main property portal",
        local_or_expat="local+expat",
        english_friendly="friendly",
        scale="very_large",
        currency="THB",
        priority=10,
        popular_url="https://www.hipflat.com/en/search?listing_type=rent&location=Bangkok",
        notes="Strong search tools; lots of rentals.",
        request_delay=2.5,
    ),
    SiteConfig(
        site_id="thai_apartment",
        country="Thailand",
        name="Thai Apartment",
        base_url="https://www.thai-apartment.com",
        category="apartment rental site",
        local_or_expat="local+expat",
        english_friendly="partial",
        scale="moderate",
        currency="THB",
        priority=11,
        popular_url="https://www.thai-apartment.com/search?type=rent&city=Bangkok",
        notes="Rental-focused backup site.",
        request_delay=2.0,
    ),
]

# Quick lookup by site_id
SITE_MAP = {s.site_id: s for s in SITES}
