import re
import requests
from datetime import datetime, timedelta, timezone
from .base import BaseScraper, Job


# -----------------------------------------------------------------------
# Verified company slugs (manually tested against each API).
# Companies whose slug 404s are included anyway — the scraper handles
# failures gracefully and just skips them.  This lets us pick up new
# boards that get created later without code changes.
# -----------------------------------------------------------------------

GREENHOUSE_COMPANIES = {
    # Verified 200 — 2026-03-28
    "stripe":          "Stripe",
    "airbnb":          "Airbnb",
    "figma":           "Figma",
    "anthropic":       "Anthropic",
    "databricks":      "Databricks",
    "brex":            "Brex",
    "mercury":         "Mercury",
    "gusto":           "Gusto",
    "lattice":         "Lattice",
    "hightouch":       "Hightouch",
    "launchdarkly":    "LaunchDarkly",
    "twilio":          "Twilio",
    "mixpanel":        "Mixpanel",
    "fivetran":        "Fivetran",
    "datadog":         "Datadog",
    "contentful":      "Contentful",
    "webflow":         "Webflow",
    "amplitude":       "Amplitude",
    "postman":         "Postman",
    "airtable":        "Airtable",
    "squarespace":     "Squarespace",
    "asana":           "Asana",
    "hubspot":         "HubSpot",
    "coinbase":        "Coinbase",
    "lyft":            "Lyft",
    "discord":         "Discord",
    "flexport":        "Flexport",
    "grafanalabs":     "Grafana Labs",
    "cockroachlabs":   "Cockroach Labs",
    "dbtlabsinc":      "dbt Labs",
    "verkada":         "Verkada",
    # May 404 — include for future coverage
    "notion":          "Notion",
    "linear":          "Linear",
    "vercel":          "Vercel",
    "openai":          "OpenAI",
    "mistral":         "Mistral",
    "snowflake":       "Snowflake",
    "plaid":           "Plaid",
    "ramp":            "Ramp",
    "rippling":        "Rippling",
    "deel":            "Deel",
    "ashby":           "Ashby",
    "retool":          "Retool",
    "replit":          "Replit",
    "supabase":        "Supabase",
    "neon":            "Neon",
    "hex":             "Hex",
    "census":          "Census",
    "rudderstack":     "RudderStack",
    "growthbook":      "GrowthBook",
    "statsig":         "Statsig",
    "segment":         "Segment",
    "sendgrid":        "SendGrid",
    "sentry":          "Sentry",
    "split":           "Split",
    "optimizely":      "Optimizely",
    "sanity":          "Sanity",
    "framer":          "Framer",
}

LEVER_COMPANIES = {
    # Verified 200 — 2026-03-28
    "palantir":        "Palantir",
    "meesho":          "Meesho",
    "wealthfront":     "Wealthfront",
    # May 404 — include for future coverage
    "figma":           "Figma",
    "notion":          "Notion",
    "vercel":          "Vercel",
    "netlify":         "Netlify",
    "descript":        "Descript",
    "anduril":         "Anduril",
    "benchling":       "Benchling",
    "cockroachlabs":   "Cockroach Labs",
    "grafana-labs":    "Grafana Labs",
    "rudderstack":     "RudderStack",
    "growthbook":      "GrowthBook",
    "statsig":         "Statsig",
    "postman":         "Postman",
    "webflow":         "Webflow",
    "framer":          "Framer",
    "sanity-io":       "Sanity",
    "contentful":      "Contentful",
    "segment":         "Segment",
    "optimizely":      "Optimizely",
}


class GreenhouseLeverScraper(BaseScraper):
    """Scrape jobs from Greenhouse and Lever public ATS APIs.

    Greenhouse: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
    Lever:      https://api.lever.co/v0/postings/{slug}

    Both are public JSON endpoints with no authentication required.
    Companies that 404 are silently skipped.
    """

    @property
    def name(self) -> str:
        return "greenhouse_lever"

    def scrape(self, job_titles: list[str], **kwargs) -> list[Job]:
        max_results = self.config.get("max_results", 40)
        title_keywords = self._build_keywords(job_titles)
        hours = self.config.get("max_age_hours", 24)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        all_jobs = []
        seen_ids = set()

        # --- Greenhouse ---
        gh_count = 0
        gh_errors = 0
        for slug, display_name in GREENHOUSE_COMPANIES.items():
            try:
                jobs = self._fetch_greenhouse(slug, display_name, title_keywords, cutoff)
                for job in jobs:
                    if job.id not in seen_ids:
                        seen_ids.add(job.id)
                        all_jobs.append(job)
                        gh_count += 1
            except Exception:
                gh_errors += 1

        print(
            f"  [Greenhouse] {len(GREENHOUSE_COMPANIES)} companies "
            f"({len(GREENHOUSE_COMPANIES) - gh_errors} reachable) → {gh_count} matching jobs"
        )

        # --- Lever ---
        lv_count = 0
        lv_errors = 0
        for slug, display_name in LEVER_COMPANIES.items():
            try:
                jobs = self._fetch_lever(slug, display_name, title_keywords, cutoff)
                for job in jobs:
                    if job.id not in seen_ids:
                        seen_ids.add(job.id)
                        all_jobs.append(job)
                        lv_count += 1
            except Exception:
                lv_errors += 1

        print(
            f"  [Lever] {len(LEVER_COMPANIES)} companies "
            f"({len(LEVER_COMPANIES) - lv_errors} reachable) → {lv_count} matching jobs"
        )

        return all_jobs[:max_results]

    # ------------------------------------------------------------------
    # Greenhouse
    # ------------------------------------------------------------------

    def _fetch_greenhouse(
        self, slug: str, display_name: str, keywords: set[str], cutoff: datetime
    ) -> list[Job]:
        """Fetch and filter jobs from Greenhouse boards API."""
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []

        data = resp.json()
        jobs = []

        for item in data.get("jobs", []):
            title = item.get("title", "")
            if not self._title_matches(title, keywords):
                continue

            # Check recency via updated_at (ISO-8601 with offset)
            updated = item.get("updated_at", "")
            if updated and not self._is_recent(updated, cutoff, mode="iso"):
                continue

            location = item.get("location", {}).get("name", "")
            job_url = item.get("absolute_url", "")

            # Use company_name from API if available, else display_name
            company = item.get("company_name", display_name) or display_name

            # Strip HTML from content for description
            description = ""
            content = item.get("content", "")
            if content:
                description = re.sub(r"<[^>]+>", " ", content)
                description = re.sub(r"\s+", " ", description).strip()[:500]

            posted_date = item.get("first_published", updated)

            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=location,
                    url=job_url,
                    description=description,
                    source="greenhouse",
                    posted_date=posted_date,
                )
            )

        return jobs

    # ------------------------------------------------------------------
    # Lever
    # ------------------------------------------------------------------

    def _fetch_lever(
        self, slug: str, display_name: str, keywords: set[str], cutoff: datetime
    ) -> list[Job]:
        """Fetch and filter jobs from Lever postings API."""
        url = f"https://api.lever.co/v0/postings/{slug}"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []

        data = resp.json()
        if not isinstance(data, list):
            return []

        jobs = []
        for item in data:
            title = item.get("text", "")
            if not self._title_matches(title, keywords):
                continue

            # Check recency via createdAt (epoch ms)
            created_at = item.get("createdAt", 0)
            if created_at and not self._is_recent(created_at, cutoff, mode="epoch_ms"):
                continue

            categories = item.get("categories", {})
            location = categories.get("location", "")
            job_url = item.get("hostedUrl", "")
            description = (item.get("descriptionPlain", "") or "")[:500]
            company = display_name

            posted_date = ""
            if created_at:
                try:
                    posted_date = datetime.fromtimestamp(
                        created_at / 1000, tz=timezone.utc
                    ).isoformat()
                except (ValueError, TypeError, OSError):
                    pass

            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=location,
                    url=job_url,
                    description=description,
                    source="lever",
                    posted_date=posted_date,
                )
            )

        return jobs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_keywords(job_titles: list[str]) -> set[str]:
        """Build a set of lowercased keywords for fuzzy title matching.

        We match on individual meaningful words rather than exact title
        strings so that "Business Intelligence Engineer" matches a job
        titled "Senior BI Engineer" via the "engineer" and "intelligence"
        keywords.
        """
        stop_words = {"a", "an", "the", "of", "and", "or", "at", "in", "for", "to", "with"}
        keywords = set()
        for title in job_titles:
            for word in title.lower().split():
                if word not in stop_words and len(word) > 1:
                    keywords.add(word)
        # Always include these high-value keywords
        keywords.update([
            "data", "analyst", "analytics", "marketing", "growth",
            "business", "intelligence", "financial", "product",
            "bi", "seo", "content", "strategy", "operations",
        ])
        return keywords

    @staticmethod
    def _title_matches(title: str, keywords: set[str]) -> bool:
        """Check if any keyword appears in the job title."""
        lower = title.lower()
        return any(kw in lower for kw in keywords)

    @staticmethod
    def _is_recent(value, cutoff: datetime, mode: str = "iso") -> bool:
        """Check if a timestamp is more recent than the cutoff.

        mode="iso"      — ISO-8601 string (Greenhouse updated_at)
        mode="epoch_ms" — Unix timestamp in milliseconds (Lever createdAt)
        """
        try:
            if mode == "iso" and isinstance(value, str):
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            elif mode == "epoch_ms" and isinstance(value, (int, float)):
                dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
            else:
                return True  # Can't parse → don't filter out
            return dt >= cutoff
        except (ValueError, TypeError, OSError):
            return True  # On error, keep the job
