import requests
from .base import BaseScraper, Job


class AmazonJobsScraper(BaseScraper):
    """Scrape Amazon.jobs using their public search API."""

    BASE_URL = "https://www.amazon.jobs/en/search.json"

    @property
    def name(self) -> str:
        return "amazon"

    def scrape(self, job_titles: list[str], **kwargs) -> list[Job]:
        max_results = self.config.get("max_results", 15)

        # Amazon's search works best with simpler queries
        queries = self._build_queries(job_titles)

        all_jobs = []
        seen_ids = set()

        for query in queries:
            try:
                jobs = self._search(query, max_results)
                for job in jobs:
                    if job.id not in seen_ids:
                        seen_ids.add(job.id)
                        all_jobs.append(job)
                print(f"  [Amazon] '{query}' → {len(jobs)} jobs")
            except Exception as e:
                print(f"  [Amazon] Error for '{query}': {e}")

        return all_jobs

    def _build_queries(self, job_titles: list[str]) -> list[str]:
        """Use Amazon-friendly search terms."""
        # Amazon uses specific titles — map our titles to theirs
        amazon_queries = [
            "Data Analyst",
            "Business Intelligence Engineer",
            "Business Analyst",
            "Financial Analyst",
            "Marketing Analyst",
            "Product Analyst",
        ]
        return amazon_queries

    def _search(self, query: str, limit: int) -> list[Job]:
        params = {
            "base_query": query,
            "normalized_country_code[]": "USA",
            "result_limit": limit,
            "sort": "recent",
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }

        resp = requests.get(self.BASE_URL, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(hours=48)

        for item in data.get("jobs", []):
            # Filter by posted date (last 48 hours)
            posted = item.get("posted_date", "")
            if posted:
                try:
                    posted_dt = datetime.strptime(posted, "%B %d, %Y")
                    if posted_dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass

            job_id = item.get("id_icims", item.get("id", ""))
            job = Job(
                title=item.get("title", ""),
                company="Amazon",
                location=item.get("normalized_location", item.get("location", "")),
                url=f"https://www.amazon.jobs/en/jobs/{job_id}",
                description=self._clean_description(item),
                source="amazon",
                posted_date=item.get("posted_date", ""),
            )
            if job.title:
                jobs.append(job)

        return jobs

    def _clean_description(self, item: dict) -> str:
        """Combine relevant fields into a description."""
        parts = []
        for field in [
            "description",
            "basic_qualifications",
            "preferred_qualifications",
            "description_short",
        ]:
            val = item.get(field, "")
            if val:
                # Strip HTML tags
                import re
                clean = re.sub(r"<[^>]+>", " ", val)
                clean = re.sub(r"\s+", " ", clean).strip()
                parts.append(clean)
        return "\n\n".join(parts)
