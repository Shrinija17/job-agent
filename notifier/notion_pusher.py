import os
import requests
from scrapers.base import Job


class NotionPusher:
    """Push job results to the Notion Job Tracker database."""

    API_BASE = "https://api.notion.com/v1"

    def __init__(self, database_id: str):
        self.token = os.getenv("NOTION_API_KEY", "").strip()
        self.database_id = database_id
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.database_id)

    def push_jobs(
        self,
        jobs: list[Job],
        pdf_paths: list[str] | None = None,
        resume_names: list[str] | None = None,
    ):
        """Push a batch of jobs to the Notion database."""
        if not self.is_configured:
            print("  [Notion] Skipped — no NOTION_API_KEY or database_id")
            return

        success = 0
        for i, job in enumerate(jobs):
            try:
                source_map = {
                    "linkedin": "LinkedIn",
                    "amazon": "Amazon",
                    "builtin": "BuiltIn",
                    "google_jobs": "LinkedIn",  # map to closest
                    "yc": "BuiltIn",
                    "greenhouse": "BuiltIn",
                    "lever": "BuiltIn",
                }
                source = source_map.get(job.source, "LinkedIn")

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
                else:
                    print(
                        f"  [Notion] Failed for {job.title}: {resp.status_code}"
                    )
            except Exception as e:
                print(f"  [Notion] Error for {job.title}: {e}")

        print(f"  [Notion] Pushed {success}/{len(jobs)} jobs")
