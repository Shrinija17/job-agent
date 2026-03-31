"""Check company career pages for current relevant openings."""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


RELEVANT_KEYWORDS = [
    "data analyst", "business analyst", "product analyst",
    "marketing analyst", "analytics", "bi ", "business intelligence",
    "financial analyst", "reporting analyst",
]

# Domains that are email providers, not company sites
SKIP_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "aol.com", "icloud.com", "protonmail.com",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def enrich_contacts(contacts: list, max_workers: int = 10) -> tuple[list, int]:
    """
    Check career pages for each contact's company domain.
    Returns (enriched_contacts, count_with_openings).
    """
    # Group by domain to avoid duplicate requests
    domain_map: dict[str, list] = {}
    for c in contacts:
        if c.domain and c.domain not in SKIP_DOMAINS:
            domain_map.setdefault(c.domain, []).append(c)

    print(f"\n  Checking {len(domain_map)} unique company domains...\n")

    results: dict[str, list[str]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_check_domain, domain): domain
            for domain in domain_map
        }

        done = 0
        for future in as_completed(futures):
            domain = futures[future]
            done += 1
            try:
                openings = future.result()
                results[domain] = openings
                status = f"{len(openings)} relevant" if openings else "none"
                if openings:
                    print(f"  [{done}/{len(domain_map)}] {domain} -> {status}")
            except Exception:
                results[domain] = []

            # Progress every 50
            if done % 50 == 0 and not openings:
                print(f"  [{done}/{len(domain_map)}] checked...")

    # Apply results back to contacts
    enriched_count = 0
    for c in contacts:
        openings = results.get(c.domain, [])
        c.current_openings = openings
        if openings:
            enriched_count += 1

    return contacts, enriched_count


def _check_domain(domain: str) -> list[str]:
    """Try to find relevant job listings on a company's career page."""
    found = set()

    # 1. Try common career page paths on the company domain
    for path in ("/careers", "/jobs", "/open-positions", "/join-us"):
        url = f"https://{domain}{path}"
        matches = _scrape_for_keywords(url)
        found.update(matches)
        if found:
            return list(found)

    # 2. Try common ATS platforms using the domain prefix as slug
    slug = domain.split(".")[0]
    ats_urls = [
        f"https://boards.greenhouse.io/{slug}",
        f"https://jobs.lever.co/{slug}",
        f"https://jobs.ashbyhq.com/{slug}",
        f"https://{slug}.bamboohr.com/careers",
    ]
    for url in ats_urls:
        matches = _scrape_for_keywords(url)
        found.update(matches)
        if found:
            return list(found)

    return list(found)


def _scrape_for_keywords(url: str) -> list[str]:
    """Fetch a URL and check for relevant job keywords."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code != 200:
            return []

        text = resp.text.lower()
        # Skip tiny pages (error pages, redirects)
        if len(text) < 500:
            return []

        return [kw for kw in RELEVANT_KEYWORDS if kw in text]
    except Exception:
        return []
