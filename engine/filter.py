import json
import re
from pathlib import Path
from scrapers.base import Job


class JobFilter:
    """Filter and score jobs based on config criteria."""

    def __init__(self, config: dict, seen_jobs_path: str):
        self.job_titles = [t.lower() for t in config.get("job_titles", [])]
        self.include_kw = [k.lower() for k in config.get("include_keywords", [])]
        self.exclude_kw = [k.lower() for k in config.get("exclude_keywords", [])]
        self.max_exp_years = config.get("exclude_experience_years", 5)
        self.seen_jobs_path = Path(seen_jobs_path)
        self.seen_jobs = self._load_seen()

    def _load_seen(self) -> dict:
        if self.seen_jobs_path.exists():
            return json.loads(self.seen_jobs_path.read_text())
        return {}

    def save_seen(self, jobs: list[Job]):
        """Mark jobs as seen so we don't show them again."""
        for job in jobs:
            self.seen_jobs[job.id] = job.to_dict()
        self.seen_jobs_path.write_text(json.dumps(self.seen_jobs, indent=2))

    def filter_and_score(self, jobs: list[Job]) -> list[Job]:
        """Filter out bad matches and score the rest. Returns sorted by score desc."""
        filtered = []
        for job in jobs:
            # Skip already seen
            if job.id in self.seen_jobs:
                continue

            # Skip excluded
            if self._is_excluded(job):
                continue

            # Skip if experience requirement too high
            if self._exceeds_experience(job):
                continue

            # Score it
            job.score = self._score(job)

            if job.score > 0:
                filtered.append(job)

        # Sort by score descending
        filtered.sort(key=lambda j: j.score, reverse=True)
        return filtered

    def _is_excluded(self, job: Job) -> bool:
        """Check if job matches any exclusion keywords."""
        text = f"{job.title} {job.description} {job.company}".lower()
        for kw in self.exclude_kw:
            if kw in text:
                return True
        return False

    def _exceeds_experience(self, job: Job) -> bool:
        """Check if job requires more experience than the threshold."""
        text = job.description.lower()
        # Match patterns like "5+ years", "5-7 years", "minimum 5 years"
        patterns = [
            r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
            r"minimum\s+(\d+)\s*(?:years?|yrs?)",
            r"(\d+)\s*-\s*\d+\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                years = int(match)
                if years >= self.max_exp_years:
                    return True
        return False

    def _score(self, job: Job) -> float:
        """Score a job 0-100 based on relevance."""
        score = 0.0
        title_lower = job.title.lower()
        text_lower = f"{job.title} {job.description} {job.company}".lower()

        # Title match (0-50 points) — weighted by priority order
        for i, target_title in enumerate(self.job_titles):
            # Fuzzy title matching — check if key words overlap
            target_words = set(target_title.split())
            title_words = set(title_lower.split())
            overlap = target_words & title_words

            if len(overlap) >= 2 or target_title in title_lower:
                # Higher priority titles get more points
                priority_bonus = max(0, 15 - i)  # Top titles get up to 15 bonus
                score += 35 + priority_bonus
                break
            elif len(overlap) >= 1:
                priority_bonus = max(0, 10 - i)
                score += 20 + priority_bonus
                break

        # Keyword matches (0-30 points)
        kw_hits = sum(1 for kw in self.include_kw if kw in text_lower)
        score += min(30, kw_hits * 3)

        # Seniority penalty — these roles are too senior
        senior_prefixes = ["senior", "sr.", "sr ", "staff", "lead", "principal", "director", "vp", "head of", "manager,"]
        for prefix in senior_prefixes:
            if title_lower.startswith(prefix) or f", {prefix}" in title_lower:
                score -= 20
                break

        # Intern penalty — too junior
        if "intern" in title_lower:
            score -= 15

        # Bonus signals (0-20 points)
        if "yc" in text_lower or "y combinator" in text_lower:
            score += 8
        if "startup" in text_lower or "early-stage" in text_lower:
            score += 5
        if "remote" in text_lower or "hybrid" in text_lower:
            score += 3
        if "no sponsorship" not in text_lower and "visa" not in text_lower:
            score += 2  # No explicit visa restriction
        if "entry" in text_lower or "junior" in text_lower or "0-2" in text_lower:
            score += 2

        return max(0, min(100, score))
