"""Load and filter H1B recruiter contacts from DOL CSV."""

import csv
from dataclasses import dataclass, field


@dataclass
class Contact:
    company: str
    role_filed: str
    hr_name: str
    hr_title: str
    hr_email: str
    hr_phone: str
    city: str
    state: str
    salary: str
    status: str = "Not Contacted"
    notes: str = ""
    tier: int = 0
    domain: str = ""
    current_openings: list = field(default_factory=list)
    draft_subject: str = ""
    draft_body: str = ""

    def __post_init__(self):
        if "@" in self.hr_email:
            self.domain = self.hr_email.split("@")[1].lower()

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "role_filed": self.role_filed,
            "hr_name": self.hr_name,
            "hr_title": self.hr_title,
            "hr_email": self.hr_email,
            "hr_phone": self.hr_phone,
            "city": self.city,
            "state": self.state,
            "salary": self.salary,
            "status": self.status,
            "notes": self.notes,
            "tier": self.tier,
            "domain": self.domain,
            "current_openings": self.current_openings,
            "draft_subject": self.draft_subject,
            "draft_body": self.draft_body,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Contact":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# Roles that directly match Shrinija's target positions
TIER_1_KEYWORDS = [
    "data analyst", "business analyst", "product analyst",
    "marketing analyst", "bi analyst", "business intelligence analyst",
    "analytics engineer", "financial analyst", "growth marketing",
    "marketing data analyst", "digital marketing analyst",
    "social media analyst", "crm analyst", "reporting analyst",
    "bi engineer", "business intelligence engineer",
    "revenue analyst", "operations analyst",
]

# Adjacent roles — company hires in the data/analytics space
TIER_2_KEYWORDS = [
    "data engineer", "data scientist", "analytics",
    "machine learning engineer", "business intelligence",
    "etl", "data warehouse", "data operations",
    "analytics manager", "data science",
]

# Roles that are clearly irrelevant
EXCLUDE_KEYWORDS = [
    "mechanical", "electrical", "civil", "chemical",
    "hardware", "embedded", "firmware", "fpga",
    "nurse", "physician", "clinical", "pharmacy", "dental",
    "attorney", "lawyer", "paralegal",
    "accountant", "auditor", "tax manager",
    "architect",  # building architect, not data
]


def load_and_filter(csv_path: str) -> tuple[list[Contact], dict]:
    """Load CSV, filter to relevant contacts. Returns (contacts, stats)."""
    contacts = []
    stats = {"total": 0, "tier_1": 0, "tier_2": 0, "skipped": 0}

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats["total"] += 1
            role_lower = row.get("Role Filed", "").lower()

            # Skip excluded roles
            if any(kw in role_lower for kw in EXCLUDE_KEYWORDS):
                stats["skipped"] += 1
                continue

            # Classify tier
            tier = 0
            if any(kw in role_lower for kw in TIER_1_KEYWORDS):
                tier = 1
                stats["tier_1"] += 1
            elif any(kw in role_lower for kw in TIER_2_KEYWORDS):
                tier = 2
                stats["tier_2"] += 1
            else:
                stats["skipped"] += 1
                continue

            contact = Contact(
                company=row.get("Company", "").strip(),
                role_filed=row.get("Role Filed", "").strip(),
                hr_name=row.get("HR Contact", "").strip(),
                hr_title=row.get("HR Title", "").strip(),
                hr_email=row.get("HR Email", "").strip(),
                hr_phone=row.get("HR Phone", "").strip(),
                city=row.get("Worksite City", "").strip(),
                state=row.get("Worksite State", "").strip(),
                salary=row.get("Salary", "").strip(),
                status=row.get("Status", "Not Contacted").strip(),
                notes=row.get("Notes", "").strip(),
                tier=tier,
            )
            contacts.append(contact)

    return contacts, stats


def deduplicate(contacts: list[Contact]) -> list[Contact]:
    """One contact per company. Prefer Tier 1 roles, then HR/TA titles over execs."""
    by_company: dict[str, Contact] = {}

    for c in contacts:
        key = c.company.lower().strip()
        if key not in by_company:
            by_company[key] = c
        else:
            existing = by_company[key]
            # Prefer higher tier (lower number = better)
            if c.tier < existing.tier:
                by_company[key] = c
            elif c.tier == existing.tier:
                # Prefer HR/TA contacts over CEO/President for outreach
                if _is_hr_role(c.hr_title) and not _is_hr_role(existing.hr_title):
                    by_company[key] = c

    result = sorted(by_company.values(), key=lambda c: (c.tier, c.company.lower()))
    return result


def _is_hr_role(title: str) -> bool:
    """HR/TA contacts are better for cold outreach than CEOs."""
    t = title.lower()
    return any(kw in t for kw in [
        "talent", "recruiting", "recruiter", "hr ",
        "human resource", "people", "immigration",
        "mobility", "acquisition", "staffing",
    ])
