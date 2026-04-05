"""
Value grading engine.

Grades each listing relative to its local market using z-scores of
price_per_sqm_usd within the same (country, city) bucket.

Grade scale:
  S  — z < -1.5   (exceptional value: >1.5 std below median)
  A  — z < -0.5
  B  — -0.5 <= z < 0.5   (market rate)
  C  — 0.5 <= z < 1.5
  D  — z >= 1.5   (poor value)
  ?  — insufficient data or missing price/size
"""
import logging
import math
from typing import Dict, List, Optional, Tuple

from rental_scraper.storage.db import Database

logger = logging.getLogger(__name__)


def _z_to_grade(z: float) -> str:
    if z < -1.5:
        return "S"
    if z < -0.5:
        return "A"
    if z < 0.5:
        return "B"
    if z < 1.5:
        return "C"
    return "D"


def _population_stddev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


class ValueGrader:
    def __init__(self, db: Database):
        self.db = db

    # ── Public API ────────────────────────────────────────────────────────────

    def grade_all(self) -> int:
        """
        Re-grade every listing in the database.
        Returns the number of listings updated.
        """
        # Build market stats per (country, city)
        buckets = self._build_buckets()
        updated = 0
        rows = self.db.get_listings(limit=100_000)
        for row in rows:
            grade, z = self._grade_row(row, buckets)
            if grade != row.get("value_grade") or z != row.get("value_score"):
                self.db._conn.execute(
                    "UPDATE listings SET value_grade=?, value_score=? WHERE id=?",
                    (grade, round(z, 4) if z is not None else None, row["id"]),
                )
                updated += 1
        self.db._conn.commit()
        logger.info("Graded %d listings", updated)
        return updated

    def grade_listing(self, listing: Dict) -> Tuple[str, Optional[float]]:
        """Grade a single listing dict (does not hit DB). Returns (grade, z_score)."""
        buckets = self._build_buckets()
        return self._grade_row(listing, buckets)

    def summary(self) -> List[Dict]:
        """Return grade distribution per (country, city, site)."""
        sql = """
            SELECT country, city, site_id, value_grade, COUNT(*) as n,
                   ROUND(AVG(price_usd), 0) as avg_price_usd,
                   ROUND(AVG(size_sqm), 1) as avg_sqm,
                   ROUND(AVG(price_per_sqm_usd), 4) as avg_ppsqm
            FROM listings
            WHERE value_grade IS NOT NULL
            GROUP BY country, city, site_id, value_grade
            ORDER BY country, city, site_id, value_grade
        """
        rows = self.db._conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def top_value_listings(self, country: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Return top-value (S and A grade) listings sorted by z-score."""
        where = "value_grade IN ('S','A')"
        params: list = []
        if country:
            where += " AND country=?"
            params.append(country)
        sql = f"""
            SELECT * FROM listings
            WHERE {where}
            ORDER BY value_score ASC
            LIMIT ?
        """
        params.append(limit)
        rows = self.db._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ── Internals ─────────────────────────────────────────────────────────────

    def _build_buckets(self) -> Dict[Tuple[str, str], Dict]:
        """
        For each (country, city) compute mean and std of price_per_sqm_usd.
        Falls back to (country, *) if city bucket has < MIN_SAMPLES.
        """
        MIN_SAMPLES = 5
        sql = """
            SELECT country, city, price_per_sqm_usd
            FROM listings
            WHERE price_per_sqm_usd IS NOT NULL AND price_per_sqm_usd > 0
        """
        rows = self.db._conn.execute(sql).fetchall()

        # Group values
        raw: Dict[Tuple[str, str], List[float]] = {}
        country_raw: Dict[str, List[float]] = {}
        for r in rows:
            key = (r["country"], r["city"] or "")
            raw.setdefault(key, []).append(r["price_per_sqm_usd"])
            country_raw.setdefault(r["country"], []).append(r["price_per_sqm_usd"])

        buckets: Dict[Tuple[str, str], Dict] = {}
        for key, vals in raw.items():
            if len(vals) >= MIN_SAMPLES:
                mean = sum(vals) / len(vals)
                std = _population_stddev(vals)
                buckets[key] = {"mean": mean, "std": std, "n": len(vals)}

        # Build country-level fallback
        country_buckets: Dict[str, Dict] = {}
        for country, vals in country_raw.items():
            if vals:
                mean = sum(vals) / len(vals)
                std = _population_stddev(vals)
                country_buckets[country] = {"mean": mean, "std": std, "n": len(vals)}

        # Attach fallback to each bucket entry for easy lookup
        for key in buckets:
            buckets[key]["country_fallback"] = country_buckets.get(key[0])

        # Also store country-level under ("country", "__all__") for rows missing a city bucket
        for country, stats in country_buckets.items():
            fallback_key = (country, "__all__")
            if fallback_key not in buckets:
                buckets[fallback_key] = {**stats, "country_fallback": None}

        return buckets

    def _grade_row(self, row: Dict, buckets: Dict) -> Tuple[str, Optional[float]]:
        ppsqm = row.get("price_per_sqm_usd")
        if not ppsqm or ppsqm <= 0:
            return "?", None

        country = row.get("country", "")
        city = row.get("city") or ""

        stats = buckets.get((country, city))
        if not stats or stats["n"] < 5:
            # Fall back to country-wide stats
            stats = buckets.get((country, "__all__"))
        if not stats or stats["n"] < 5:
            return "?", None

        mean = stats["mean"]
        std = stats["std"]
        if std == 0:
            return "B", 0.0

        z = (ppsqm - mean) / std
        return _z_to_grade(z), round(z, 4)
