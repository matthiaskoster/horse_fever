"""
SQLite storage layer for rental listings.
"""
import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "rentals.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS listings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id           TEXT NOT NULL,
    country           TEXT NOT NULL,
    listing_id        TEXT,
    url               TEXT,
    title             TEXT,
    price_local       REAL,
    currency          TEXT,
    price_usd         REAL,
    size_sqm          REAL,
    price_per_sqm_usd REAL,
    bedrooms          INTEGER,
    bathrooms         INTEGER,
    location          TEXT,
    city              TEXT,
    district          TEXT,
    property_type     TEXT,
    is_furnished      INTEGER,
    year_built        INTEGER,
    floor             INTEGER,
    description       TEXT,
    amenities         TEXT,      -- JSON array
    images            TEXT,      -- JSON array of URLs
    popularity_score  REAL,      -- site-relative score 0-1 if available
    value_grade       TEXT,      -- S/A/B/C/D
    value_score       REAL,      -- z-score relative to local market
    scraped_at        TEXT NOT NULL,
    raw_data          TEXT       -- full JSON from site
);

CREATE INDEX IF NOT EXISTS idx_listings_site   ON listings(site_id);
CREATE INDEX IF NOT EXISTS idx_listings_country ON listings(country);
CREATE INDEX IF NOT EXISTS idx_listings_grade   ON listings(value_grade);
CREATE INDEX IF NOT EXISTS idx_listings_city    ON listings(city);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id     TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT,       -- "running", "success", "partial", "failed"
    listings_found INTEGER DEFAULT 0,
    listings_new   INTEGER DEFAULT 0,
    error_msg   TEXT
);
"""


class Database:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()
        logger.info("Database connected: %s", self.db_path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Listings ────────────────────────────────────────────────────────────

    def upsert_listing(self, listing: Dict[str, Any]) -> bool:
        """Insert or update a listing. Returns True if it was new."""
        now = datetime.utcnow().isoformat()
        listing.setdefault("scraped_at", now)

        # Serialize list fields
        for field in ("amenities", "images"):
            v = listing.get(field)
            if isinstance(v, list):
                listing[field] = json.dumps(v, ensure_ascii=False)

        if isinstance(listing.get("raw_data"), dict):
            listing["raw_data"] = json.dumps(listing["raw_data"], ensure_ascii=False)

        # Check for existing record by (site_id, listing_id)
        existing_id = None
        if listing.get("listing_id"):
            row = self._conn.execute(
                "SELECT id FROM listings WHERE site_id=? AND listing_id=?",
                (listing["site_id"], listing["listing_id"]),
            ).fetchone()
            if row:
                existing_id = row["id"]
        elif listing.get("url"):
            row = self._conn.execute(
                "SELECT id FROM listings WHERE site_id=? AND url=?",
                (listing["site_id"], listing["url"]),
            ).fetchone()
            if row:
                existing_id = row["id"]

        columns = [
            "site_id", "country", "listing_id", "url", "title",
            "price_local", "currency", "price_usd", "size_sqm",
            "price_per_sqm_usd", "bedrooms", "bathrooms", "location",
            "city", "district", "property_type", "is_furnished",
            "year_built", "floor", "description", "amenities", "images",
            "popularity_score", "value_grade", "value_score",
            "scraped_at", "raw_data",
        ]
        values = [listing.get(c) for c in columns]

        if existing_id:
            set_clause = ", ".join(f"{c}=?" for c in columns)
            self._conn.execute(
                f"UPDATE listings SET {set_clause} WHERE id=?",
                values + [existing_id],
            )
            self._conn.commit()
            return False
        else:
            placeholders = ", ".join("?" * len(columns))
            self._conn.execute(
                f"INSERT INTO listings ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            self._conn.commit()
            return True

    def get_listings(
        self,
        country: Optional[str] = None,
        site_id: Optional[str] = None,
        city: Optional[str] = None,
        min_size_sqm: Optional[float] = None,
        max_price_usd: Optional[float] = None,
        grade: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        where = []
        params = []
        if country:
            where.append("country=?"); params.append(country)
        if site_id:
            where.append("site_id=?"); params.append(site_id)
        if city:
            where.append("city LIKE ?"); params.append(f"%{city}%")
        if min_size_sqm is not None:
            where.append("size_sqm>=?"); params.append(min_size_sqm)
        if max_price_usd is not None:
            where.append("price_usd<=?"); params.append(max_price_usd)
        if grade:
            where.append("value_grade=?"); params.append(grade)

        sql = "SELECT * FROM listings"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY scraped_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_market_stats(self, country: str, city: Optional[str] = None) -> Dict[str, Any]:
        """Return price_per_sqm_usd stats for grading."""
        params: list = [country]
        city_filter = ""
        if city:
            city_filter = " AND city LIKE ?"
            params.append(f"%{city}%")
        sql = f"""
            SELECT
                COUNT(*)                            AS n,
                AVG(price_per_sqm_usd)              AS mean,
                MIN(price_per_sqm_usd)              AS min,
                MAX(price_per_sqm_usd)              AS max
            FROM listings
            WHERE country=?{city_filter}
              AND price_per_sqm_usd IS NOT NULL
              AND price_per_sqm_usd > 0
        """
        row = self._conn.execute(sql, params).fetchone()
        if not row or row["n"] < 5:
            return {}
        vals = [
            r["price_per_sqm_usd"]
            for r in self._conn.execute(
                f"SELECT price_per_sqm_usd FROM listings WHERE country=?{city_filter}"
                " AND price_per_sqm_usd IS NOT NULL AND price_per_sqm_usd > 0",
                params,
            ).fetchall()
        ]
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = variance ** 0.5
        return {"n": len(vals), "mean": mean, "std": std, "min": row["min"], "max": row["max"]}

    # ── Scrape runs ──────────────────────────────────────────────────────────

    def start_run(self, site_id: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO scrape_runs (site_id, started_at, status) VALUES (?,?,?)",
            (site_id, datetime.utcnow().isoformat(), "running"),
        )
        self._conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, status: str, listings_found: int, listings_new: int, error_msg: str = "") -> None:
        self._conn.execute(
            "UPDATE scrape_runs SET finished_at=?, status=?, listings_found=?, listings_new=?, error_msg=? WHERE id=?",
            (datetime.utcnow().isoformat(), status, listings_found, listings_new, error_msg, run_id),
        )
        self._conn.commit()

    def recent_runs(self, limit: int = 20) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
