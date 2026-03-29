import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Job


class BuiltInScraper(BaseScraper):
    """Scrape BuiltIn.com for job listings."""

    BASE_URL = "https://builtin.com/jobs"

    @property
    def name(self) -> str:
        return "builtin"

    def scrape(self, job_titles: list[str], **kwargs) -> list[Job]:
        max_results = self.config.get("max_results", 15)

        # BuiltIn uses URL-based categories
        search_terms = self._build_search_terms(job_titles)

        all_jobs = []
        seen_urls = set()

        for term in search_terms:
            try:
                jobs = self._search(term, max_results)
                for job in jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        all_jobs.append(job)
                print(f"  [BuiltIn] '{term}' → {len(jobs)} jobs")
            except Exception as e:
                print(f"  [BuiltIn] Error for '{term}': {e}")

        return all_jobs

    def _build_search_terms(self, job_titles: list[str]) -> list[str]:
        """Convert job titles to BuiltIn search-friendly terms."""
        terms = set()
        for title in job_titles:
            lower = title.lower()
            if "data" in lower:
                terms.add("data analyst")
            if "marketing" in lower:
                terms.add("marketing analyst")
            if "business" in lower and "intelligence" in lower:
                terms.add("business intelligence")
            if "business analyst" in lower:
                terms.add("business analyst")
            if "financial" in lower:
                terms.add("financial analyst")
            if "product" in lower:
                terms.add("product analyst")
            if "growth" in lower:
                terms.add("growth marketing")
            if "analytics engineer" in lower:
                terms.add("analytics engineer")
        return list(terms)[:5]

    def _search(self, query: str, limit: int) -> list[Job]:
        params = {
            "search": query,
            "datePosted": "1",  # Last 24 hours
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html",
        }

        resp = requests.get(self.BASE_URL, params=params, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = []

        # BuiltIn uses job card elements
        job_cards = soup.select('[data-id="job-card"]')
        if not job_cards:
            # Fallback selectors
            job_cards = soup.select(".job-card, .jobs-list-item, [class*='JobCard']")

        for card in job_cards[:limit]:
            try:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)
            except Exception:
                continue

        return jobs

    def _parse_card(self, card) -> Job | None:
        """Parse a BuiltIn job card HTML element."""
        # Title lives in an <a> with data-id="job-card-title"
        title_el = card.select_one('[data-id="job-card-title"]')
        if not title_el:
            title_el = card.select_one("a[href*='/job/']")
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        url = href if href.startswith("http") else f"https://builtin.com{href}"

        # Company name — data-id="company-title"
        company_el = card.select_one('[data-id="company-title"]')
        company = company_el.get_text(strip=True) if company_el else "Unknown"

        # Location — found via the fa-location-dot icon
        location = self._extract_icon_text(card, "fa-location-dot")

        # Work type (Remote/Hybrid/In-Office) — found via fa-house-building icon
        work_type = self._extract_icon_text(card, "fa-house-building")
        if work_type and location:
            location = f"{location} ({work_type})"
        elif work_type:
            location = work_type

        # Description snippet — inside the collapsible section
        description = ""
        collapse = card.select_one(".collapse")
        if collapse:
            desc_el = collapse.select_one("div.fs-sm.fw-regular")
            if desc_el:
                description = desc_el.get_text(strip=True)

        # Salary — found via fa-sack-dollar icon; prepend to description
        salary = self._extract_icon_text(card, "fa-sack-dollar")
        if salary:
            description = f"Salary: {salary}. {description}" if description else f"Salary: {salary}"

        return Job(
            title=title,
            company=company,
            location=location,
            url=url,
            description=description,
            source="builtin",
        )

    @staticmethod
    def _extract_icon_text(card, icon_class: str) -> str:
        """Extract the text label next to a Font Awesome icon in a BuiltIn job card.

        BuiltIn renders metadata fields as:
            <div class="d-flex align-items-start gap-sm">
              <div>...<i class="fa-regular fa-{icon}">...</div>
              <span class="font-barlow text-gray-04">Label</span>
            </div>
        """
        icon = card.select_one(f"i.{icon_class}")
        if not icon:
            return ""
        container = icon.find_parent("div", class_=lambda c: c and "d-flex" in c and "gap-sm" in c)
        if container:
            # Try direct span child first
            span = container.find("span", class_="font-barlow")
            if span:
                return span.get_text(strip=True)
            # Some fields wrap the span in an extra div
            inner_div = container.find("div", recursive=False)
            if inner_div:
                span = inner_div.find("span")
                if span:
                    return span.get_text(strip=True)
        return ""
