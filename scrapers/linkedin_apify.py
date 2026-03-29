import os
import time
import requests
from .base import BaseScraper, Job


class LinkedInApifyScraper(BaseScraper):
    """Scrape LinkedIn jobs using Apify's LinkedIn Jobs Scraper actor."""

    ACTOR_ID = "hMvNSpz3JnHgl5jkh"  # apify/linkedin-jobs-scraper
    API_BASE = "https://api.apify.com/v2"

    @property
    def name(self) -> str:
        return "linkedin"

    def scrape(self, job_titles: list[str], **kwargs) -> list[Job]:
        token = os.getenv("APIFY_API_TOKEN", "").strip()
        if not token:
            print("  [LinkedIn] Skipped — no APIFY_API_TOKEN in .env")
            return []

        max_results = self.config.get("max_results", 15)
        posted_within = self.config.get("posted_within_hours", 24)

        # Build search queries — combine related titles to reduce API calls
        queries = self._build_queries(job_titles)

        all_jobs = []
        for query in queries:
            try:
                jobs = self._run_actor(token, query, max_results, posted_within)
                all_jobs.extend(jobs)
                print(f"  [LinkedIn] '{query}' → {len(jobs)} jobs")
            except Exception as e:
                print(f"  [LinkedIn] Error for '{query}': {e}")

        return all_jobs

    def _build_queries(self, job_titles: list[str]) -> list[str]:
        """Group titles into efficient search queries."""
        # LinkedIn search works best with 1-2 title keywords
        queries = []
        for title in job_titles[:8]:  # Limit to top 8 to stay in free tier
            queries.append(title)
        return queries

    def _run_actor(
        self, token: str, query: str, max_results: int, posted_within: int
    ) -> list[Job]:
        """Run the Apify actor and wait for results."""
        run_url = f"{self.API_BASE}/acts/{self.ACTOR_ID}/runs"

        payload = {
            "searchQueries": [query],
            "location": "United States",
            "maxResults": max_results,
            "publishedAt": f"past 24 hours" if posted_within <= 24 else "past week",
            "proxy": {"useApifyProxy": True},
        }

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Start the actor run
        resp = requests.post(run_url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        run_data = resp.json()["data"]
        run_id = run_data["id"]
        dataset_id = run_data["defaultDatasetId"]

        # Poll for completion (max 2 minutes)
        status_url = f"{self.API_BASE}/actor-runs/{run_id}"
        for _ in range(24):
            time.sleep(5)
            status_resp = requests.get(status_url, headers=headers, timeout=15)
            status = status_resp.json()["data"]["status"]
            if status == "SUCCEEDED":
                break
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise RuntimeError(f"Actor run {status}")
        else:
            raise TimeoutError("Actor run timed out after 2 minutes")

        # Fetch results
        dataset_url = f"{self.API_BASE}/datasets/{dataset_id}/items?format=json"
        data_resp = requests.get(dataset_url, headers=headers, timeout=30)
        items = data_resp.json()

        jobs = []
        for item in items:
            job = Job(
                title=item.get("title", ""),
                company=item.get("companyName", ""),
                location=item.get("location", ""),
                url=item.get("link", item.get("url", "")),
                description=item.get("description", ""),
                source="linkedin",
                posted_date=item.get("publishedAt", ""),
            )
            if job.title and job.company:
                jobs.append(job)

        return jobs
