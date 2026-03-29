from dataclasses import dataclass, field
from datetime import datetime
from abc import ABC, abstractmethod


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    description: str
    source: str
    posted_date: str = ""
    score: float = 0.0
    tags: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        """Unique identifier for cross-source deduplication."""
        return f"{self.company}:{self.title}".lower().replace(" ", "_")

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "description": self.description[:500],
            "source": self.source,
            "posted_date": self.posted_date,
            "score": self.score,
            "seen_at": datetime.now().isoformat(),
        }


class BaseScraper(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def scrape(self, job_titles: list[str], **kwargs) -> list[Job]:
        """Return a list of Job objects matching the search criteria."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass
