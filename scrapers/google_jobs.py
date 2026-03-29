import os
import time
import requests
from .base import BaseScraper, Job


class GoogleJobsScraper(BaseScraper):
    """Scrape Google Jobs via Apify actor or direct search."""

    ACTOR_ID = "nFJndFXA5zjCTuudP"  # Google Jobs Scraper on Apify

    @property
    def name(self) -> str:
        return "google_jobs"

    def scrape(self, job_titles: list[str], **kwargs) -> list[Job]:
        token = os.getenv("APIFY_API_TOKEN", "").strip()
        max_results = self.config.get("max_results", 20)
        queries = job_titles[:4]  # Limit to save Apify credits

        all_jobs = []
        seen_urls = set()

        if token:
            for query in queries:
                try:
                    jobs = self._search_apify(token, query, max_results)
                    for job in jobs:
                        if job.url not in seen_urls:
                            seen_urls.add(job.url)
                            all_jobs.append(job)
                    print(f"  [Google Jobs] '{query}' → {len(jobs)} jobs")
                except Exception as e:
                    print(f"  [Google Jobs] Error for '{query}': {e}")
        else:
            print("  [Google Jobs] Skipped — no APIFY_API_TOKEN")

        return all_jobs

    def _search_apify(self, token: str, query: str, limit: int) -> list[Job]:
        """Run the Apify Google Jobs Scraper actor."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # First try to find a free/available Google Jobs actor
        payload = {
            "queries": [f"{query} United States"],
            "maxResults": limit,
            "csvFriendlyOutput": False,
        }

        run_url = f"https://api.apify.com/v2/acts/{self.ACTOR_ID}/runs"

        resp = requests.post(run_url, json=payload, headers=headers, timeout=30)

        if resp.status_code == 403:
            # Actor needs renting, try alternative actor
            return self._search_alternative_actor(token, query, limit, headers)

        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Actor start failed: {resp.status_code}")

        run_data = resp.json()["data"]
        run_id = run_data["id"]
        dataset_id = run_data["defaultDatasetId"]

        # Poll for completion (max 90 seconds)
        for _ in range(18):
            time.sleep(5)
            status_resp = requests.get(
                f"https://api.apify.com/v2/actor-runs/{run_id}",
                headers=headers,
                timeout=15,
            )
            status = status_resp.json()["data"]["status"]
            if status == "SUCCEEDED":
                break
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise RuntimeError(f"Actor run {status}")
        else:
            # Abort and skip
            requests.post(
                f"https://api.apify.com/v2/actor-runs/{run_id}/abort",
                headers=headers,
                timeout=10,
            )
            return []

        # Fetch results
        data_resp = requests.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items?format=json&limit={limit}",
            headers=headers,
            timeout=30,
        )
        items = data_resp.json()

        return self._parse_results(items)

    def _search_alternative_actor(
        self, token: str, query: str, limit: int, headers: dict
    ) -> list[Job]:
        """Try alternative Google Jobs actors on Apify."""
        alt_actors = [
            "SpK2FgpWRNKAWLGEn",  # Google Jobs Scraper (another)
            "JL5NqB3lNfWdhR7oU",  # Google Search Results
        ]

        for actor_id in alt_actors:
            try:
                payload = {
                    "queries": [f"{query} jobs United States"],
                    "maxResults": limit,
                }

                resp = requests.post(
                    f"https://api.apify.com/v2/acts/{actor_id}/runs",
                    json=payload,
                    headers=headers,
                    timeout=30,
                )

                if resp.status_code in (200, 201):
                    run_data = resp.json()["data"]
                    run_id = run_data["id"]
                    dataset_id = run_data["defaultDatasetId"]

                    for _ in range(18):
                        time.sleep(5)
                        status_resp = requests.get(
                            f"https://api.apify.com/v2/actor-runs/{run_id}",
                            headers=headers,
                            timeout=15,
                        )
                        status = status_resp.json()["data"]["status"]
                        if status == "SUCCEEDED":
                            data_resp = requests.get(
                                f"https://api.apify.com/v2/datasets/{dataset_id}/items?format=json&limit={limit}",
                                headers=headers,
                                timeout=30,
                            )
                            return self._parse_results(data_resp.json())
                        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                            break
            except Exception:
                continue

        return []

    def _parse_results(self, items: list) -> list[Job]:
        """Parse Apify Google Jobs results into Job objects."""
        jobs = []
        for item in items:
            if isinstance(item, dict) and "error" not in item:
                title = item.get("title", item.get("jobTitle", ""))
                company = item.get(
                    "companyName", item.get("company", item.get("employer", ""))
                )
                location = item.get("location", item.get("jobLocation", ""))
                url = item.get(
                    "applyLink", item.get("link", item.get("url", ""))
                )
                if isinstance(url, list) and url:
                    url = url[0].get("link", "") if isinstance(url[0], dict) else url[0]
                description = item.get(
                    "description", item.get("jobDescription", "")
                )[:500]

                if title and company:
                    jobs.append(
                        Job(
                            title=title,
                            company=company,
                            location=location,
                            url=url,
                            description=description,
                            source="google_jobs",
                        )
                    )
        return jobs
