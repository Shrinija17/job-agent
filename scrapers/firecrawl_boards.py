import re
import json
import requests
from .base import BaseScraper, Job


class FirecrawlBoardsScraper(BaseScraper):
    """Use local Firecrawl (Docker) to scrape JS-heavy job boards that regular requests can't handle."""

    FIRECRAWL_URL = "http://localhost:3002/v1/scrape"
    FIRECRAWL_TOKEN = "fc-"  # Local Docker instance, no real token needed

    # Boards to scrape with search URLs
    BOARDS = {
        "Wellfound": [
            "https://wellfound.com/role/data-analyst",
            "https://wellfound.com/role/marketing",
            "https://wellfound.com/role/business-analyst",
            "https://wellfound.com/role/business-development",
        ],
        "Indeed": [
            "https://www.indeed.com/jobs?q=data+analyst&fromage=1&sort=date",
            "https://www.indeed.com/jobs?q=business+analyst+entry+level&fromage=1&sort=date",
            "https://www.indeed.com/jobs?q=marketing+analyst&fromage=1&sort=date",
            "https://www.indeed.com/jobs?q=growth+marketing&fromage=1&sort=date",
            "https://www.indeed.com/jobs?q=business+intelligence+analyst&fromage=1&sort=date",
        ],
        "Glassdoor": [
            "https://www.glassdoor.com/Job/data-analyst-jobs-SRCH_KO0,12.htm?fromAge=1",
            "https://www.glassdoor.com/Job/marketing-analyst-jobs-SRCH_KO0,18.htm?fromAge=1",
            "https://www.glassdoor.com/Job/business-analyst-entry-level-jobs-SRCH_KO0,28.htm?fromAge=1",
        ],
        "Remotive": [
            "https://remotive.com/remote-jobs/marketing",
            "https://remotive.com/remote-jobs/data",
            "https://remotive.com/remote-jobs/finance-legal",
        ],
        "PowerToFly": [
            "https://powertofly.com/jobs/?keywords=data+analyst",
            "https://powertofly.com/jobs/?keywords=marketing+analyst",
        ],
        "Arc.dev": [
            "https://arc.dev/remote-jobs/data-analyst",
            "https://arc.dev/remote-jobs/marketing",
        ],
    }

    @property
    def name(self) -> str:
        return "firecrawl_boards"

    def scrape(self, job_titles: list[str], **kwargs) -> list[Job]:
        max_results = self.config.get("max_results", 50)
        all_jobs = []
        seen_urls = set()

        for board_name, urls in self.BOARDS.items():
            board_jobs = 0
            for url in urls:
                try:
                    jobs = self._scrape_url(url, board_name.lower())
                    for job in jobs:
                        if job.url and job.url not in seen_urls:
                            seen_urls.add(job.url)
                            all_jobs.append(job)
                            board_jobs += 1
                except Exception as e:
                    pass  # Silent fail per URL, report per board
            if board_jobs > 0:
                print(f"  [Firecrawl:{board_name}] → {board_jobs} jobs")
            else:
                print(f"  [Firecrawl:{board_name}] → 0 jobs")

        return all_jobs[:max_results]

    def _scrape_url(self, url: str, source: str) -> list[Job]:
        """Scrape a single URL using Firecrawl and extract job listings."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.FIRECRAWL_TOKEN}",
        }

        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "waitFor": 3000,
        }

        resp = requests.post(
            self.FIRECRAWL_URL, json=payload, headers=headers, timeout=60
        )

        if resp.status_code != 200:
            return []

        data = resp.json()
        if not data.get("success"):
            return []

        markdown = data.get("data", {}).get("markdown", "")
        if not markdown:
            return []

        return self._extract_jobs_from_markdown(markdown, source, url)

    def _extract_jobs_from_markdown(self, markdown: str, source: str, page_url: str) -> list[Job]:
        """Parse job listings from markdown content."""
        jobs = []

        # Pattern 1: Markdown links that look like job titles
        # [Job Title](url) or [Job Title at Company](url)
        link_pattern = re.compile(
            r'\[([^\]]{10,100})\]\((https?://[^\)]+)\)', re.IGNORECASE
        )

        for match in link_pattern.finditer(markdown):
            text = match.group(1).strip()
            url = match.group(2).strip()

            # Skip navigation/non-job links
            if any(skip in text.lower() for skip in [
                "sign up", "log in", "subscribe", "learn more", "view all",
                "next page", "previous", "cookie", "privacy", "terms",
                "home", "about", "contact", "blog", "pricing",
            ]):
                continue

            # Check if it looks like a job title
            if not self._looks_like_job(text):
                continue

            # Try to extract company from the text or surrounding context
            title, company = self._split_title_company(text)

            if title:
                jobs.append(Job(
                    title=title,
                    company=company,
                    location="",
                    url=url,
                    description="",
                    source=source,
                ))

        # Pattern 2: Look for structured job listings in markdown
        # Title\nCompany\nLocation patterns
        lines = markdown.split("\n")
        i = 0
        while i < len(lines) - 1:
            line = lines[i].strip()
            if self._looks_like_job(line) and not line.startswith("["):
                # Next lines might be company/location
                company = ""
                location = ""
                url_found = ""

                for j in range(i + 1, min(i + 4, len(lines))):
                    next_line = lines[j].strip()
                    if not next_line:
                        continue
                    link_match = re.search(r'\((https?://[^\)]+)\)', next_line)
                    if link_match:
                        url_found = link_match.group(1)
                    if not company and next_line and not next_line.startswith("-"):
                        company = next_line[:80]

                if url_found or company:
                    jobs.append(Job(
                        title=line[:100],
                        company=re.sub(r'[\[\]\(\)]', '', company)[:80],
                        location=location,
                        url=url_found or page_url,
                        description="",
                        source=source,
                    ))
            i += 1

        return jobs

    def _looks_like_job(self, text: str) -> bool:
        """Check if text looks like a job title."""
        lower = text.lower()
        job_words = [
            "analyst", "engineer", "manager", "marketing", "data",
            "business", "intelligence", "financial", "product",
            "growth", "content", "social media", "operations",
            "bi ", "ai ", "ml ", "seo", "crm", "revops",
        ]
        return any(w in lower for w in job_words) and len(text) < 120

    def _split_title_company(self, text: str) -> tuple[str, str]:
        """Split 'Job Title at Company' or 'Job Title - Company' into parts."""
        for sep in [" at ", " @ ", " - ", " | ", " — ", " – "]:
            if sep in text:
                parts = text.split(sep, 1)
                return parts[0].strip(), parts[1].strip()
        return text, ""
