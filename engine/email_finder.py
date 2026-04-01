"""
Find recruiter/hiring manager emails for job applications.

Uses free methods:
1. LinkedIn job poster info (already scraped)
2. Company email pattern guessing (firstname@company.com, etc.)
3. Hunter.io free tier (50 requests/month) if API key provided
"""

import os
import re
import requests


COMMON_PATTERNS = [
    "{first}@{domain}",
    "{first}.{last}@{domain}",
    "{first}{last}@{domain}",
    "{f}{last}@{domain}",
    "{first}_{last}@{domain}",
    "{first}.{l}@{domain}",
]


def guess_company_domain(company_name: str) -> str:
    """Guess the company's email domain from their name."""
    clean = company_name.lower().strip()
    clean = re.sub(r"[,.\-_&'\"!()]", "", clean)
    clean = re.sub(r"\s+", "", clean)

    # Common suffixes to try
    for suffix in [".com", ".io", ".co", ".ai"]:
        domain = clean + suffix
        return domain

    return clean + ".com"


def generate_email_guesses(
    first_name: str, last_name: str, company_name: str
) -> list[str]:
    """Generate possible email addresses for a person at a company."""
    domain = guess_company_domain(company_name)
    first = first_name.lower().strip()
    last = last_name.lower().strip()
    f = first[0] if first else ""
    l = last[0] if last else ""

    emails = []
    for pattern in COMMON_PATTERNS:
        email = (
            pattern.replace("{first}", first)
            .replace("{last}", last)
            .replace("{f}", f)
            .replace("{l}", l)
            .replace("{domain}", domain)
        )
        emails.append(email)

    return emails


def verify_email_hunter(email: str) -> bool:
    """Verify an email using Hunter.io free tier (if API key available)."""
    api_key = os.getenv("HUNTER_API_KEY", "").strip()
    if not api_key:
        return False

    try:
        resp = requests.get(
            "https://api.hunter.io/v2/email-verifier",
            params={"email": email, "api_key": api_key},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            return data.get("result") == "deliverable"
    except Exception:
        pass
    return False


def find_company_emails_hunter(
    domain: str, role_type: str = "marketing"
) -> list[dict]:
    """Search for emails at a company using Hunter.io."""
    api_key = os.getenv("HUNTER_API_KEY", "").strip()
    if not api_key:
        return []

    try:
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": api_key,
                "department": role_type,
                "limit": 5,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            return [
                {
                    "email": e["value"],
                    "name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
                    "position": e.get("position", ""),
                    "confidence": e.get("confidence", 0),
                }
                for e in data.get("emails", [])
            ]
    except Exception:
        pass
    return []


def find_recruiter_email(
    company_name: str,
    recruiter_name: str = "",
    role_type: str = "marketing",
) -> dict:
    """
    Find the best email to reach out to at a company.

    Returns: {"email": str, "name": str, "method": str, "confidence": str}
    """
    domain = guess_company_domain(company_name)

    # Method 1: Hunter.io domain search
    hunter_results = find_company_emails_hunter(domain, role_type)
    if hunter_results:
        best = max(hunter_results, key=lambda x: x["confidence"])
        return {
            "email": best["email"],
            "name": best["name"],
            "method": "hunter.io",
            "confidence": "high",
        }

    # Method 2: If we know the recruiter name, guess their email
    if recruiter_name:
        parts = recruiter_name.strip().split()
        if len(parts) >= 2:
            first = parts[0]
            last = parts[-1]
            guesses = generate_email_guesses(first, last, company_name)

            # If Hunter API available, verify
            for email in guesses:
                if verify_email_hunter(email):
                    return {
                        "email": email,
                        "name": recruiter_name,
                        "method": "pattern + verified",
                        "confidence": "high",
                    }

            # Return best guess without verification
            return {
                "email": guesses[0],  # first.last@domain.com
                "name": recruiter_name,
                "method": "pattern guess",
                "confidence": "medium",
            }

    # Method 3: Generic careers/hiring email
    return {
        "email": f"careers@{domain}",
        "name": "Hiring Team",
        "method": "generic",
        "confidence": "low",
    }
