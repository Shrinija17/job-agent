import time
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Job


class LinkedInScraper(BaseScraper):
    """Scrape LinkedIn's public job search page (no login/API key needed)."""

    BASE_URL = "https://www.linkedin.com/jobs/search"

    @property
    def name(self) -> str:
        return "linkedin"

    def scrape(self, job_titles: list[str], **kwargs) -> list[Job]:
        max_results = self.config.get("max_results", 15)

        queries = self._build_queries(job_titles)
        all_jobs = []
        seen_urls = set()

        for query in queries:
            try:
                jobs = self._search(query, max_results)
                for job in jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        all_jobs.append(job)
                print(f"  [LinkedIn] '{query}' → {len(jobs)} jobs")
            except Exception as e:
                print(f"  [LinkedIn] Error for '{query}': {e}")

        return all_jobs

    def _build_queries(self, job_titles: list[str]) -> list[str]:
        """Pick the most distinctive search queries."""
        queries = []
        seen = set()
        for title in job_titles:
            key = title.lower().strip()
            if key not in seen:
                seen.add(key)
                queries.append(title)
        return queries[:6]

    def _search(self, query: str, limit: int) -> list[Job]:
        params = {
            "keywords": query,
            "location": "United States",
            "f_TPR": "r86400",  # past 24 hours
            "position": "1",
            "pageNum": "0",
        }

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        }

        resp = requests.get(self.BASE_URL, params=params, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select(".base-card")

        jobs = []
        for card in cards[:limit]:
            try:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)
            except Exception:
                continue

        # Fetch full descriptions for top jobs (rate limited)
        for job in jobs[:8]:
            if job.url and not job.description:
                try:
                    job.description = self._fetch_full_description(job.url, headers)
                    time.sleep(1)
                except Exception:
                    pass

        return jobs

    def _parse_card(self, card) -> Job | None:
        """Parse a LinkedIn public job search card."""
        # Title
        title_el = card.select_one(".base-search-card__title")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)

        # URL
        link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view']")
        url = ""
        if link_el:
            url = link_el.get("href", "").split("?")[0]

        # Company
        company_el = card.select_one(".base-search-card__subtitle a, .base-search-card__subtitle")
        company = company_el.get_text(strip=True) if company_el else "Unknown"

        # Location
        location_el = card.select_one(".job-search-card__location")
        location = location_el.get_text(strip=True) if location_el else ""

        # Date
        date_el = card.select_one("time")
        posted_date = date_el.get("datetime", "") if date_el else ""

        # Description (not available on search page, fetched later if needed)
        description = ""
        snippet_el = card.select_one(".base-search-card__metadata, .job-search-card__snippet")
        if snippet_el:
            description = snippet_el.get_text(strip=True)

        if not title or not url:
            return None

        return Job(
            title=title,
            company=company,
            location=location,
            url=url,
            description=description,
            source="linkedin",
            posted_date=posted_date,
        )

    def _fetch_full_description(self, url: str, headers: dict) -> str:
        """Fetch the full job description from a LinkedIn job page."""
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")

        # LinkedIn public job pages put the description in these elements
        for selector in [
            ".show-more-less-html__markup",
            ".description__text",
            "[class*='description']",
        ]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(separator=" ", strip=True)[:1500]

        return ""
