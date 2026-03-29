import re
import html as htmlmod
import json
import requests
from .base import BaseScraper, Job


class YCJobsScraper(BaseScraper):
    """Scrape Y Combinator's Work at a Startup (workatastartup.com).

    The site is a server-rendered Inertia.js app that embeds job data
    directly in the HTML as a JSON blob inside a data-page attribute.
    Role-specific pages at /jobs/l/{role} return ~25 jobs each.

    The Algolia search key on the page is restricted with
    tagFilters=[["none"]], so it returns zero results for non-logged-in
    users. Instead, we scrape the pre-rendered Inertia props.
    """

    BASE_URL = "https://www.workatastartup.com"

    # Role slugs available at workatastartup.com/jobs
    ROLE_SLUGS = [
        "marketing",
        "finance",
        "operations",
        "product-manager",
        "sales-manager",
        "software-engineer",
        "designer",
        "science",
        "recruiting",
        "legal",
    ]

    @property
    def name(self) -> str:
        return "yc"

    def scrape(self, job_titles: list[str], **kwargs) -> list[Job]:
        max_results = self.config.get("max_results", 50)
        slugs_to_fetch = self._map_titles_to_slugs(job_titles)

        all_jobs = []
        seen_ids = set()

        # Fetch role-specific pages
        for slug in slugs_to_fetch:
            try:
                jobs = self._fetch_role_page(slug, job_titles)
                for job in jobs:
                    if job.id not in seen_ids:
                        seen_ids.add(job.id)
                        all_jobs.append(job)
                print(f"  [YC] /jobs/l/{slug} → {len(jobs)} jobs")
            except Exception as e:
                print(f"  [YC] Error for /jobs/l/{slug}: {e}")

        # Also fetch the main /jobs page for general listings
        try:
            jobs = self._fetch_role_page(None, job_titles)
            new = 0
            for job in jobs:
                if job.id not in seen_ids:
                    seen_ids.add(job.id)
                    all_jobs.append(job)
                    new += 1
            print(f"  [YC] /jobs (main) → {new} new jobs")
        except Exception as e:
            print(f"  [YC] Error for /jobs (main): {e}")

        return all_jobs[:max_results]

    def _map_titles_to_slugs(self, job_titles: list[str]) -> list[str]:
        """Map config job titles to the most relevant YC role page slugs."""
        slugs = set()
        for title in job_titles:
            lower = title.lower()
            if any(kw in lower for kw in ["marketing", "growth", "seo", "content", "social media"]):
                slugs.add("marketing")
            if any(kw in lower for kw in ["data", "analytics", "bi", "business intelligence"]):
                slugs.add("operations")
                slugs.add("science")
            if any(kw in lower for kw in ["financial", "finance"]):
                slugs.add("finance")
            if "product" in lower:
                slugs.add("product-manager")
            if any(kw in lower for kw in ["business analyst", "bizops", "strategy", "operations"]):
                slugs.add("operations")
        # Always include these — most relevant for the config's job titles
        slugs.update(["marketing", "operations", "finance"])
        return list(slugs)

    def _fetch_role_page(self, slug: str | None, job_titles: list[str]) -> list[Job]:
        """Fetch a role page and extract jobs from the Inertia.js data-page attribute."""
        if slug:
            url = f"{self.BASE_URL}/jobs/l/{slug}"
        else:
            url = f"{self.BASE_URL}/jobs"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }

        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        raw_jobs = self._extract_inertia_jobs(resp.text)
        if not raw_jobs:
            return []

        jobs = []
        for item in raw_jobs:
            job = self._parse_job(item)
            if job and self._is_relevant(job.title):
                jobs.append(job)

        return jobs

    def _extract_inertia_jobs(self, html_content: str) -> list[dict]:
        """Extract job data from the Inertia.js data-page attribute.

        The page contains: <div id="app" data-page="{...HTML-escaped JSON...}">
        Inside the JSON: { props: { jobs: [...] } }
        """
        match = re.search(r'data-page="([^"]+)"', html_content)
        if not match:
            return []

        raw = match.group(1)
        decoded = htmlmod.unescape(raw)

        try:
            data = json.loads(decoded)
        except json.JSONDecodeError:
            return []

        return data.get("props", {}).get("jobs", [])

    def _parse_job(self, item: dict) -> Job | None:
        """Parse a YC job listing from the Inertia data.

        Fields: id, title, jobType, location, roleType, companyName,
        companySlug, companyBatch, companyOneLiner, companyLogoUrl,
        companyLastActiveAt, applyUrl
        """
        title = item.get("title", "").strip()
        company = item.get("companyName", "").strip()
        if not title or not company:
            return None

        location = item.get("location", "")
        company_slug = item.get("companySlug", "")

        # Build URL to the company page on WAAS
        url = f"{self.BASE_URL}/companies/{company_slug}" if company_slug else ""

        # Build description from available metadata
        desc_parts = []
        batch = item.get("companyBatch", "")
        if batch:
            desc_parts.append(f"YC {batch}")
        one_liner = item.get("companyOneLiner", "")
        if one_liner:
            desc_parts.append(one_liner)
        role_type = item.get("roleType", "")
        if role_type:
            desc_parts.append(f"Role: {role_type}")
        job_type = item.get("jobType", "")
        if job_type:
            desc_parts.append(f"Type: {job_type}")

        description = " | ".join(desc_parts)

        return Job(
            title=title,
            company=company,
            location=location,
            url=url,
            description=description,
            source="yc",
            tags=["YC"],
        )

    @staticmethod
    def _is_relevant(job_title: str) -> bool:
        """Check if a job title is in the analyst/marketing/data/ops domain.

        The role pages already pre-filter by category, so we use a loose
        check here. The downstream scoring pipeline handles precise ranking.
        """
        lower = job_title.lower()
        keywords = [
            "data", "analyst", "analytics", "marketing", "growth",
            "business", "intelligence", "financial", "product",
            "bi", "seo", "content", "strategy", "operations",
            "bizops", "ai", "insights", "reporting", "revenue",
            "go-to-market", "gtm", "demand gen", "performance",
        ]
        return any(kw in lower for kw in keywords)
