#!/usr/bin/env python3
"""
Job Agent — Finds jobs across the internet, picks the best resume, tailors it, generates PDFs.

Usage:
    python main.py                    # Full run (scrape → filter → tailor → PDF → Notion)
    python main.py --dry-run          # Scrape and show jobs, but don't tailor
    python main.py --manual           # Paste a job description, get a tailored resume + PDF
    python main.py --url URL          # Fetch a job page and tailor resume for it
    python main.py --no-email         # Skip email, save report locally
    python main.py --top N            # Override how many top jobs to tailor (default: 10)
"""

import argparse
import os
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
from dotenv import load_dotenv


def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def run_scrapers(config: dict) -> list:
    """Run all enabled scrapers in parallel."""
    from scrapers import (
        LinkedInScraper,
        AmazonJobsScraper,
        BuiltInScraper,
        YCJobsScraper,
        GreenhouseLeverScraper,
        GoogleJobsScraper,
        RemoteBoardsScraper,
        FirecrawlBoardsScraper,
    )

    scrapers_config = config.get("scrapers", {})
    job_titles = config.get("job_titles", [])
    all_jobs = []

    scraper_classes = {
        "linkedin": LinkedInScraper,
        "amazon": AmazonJobsScraper,
        "builtin": BuiltInScraper,
        "yc_jobs": YCJobsScraper,
        "greenhouse_lever": GreenhouseLeverScraper,
        "remote_boards": RemoteBoardsScraper,
        "firecrawl_boards": FirecrawlBoardsScraper,
        "google_jobs": GoogleJobsScraper,
    }

    enabled_scrapers = []
    for name, cls in scraper_classes.items():
        sc = scrapers_config.get(name, {})
        if sc.get("enabled", False):
            enabled_scrapers.append((name, cls(sc)))

    if not enabled_scrapers:
        print("No scrapers enabled in config.yaml")
        return []

    print(f"\n🔍 Running {len(enabled_scrapers)} scrapers...\n")

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {}
        for name, scraper in enabled_scrapers:
            future = executor.submit(scraper.scrape, job_titles)
            futures[future] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                jobs = future.result()
                all_jobs.extend(jobs)
            except Exception as e:
                print(f"  [{name}] Failed: {e}")

    return all_jobs


def run_daily(config: dict, dry_run: bool = False, send_email: bool = True, top_n: int = None):
    """Full pipeline: scrape → filter → select resume → tailor → PDF → Notion."""
    from engine import JobFilter, ResumeTailor, PDFGenerator, ResumeSelector
    from notifier import EmailNotifier
    from notifier.notion_pusher import NotionPusher

    # 1. Scrape
    raw_jobs = run_scrapers(config)
    print(f"\n📥 Found {len(raw_jobs)} raw jobs across all sources\n")

    if not raw_jobs:
        print("No jobs found. Check your scraper configuration or try --manual mode.")
        return

    # 2. Filter and score
    seen_path = Path(__file__).parent / config.get("seen_jobs_file", "data/seen_jobs.json")
    job_filter = JobFilter(config, str(seen_path))
    filtered_jobs = job_filter.filter_and_score(raw_jobs)
    print(f"✅ {len(filtered_jobs)} jobs passed filters (from {len(raw_jobs)} raw)\n")

    if not filtered_jobs:
        print("No new jobs passed filters today. All caught up!")
        return

    # Show top results
    n = top_n or config.get("top_n_to_tailor", 10)
    top_jobs = filtered_jobs[:n]

    print(f"🏆 Top {len(top_jobs)} jobs:\n")
    for i, job in enumerate(top_jobs, 1):
        print(f"  {i}. [{job.score:.0f}] {job.title} @ {job.company}")
        print(f"     📍 {job.location} | 🔗 {job.url}")
        print()

    if dry_run:
        print("(Dry run — skipping tailoring)\n")
        job_filter.save_seen(top_jobs)

        # Save full list to report
        today = datetime.now().strftime("%Y-%m-%d")
        report_path = Path(__file__).parent / config.get("output_dir", "output") / f"dry_run_{today}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# Job Agent — Dry Run {today}\n", f"**{len(filtered_jobs)} jobs** passed filters (from {len(raw_jobs)} raw)\n"]
        for i, job in enumerate(filtered_jobs, 1):
            lines.append(f"{i}. **[{job.score:.0f}]** [{job.title} @ {job.company}]({job.url}) — {job.location}")
        report_path.write_text("\n".join(lines))
        print(f"📄 Full list saved to {report_path}\n")

        # Push to Notion
        notion_config = config.get("notion", {})
        if notion_config.get("enabled"):
            print("📋 Pushing to Notion...\n")
            pusher = NotionPusher(notion_config.get("database_id", ""))
            pusher.push_jobs(filtered_jobs[:50])

        if len(filtered_jobs) > n:
            print(f"\n--- All {len(filtered_jobs)} filtered jobs ---\n")
            for i, job in enumerate(filtered_jobs, 1):
                print(f"  {i}. [{job.score:.0f}] {job.title} @ {job.company} — {job.location}")
        return

    # 3. Select best resume + Tailor
    print("📝 Selecting resumes & tailoring...\n")
    catalog_dir = config.get("resume_catalog_dir", "data/resumes/")
    selector = ResumeSelector(catalog_dir)

    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path(__file__).parent / config.get("output_dir", "output") / today
    pdf_gen = PDFGenerator(str(output_dir))

    pdf_paths = []
    match_analyses = []
    resume_names = []

    for i, job in enumerate(top_jobs, 1):
        print(f"  [{i}/{len(top_jobs)}] {job.title} @ {job.company}...")
        try:
            # Pick the best base resume for this job
            resume_name, resume_text = selector.select_best(job.title, job.description)
            resume_names.append(resume_name)
            print(f"    📄 Using: {resume_name}")

            # Create a tailor with the selected resume
            tailor = ResumeTailor(resume_text)

            # Tailor the resume
            tailored_text = tailor.tailor(job.title, job.company, job.description)

            # Generate PDF
            safe_name = f"{job.company}_{job.title}".replace(" ", "_")
            pdf_path = pdf_gen.generate(tailored_text, safe_name)
            pdf_paths.append(pdf_path)

            # Quick match analysis
            analysis = tailor.quick_match_analysis(job.description)
            match_analyses.append(analysis)

            # Save markdown
            md_path = output_dir / f"Shrinija_Kummari_{safe_name}.md"
            md_path.write_text(tailored_text)

            # Copy to Desktop
            import shutil
            desktop_path = Path.home() / "Desktop" / Path(pdf_path).name
            shutil.copy2(pdf_path, desktop_path)

            print(f"    ✓ PDF: {Path(pdf_path).name}")
        except Exception as e:
            print(f"    ✗ Error: {e}")
            pdf_paths.append("")
            match_analyses.append(f"Error: {e}")
            resume_names.append("")

    # 4. Push to Notion
    notion_config = config.get("notion", {})
    if notion_config.get("enabled"):
        print("\n📋 Pushing to Notion...\n")
        pusher = NotionPusher(notion_config.get("database_id", ""))
        pusher.push_jobs(top_jobs, pdf_paths, resume_names)

    # 5. Send email digest
    print("\n📧 Sending digest...\n")
    notifier = EmailNotifier(config.get("email", {}))
    if send_email and notifier.is_configured:
        notifier.send_digest(top_jobs, pdf_paths, match_analyses)
    else:
        notifier._save_local_report(top_jobs, pdf_paths, match_analyses)

    # 6. Mark as seen
    job_filter.save_seen(top_jobs)

    print(f"\n🎯 Done! {len([p for p in pdf_paths if p])} tailored resumes ready in {output_dir}\n")


def run_manual(config: dict):
    """Interactive mode: paste a JD, get a tailored resume + PDF."""
    from engine import ResumeTailor, PDFGenerator, ResumeSelector

    print("\n📋 Manual Mode — Paste a job description (press Ctrl+D or type END when done):\n")

    lines = []
    try:
        while True:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
    except EOFError:
        pass

    jd_text = "\n".join(lines).strip()
    if not jd_text:
        print("No job description provided.")
        return

    print()
    job_title = input("Job title: ").strip() or "Unknown Role"
    company = input("Company: ").strip() or "Unknown Company"

    # Select best resume
    catalog_dir = config.get("resume_catalog_dir", "data/resumes/")
    selector = ResumeSelector(catalog_dir)
    resume_name, resume_text = selector.select_best(job_title, jd_text)
    print(f"\n📄 Best resume match: {resume_name}")
    print(f"📝 Tailoring for {job_title} @ {company}...\n")

    tailor = ResumeTailor(resume_text)
    tailored_text = tailor.tailor(job_title, company, jd_text)

    analysis = tailor.quick_match_analysis(jd_text)
    print(f"Match Analysis:\n{analysis}\n")

    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path(__file__).parent / config.get("output_dir", "output") / today
    pdf_gen = PDFGenerator(str(output_dir))

    safe_name = f"{company}_{job_title}".replace(" ", "_")
    pdf_path = pdf_gen.generate(tailored_text, safe_name)

    md_path = output_dir / f"Shrinija_Kummari_{safe_name}.md"
    md_path.write_text(tailored_text)

    import shutil
    desktop_path = Path.home() / "Desktop" / Path(pdf_path).name
    shutil.copy2(pdf_path, desktop_path)

    print(f"✅ Resume tailored!\n")
    print(f"   PDF: {pdf_path}")
    print(f"   Desktop: {desktop_path}")
    print(f"   Markdown: {md_path}")


def run_url(config: dict, url: str):
    """Fetch a job page and tailor resume for it."""
    import requests
    from bs4 import BeautifulSoup
    from engine import ResumeTailor, PDFGenerator, ResumeSelector

    print(f"\n🌐 Fetching {url}...\n")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    title = ""
    for selector in ["h1", "[class*='title']", "title"]:
        el = soup.select_one(selector)
        if el:
            title = el.get_text(strip=True)
            break

    company = ""
    for selector in ["[class*='company']", "[class*='employer']", "[class*='org']"]:
        el = soup.select_one(selector)
        if el:
            company = el.get_text(strip=True)
            break

    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    description = soup.get_text(separator="\n", strip=True)[:6000]

    if not title:
        title = input("Could not detect job title. Enter it: ").strip()
    if not company:
        company = input("Could not detect company. Enter it: ").strip()

    print(f"  Title: {title}")
    print(f"  Company: {company}")

    # Select best resume
    catalog_dir = config.get("resume_catalog_dir", "data/resumes/")
    selector = ResumeSelector(catalog_dir)
    resume_name, resume_text = selector.select_best(title, description)
    print(f"  Resume: {resume_name}\n")

    tailor = ResumeTailor(resume_text)
    tailored_text = tailor.tailor(title, company, description)
    analysis = tailor.quick_match_analysis(description)
    print(f"Match Analysis:\n{analysis}\n")

    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path(__file__).parent / config.get("output_dir", "output") / today
    pdf_gen = PDFGenerator(str(output_dir))

    safe_name = f"{company}_{title}".replace(" ", "_")
    pdf_path = pdf_gen.generate(tailored_text, safe_name)

    md_path = output_dir / f"Shrinija_Kummari_{safe_name}.md"
    md_path.write_text(tailored_text)

    import shutil
    desktop_path = Path.home() / "Desktop" / Path(pdf_path).name
    shutil.copy2(pdf_path, desktop_path)

    print(f"✅ Resume tailored!\n")
    print(f"   PDF: {pdf_path}")
    print(f"   Desktop: {desktop_path}")


def main():
    os.chdir(Path(__file__).parent)
    load_dotenv()

    parser = argparse.ArgumentParser(description="Job Agent — Your automated job hunter")
    parser.add_argument("--dry-run", action="store_true", help="Scrape and show jobs only")
    parser.add_argument("--manual", action="store_true", help="Paste a JD, get a tailored resume")
    parser.add_argument("--url", type=str, help="Fetch a job URL and tailor resume")
    parser.add_argument("--no-email", action="store_true", help="Skip email, save locally")
    parser.add_argument("--top", type=int, help="Number of top jobs to tailor")

    args = parser.parse_args()
    config = load_config()

    print("=" * 60)
    print(f"  Job Agent — {datetime.now().strftime('%B %d, %Y %I:%M %p')}")
    print("=" * 60)

    if args.manual:
        run_manual(config)
    elif args.url:
        run_url(config, args.url)
    else:
        run_daily(
            config,
            dry_run=args.dry_run,
            send_email=not args.no_email,
            top_n=args.top,
        )


if __name__ == "__main__":
    main()
