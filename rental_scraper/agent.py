"""
Agentic scraping orchestrator.

Architecture
────────────
  OrchestratorAgent
    └─ SiteAgent (one per site, runs concurrently)
         ├─ fetches listings via the site-specific scraper
         ├─ stores results through the Database
         └─ reports telemetry back to the orchestrator

  GradingAgent   – recomputes value grades after each scrape batch
  SchedulerAgent – decides which sites to run based on priority and recency

All agents communicate through the shared Database and an asyncio.Queue.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Type

from rental_scraper.config import SITES, SiteConfig
from rental_scraper.grader.grader import ValueGrader
from rental_scraper.scrapers.base import BaseScraper
from rental_scraper.scrapers.japan import (
    ApartmentJapanScraper,
    ChintaiScraper,
    HomesScraper,
    SuumoScraper,
)
from rental_scraper.scrapers.thailand import (
    DDpropertyScraper,
    HipflatScraper,
    ThaiApartmentScraper,
)
from rental_scraper.scrapers.vietnam import (
    BatdongsanScraper,
    ChototScraper,
    LivingInVietnamScraper,
    MuabanScraper,
)
from rental_scraper.storage.db import Database

logger = logging.getLogger(__name__)

# Map site_id → scraper class
SCRAPER_REGISTRY: Dict[str, Type[BaseScraper]] = {
    "suumo": SuumoScraper,
    "homes": HomesScraper,
    "chintai": ChintaiScraper,
    "apartment_japan": ApartmentJapanScraper,
    "batdongsan": BatdongsanScraper,
    "chotot": ChototScraper,
    "muaban": MuabanScraper,
    "living_in_vietnam": LivingInVietnamScraper,
    "ddproperty": DDpropertyScraper,
    "hipflat": HipflatScraper,
    "thai_apartment": ThaiApartmentScraper,
}


@dataclass
class ScrapeResult:
    site_id: str
    status: str  # "success" | "partial" | "failed"
    listings_found: int = 0
    listings_new: int = 0
    error: str = ""
    duration_s: float = 0.0


# ── Site Agent ────────────────────────────────────────────────────────────────

class SiteAgent:
    """
    Autonomous agent responsible for one site.
    Scrapes, stores, and reports results.
    """

    def __init__(self, config: SiteConfig, db: Database, result_queue: asyncio.Queue):
        self.config = config
        self.db = db
        self.result_queue = result_queue

    async def run(self) -> ScrapeResult:
        site_id = self.config.site_id
        logger.info("[SiteAgent:%s] Starting", site_id)
        run_id = self.db.start_run(site_id)
        t0 = asyncio.get_event_loop().time()

        scraper_cls = SCRAPER_REGISTRY.get(site_id)
        if not scraper_cls:
            err = f"No scraper registered for {site_id}"
            logger.error("[SiteAgent:%s] %s", site_id, err)
            self.db.finish_run(run_id, "failed", 0, 0, err)
            result = ScrapeResult(site_id=site_id, status="failed", error=err)
            await self.result_queue.put(result)
            return result

        scraper = scraper_cls()
        listings_found = 0
        listings_new = 0
        status = "success"
        error_msg = ""

        try:
            listings = await scraper.fetch_listings()
            listings_found = len(listings)
            for listing in listings:
                try:
                    is_new = self.db.upsert_listing(listing)
                    if is_new:
                        listings_new += 1
                except Exception as e:
                    logger.warning("[SiteAgent:%s] DB upsert error: %s", site_id, e)
            if listings_found == 0:
                status = "partial"
        except Exception as e:
            status = "failed"
            error_msg = str(e)
            logger.error("[SiteAgent:%s] Scrape failed: %s", site_id, e, exc_info=True)

        duration = asyncio.get_event_loop().time() - t0
        self.db.finish_run(run_id, status, listings_found, listings_new, error_msg)

        result = ScrapeResult(
            site_id=site_id,
            status=status,
            listings_found=listings_found,
            listings_new=listings_new,
            error=error_msg,
            duration_s=round(duration, 1),
        )
        await self.result_queue.put(result)
        logger.info(
            "[SiteAgent:%s] Done – %d found, %d new, %.1fs",
            site_id, listings_found, listings_new, duration,
        )
        return result


# ── Grading Agent ─────────────────────────────────────────────────────────────

class GradingAgent:
    """Runs after scraping batches to refresh value grades."""

    def __init__(self, db: Database):
        self.db = db

    async def run(self) -> int:
        logger.info("[GradingAgent] Recomputing value grades…")
        grader = ValueGrader(self.db)
        loop = asyncio.get_event_loop()
        # Run the synchronous grading in a thread pool to avoid blocking
        n = await loop.run_in_executor(None, grader.grade_all)
        logger.info("[GradingAgent] Updated %d listings", n)
        return n


# ── Scheduler ─────────────────────────────────────────────────────────────────

class SchedulerAgent:
    """
    Decides which sites to scrape in each cycle.

    Strategy:
    - Sites with no recent run (> max_age_hours) are always included.
    - Sites are sorted by priority (lowest number = highest priority).
    - If max_concurrent is set, only that many run simultaneously.
    """

    def __init__(self, db: Database, max_age_hours: float = 24.0):
        self.db = db
        self.max_age_hours = max_age_hours

    def select_sites(self, site_ids: Optional[List[str]] = None) -> List[SiteConfig]:
        """Return ordered list of SiteConfigs that should be scraped now."""
        if site_ids:
            configs = [s for s in SITES if s.site_id in site_ids]
        else:
            configs = list(SITES)

        cutoff = (datetime.utcnow() - timedelta(hours=self.max_age_hours)).isoformat()
        recent_runs = {
            r["site_id"]: r["started_at"]
            for r in self.db.recent_runs(limit=100)
            if r["status"] == "success" and r["started_at"] >= cutoff
        }

        # Only select sites that haven't been scraped recently
        due = [s for s in configs if s.site_id not in recent_runs]
        due.sort(key=lambda s: s.priority)
        return due


# ── Orchestrator ──────────────────────────────────────────────────────────────

class OrchestratorAgent:
    """
    Top-level agent that coordinates site agents, grading, and scheduling.

    Usage:
        async with OrchestratorAgent(db) as orch:
            summary = await orch.run(site_ids=["suumo", "ddproperty"])
    """

    def __init__(
        self,
        db: Database,
        max_concurrent: int = 3,
        max_age_hours: float = 24.0,
    ):
        self.db = db
        self.max_concurrent = max_concurrent
        self.scheduler = SchedulerAgent(db, max_age_hours=max_age_hours)
        self.grader = GradingAgent(db)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def run(
        self,
        site_ids: Optional[List[str]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Run a full scrape cycle.

        Args:
            site_ids: Limit to these sites. None = all.
            force:    Ignore recency check and always scrape.

        Returns a summary dict.
        """
        if force:
            sites = [s for s in SITES if site_ids is None or s.site_id in site_ids]
            sites.sort(key=lambda s: s.priority)
        else:
            sites = self.scheduler.select_sites(site_ids)

        if not sites:
            logger.info("[Orchestrator] All sites are up-to-date. Nothing to scrape.")
            return {"sites_run": 0, "results": []}

        logger.info(
            "[Orchestrator] Scraping %d sites: %s",
            len(sites),
            [s.site_id for s in sites],
        )

        result_queue: asyncio.Queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results: List[ScrapeResult] = []

        async def _run_site(config: SiteConfig) -> None:
            async with semaphore:
                agent = SiteAgent(config, self.db, result_queue)
                await agent.run()

        tasks = [asyncio.create_task(_run_site(s)) for s in sites]

        # Collect results as they arrive
        completed = 0
        while completed < len(sites):
            result = await result_queue.get()
            results.append(result)
            completed += 1
            logger.info(
                "[Orchestrator] %d/%d – %s: %s (%d new)",
                completed, len(sites), result.site_id, result.status, result.listings_new,
            )

        # Wait for all tasks to finish cleanly
        await asyncio.gather(*tasks, return_exceptions=True)

        # Re-grade after scraping
        grades_updated = await self.grader.run()

        summary = {
            "sites_run": len(results),
            "total_found": sum(r.listings_found for r in results),
            "total_new": sum(r.listings_new for r in results),
            "grades_updated": grades_updated,
            "results": [
                {
                    "site_id": r.site_id,
                    "status": r.status,
                    "found": r.listings_found,
                    "new": r.listings_new,
                    "duration_s": r.duration_s,
                    "error": r.error,
                }
                for r in results
            ],
        }
        logger.info("[Orchestrator] Cycle complete: %s", summary)
        return summary
