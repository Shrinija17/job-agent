import re
from pathlib import Path

ROLE_KEYWORDS = {
    "01_Growth_Marketer": [
        "growth", "acquisition", "funnel", "lifecycle", "PLG", "product-led",
        "retention", "conversion", "CAC", "ROAS", "growth marketing",
    ],
    "02_Marketing_Analyst": [
        "marketing analyst", "campaign", "attribution", "marketing analytics",
        "media mix", "channel performance", "marketing ROI",
    ],
    "03_Data_Analyst": [
        "data analyst", "analytics", "dashboard", "reporting", "SQL",
        "data analysis", "metrics", "KPI", "visualization",
    ],
    "04_Business_Analyst": [
        "business analyst", "requirements", "process", "stakeholder",
        "BizOps", "strategy & operations", "operations analyst",
    ],
    "05_Business_Intelligence_Analyst": [
        "business intelligence", "BI", "data warehouse", "ETL", "BIE",
        "BI analyst", "BI engineer", "data engineering", "pipeline",
    ],
    "06_AI_Marketing_Specialist": [
        "AI marketing", "LLM", "generative AI", "AI-native", "automation",
        "AI specialist", "prompt engineering", "AI tools",
    ],
    "07_Social_Media_Analyst": [
        "social media", "content", "engagement", "community",
        "social analytics", "influencer", "social strategy",
    ],
    "08_Product_Analyst": [
        "product analyst", "product metrics", "user behavior", "product analytics",
        "A/B testing", "experimentation", "feature adoption", "product data",
    ],
    "09_Marketing_Data_Analyst": [
        "marketing data", "marketing analytics", "campaign data",
        "marketing measurement", "digital analytics", "web analytics",
    ],
    "10_Revenue_Operations_Analyst": [
        "RevOps", "revenue operations", "CRM", "salesforce", "HubSpot",
        "sales operations", "pipeline management", "forecasting",
    ],
    "11_Digital_Marketing_Analyst": [
        "digital marketing", "SEO", "SEM", "PPC", "paid media",
        "Google Ads", "Meta Ads", "performance marketing", "digital analyst",
    ],
    "12_AI_ML_Analyst": [
        "machine learning", "ML", "AI analyst", "NLP", "deep learning",
        "model", "prediction", "classification", "data science",
    ],
    "13_Analytics_Engineer": [
        "analytics engineer", "dbt", "data modeling", "data pipeline",
        "ELT", "transformation", "data infrastructure", "warehouse",
    ],
    "14_CRM_Marketing_Operations_Analyst": [
        "CRM", "marketing operations", "marketing ops", "email marketing",
        "lifecycle marketing", "Marketo", "Pardot", "Iterable",
    ],
    "15_Content_SEO_Analyst": [
        "content", "SEO", "keyword", "organic", "search engine",
        "content strategy", "AEO", "backlink", "SERP",
    ],
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "this", "that", "these",
    "those", "i", "you", "we", "they", "he", "she", "it", "my", "your",
    "our", "their", "its", "not", "no", "nor", "as", "if", "from",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


class ResumeSelector:
    """Select the best base resume from a catalog of role-specific resumes."""

    def __init__(self, catalog_dir: str):
        self.catalog_dir = Path(catalog_dir)
        self.resumes: dict[str, str] = {}  # filename -> full text

        # Load all numbered resume files
        for f in sorted(self.catalog_dir.glob("[0-9][0-9]_*.md")):
            self.resumes[f.stem] = f.read_text()

        if not self.resumes:
            raise ValueError(f"No resumes found in {catalog_dir}")

    def select_best(self, job_title: str, job_description: str) -> tuple[str, str]:
        """Return (resume_filename, resume_text) for the best matching resume."""
        scores = self._score_all(job_title, job_description)
        best = max(scores, key=scores.get)
        return best, self.resumes[best]

    def _score_all(self, job_title: str, job_description: str) -> dict[str, float]:
        title_tokens = _tokenize(job_title)
        desc_tokens = _tokenize(job_description)
        job_text_lower = f"{job_title} {job_description}".lower()

        scores = {}
        for name, text in self.resumes.items():
            score = 0.0

            # Get role keywords for this resume
            keywords = ROLE_KEYWORDS.get(name, [])

            # Multi-word phrase matching (most reliable signal)
            for kw in keywords:
                if kw.lower() in job_text_lower:
                    # Phrases in title are worth more
                    if kw.lower() in job_title.lower():
                        score += 15
                    else:
                        score += 5

            # Single-word keyword matching
            kw_tokens = set()
            for kw in keywords:
                kw_tokens.update(_tokenize(kw))

            title_hits = len(title_tokens & kw_tokens)
            desc_hits = len(desc_tokens & kw_tokens)
            score += title_hits * 3 + desc_hits * 1

            scores[name] = score

        return scores
