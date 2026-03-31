import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from .base import BaseScraper, Job


class RemoteBoardsScraper(BaseScraper):
    """Scrape multiple job boards: Remotive, Jobspresso, Working Nomads, AI-Jobs.net, GovernmentJobs."""

    @property
    def name(self) -> str:
        return "remote_boards"

    def scrape(self, job_titles: list[str], **kwargs) -> list[Job]:
        max_results = self.config.get("max_results", 30)
        all_jobs = []
        seen_urls = set()

        scrapers = [
            ("Remotive", self._scrape_remotive),
            ("Jobspresso", self._scrape_jobspresso),
            ("WorkingNomads", self._scrape_working_nomads),
            ("AI-Jobs", self._scrape_ai_jobs),
            ("GovJobs", self._scrape_governmentjobs),
        ]

        for name, fn in scrapers:
            try:
                jobs = fn(job_titles)
                new = 0
                for job in jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        all_jobs.append(job)
                        new += 1
                print(f"  [{name}] → {new} jobs")
            except Exception as e:
                print(f"  [{name}] Error: {e}")

        return all_jobs[:max_results]

    def _headers(self):
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def _title_relevant(self, title: str) -> bool:
        lower = title.lower()
        keywords = [
            "data analyst", "business analyst", "bi ", "business intelligence",
            "marketing analyst", "growth", "financial analyst", "product analyst",
            "analytics engineer", "marketing", "data", "analyst", "bi",
            "bizops", "operations analyst", "ai ",
        ]
        return any(kw in lower for kw in keywords)

    # --- Remotive.io (has a public JSON API) ---
    def _scrape_remotive(self, job_titles: list[str]) -> list[Job]:
        resp = requests.get(
            "https://remotive.com/api/remote-jobs",
            params={"limit": 50},
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for item in data.get("jobs", []):
            title = item.get("title", "")
            if not self._title_relevant(title):
                continue

            # Check recency
            pub_date = item.get("publication_date", "")
            if pub_date:
                try:
                    dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    if dt < datetime.now(dt.tzinfo) - timedelta(hours=72):
                        continue
                except (ValueError, TypeError):
                    pass

            company = item.get("company_name", "")
            location = item.get("candidate_required_location", "Anywhere")
            url = item.get("url", "")
            description = re.sub(r"<[^>]+>", " ", item.get("description", ""))
            description = re.sub(r"\s+", " ", description).strip()[:500]

            jobs.append(Job(
                title=title, company=company, location=location,
                url=url, description=description, source="remotive",
            ))
        return jobs

    # --- Jobspresso ---
    def _scrape_jobspresso(self, job_titles: list[str]) -> list[Job]:
        jobs = []
        for query in ["data-analyst", "marketing-analyst", "business-analyst", "growth-marketing"]:
            resp = requests.get(
                f"https://jobspresso.co/remote-work/{query}/",
                headers=self._headers(),
                timeout=15,
            )
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select(".job_listing, article")[:10]:
                title_el = card.select_one("h3 a, .job_listing-title a, a[href*='job']")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not self._title_relevant(title):
                    continue

                href = title_el.get("href", "")
                url = href if href.startswith("http") else f"https://jobspresso.co{href}"

                company_el = card.select_one(".company, .job_listing-company")
                company = company_el.get_text(strip=True) if company_el else ""

                jobs.append(Job(
                    title=title, company=company, location="Remote",
                    url=url, description="", source="jobspresso",
                ))
        return jobs

    # --- Working Nomads (RSS feed) ---
    def _scrape_working_nomads(self, job_titles: list[str]) -> list[Job]:
        resp = requests.get(
            "https://www.workingnomads.com/api/exposed_jobs/",
            headers=self._headers(),
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        jobs = []
        for item in resp.json()[:50]:
            title = item.get("title", "")
            if not self._title_relevant(title):
                continue

            pub_date = item.get("pub_date", "")
            if pub_date:
                try:
                    dt = datetime.fromisoformat(pub_date)
                    if dt.replace(tzinfo=None) < datetime.now() - timedelta(hours=72):
                        continue
                except (ValueError, TypeError):
                    pass

            company = item.get("company_name", "")
            location = item.get("location", "Remote")
            url = item.get("url", "")
            description = re.sub(r"<[^>]+>", " ", item.get("description", ""))[:500]

            jobs.append(Job(
                title=title, company=company, location=location,
                url=url, description=description, source="workingnomads",
            ))
        return jobs

    # --- AI-Jobs.net ---
    def _scrape_ai_jobs(self, job_titles: list[str]) -> list[Job]:
        resp = requests.get(
            "https://ai-jobs.net/",
            headers=self._headers(),
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = []

        for card in soup.select("article, .job-card, [class*='job'], tr")[:30]:
            title_el = card.select_one("a[href*='job'], h2 a, h3 a, td a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not self._title_relevant(title):
                continue

            href = title_el.get("href", "")
            url = href if href.startswith("http") else f"https://ai-jobs.net{href}"

            company_el = card.select_one("[class*='company'], td:nth-child(2)")
            company = company_el.get_text(strip=True) if company_el else ""

            location_el = card.select_one("[class*='location'], td:nth-child(3)")
            location = location_el.get_text(strip=True) if location_el else ""

            jobs.append(Job(
                title=title, company=company, location=location,
                url=url, description="", source="ai-jobs",
            ))
        return jobs

    # --- GovernmentJobs.com ---
    def _scrape_governmentjobs(self, job_titles: list[str]) -> list[Job]:
        jobs = []
        queries = ["data analyst", "business analyst", "financial analyst", "marketing analyst"]

        for query in queries:
            try:
                resp = requests.get(
                    "https://www.governmentjobs.com/careers/jobs",
                    params={"keyword": query, "sort": "PostDate|Descending", "page": "1"},
                    headers=self._headers(),
                    timeout=15,
                )
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                for card in soup.select(".job-listing, .job-item, [class*='job-result'], tr[class*='job']")[:10]:
                    title_el = card.select_one("a[href*='job'], h3 a, .job-title a")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if not self._title_relevant(title):
                        continue

                    href = title_el.get("href", "")
                    url = href if href.startswith("http") else f"https://www.governmentjobs.com{href}"

                    company_el = card.select_one("[class*='employer'], [class*='agency'], .department")
                    company = company_el.get_text(strip=True) if company_el else "Government"

                    location_el = card.select_one("[class*='location']")
                    location = location_el.get_text(strip=True) if location_el else ""

                    jobs.append(Job(
                        title=title, company=company, location=location,
                        url=url, description="", source="governmentjobs",
                    ))
            except Exception:
                continue
        return jobs
