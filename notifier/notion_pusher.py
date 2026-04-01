import os
import requests
from scrapers.base import Job


class NotionPusher:
    """Push job results to the Notion Job Tracker database. Deduplicates against existing entries."""

    API_BASE = "https://api.notion.com/v1"

    def __init__(self, database_id: str):
        self.token = os.getenv("NOTION_API_KEY", "").strip()
        self.database_id = database_id
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
        self._existing_keys: set[str] | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.database_id)

    def _load_existing_jobs(self):
        """Load all existing job keys from Notion to prevent duplicates."""
        if self._existing_keys is not None:
            return

        self._existing_keys = set()
        has_more = True
        start_cursor = None

        while has_more:
            body = {"page_size": 100}
            if start_cursor:
                body["start_cursor"] = start_cursor
            try:
                resp = requests.post(
                    f"{self.API_BASE}/databases/{self.database_id}/query",
                    headers=self.headers,
                    json=body,
                    timeout=15,
                )
                data = resp.json()
                for page in data.get("results", []):
                    t = page["properties"].get("Job Title", {}).get("title", [])
                    title = t[0]["plain_text"] if t else ""
                    c = page["properties"].get("Company", {}).get("rich_text", [])
                    company = c[0]["plain_text"] if c else ""
                    key = f"{company}:{title}".lower().strip()
                    if key:
                        self._existing_keys.add(key)
                has_more = data.get("has_more", False)
                start_cursor = data.get("next_cursor")
            except Exception:
                has_more = False

        print(f"  [Notion] Loaded {len(self._existing_keys)} existing jobs for dedup")

    def push_jobs(
        self,
        jobs: list[Job],
        pdf_paths: list[str] | None = None,
        resume_names: list[str] | None = None,
    ):
        """Push a batch of jobs to the Notion database, skipping duplicates."""
        if not self.is_configured:
            print("  [Notion] Skipped — no NOTION_API_KEY or database_id")
            return

        # Load existing jobs for dedup
        self._load_existing_jobs()

        success = 0
        skipped = 0
        for i, job in enumerate(jobs):
            # Check for duplicate
            key = f"{job.company}:{job.title}".lower().strip()
            if key in self._existing_keys:
                skipped += 1
                continue

            try:
                source_map = {
                    "linkedin": "LinkedIn",
                    "amazon": "Amazon",
                    "builtin": "BuiltIn",
                    "yc": "YC",
                    "greenhouse": "Greenhouse",
                    "lever": "Lever",
                    "google_jobs": "LinkedIn",
                    "indeed": "Indeed",
                    "glassdoor": "Glassdoor",
                    "remotive": "Remotive",
                    "powertofly": "PowerToFly",
                    "arc.dev": "Arc.dev",
                    "governmentjobs": "GovernmentJobs",
                    "jobspresso": "Jobspresso",
                    "ai-jobs": "AI-Jobs",
                    "workingnomads": "WorkingNomads",
                }
                source = source_map.get(job.source, job.source.title())

                properties = {
                    "Job Title": {"title": [{"text": {"content": job.title[:100]}}]},
                    "Company": {
                        "rich_text": [{"text": {"content": job.company[:100]}}]
                    },
                    "Score": {"number": job.score},
                    "Location": {
                        "rich_text": [{"text": {"content": job.location[:100]}}]
                    },
                    "URL": {"url": job.url if job.url else None},
                    "Source": {"select": {"name": source}},
                    "Status": {"select": {"name": "New"}},
                }

                payload = {
                    "parent": {"database_id": self.database_id},
                    "properties": properties,
                }

                resp = requests.post(
                    f"{self.API_BASE}/pages",
                    json=payload,
                    headers=self.headers,
                    timeout=15,
                )

                if resp.status_code == 200:
                    success += 1
                    self._existing_keys.add(key)
                else:
                    print(
                        f"  [Notion] Failed for {job.title}: {resp.status_code}"
                    )
            except Exception as e:
                print(f"  [Notion] Error for {job.title}: {e}")

        print(f"  [Notion] Pushed {success} new, skipped {skipped} duplicates (of {len(jobs)} total)")
