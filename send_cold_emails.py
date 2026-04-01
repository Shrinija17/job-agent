#!/usr/bin/env python3
"""Send customized cold emails for non-sponsored job applications."""

import os
import time
import smtplib
import json
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from dotenv import load_dotenv

load_dotenv()

GMAIL = os.getenv("GMAIL_ADDRESS", "shrinijakummari1997@gmail.com")
APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip()

TEMPLATES = {
    "growth": {
        "opener": "With 2+ years driving growth through data at a YC-backed fintech startup and EA Games, I specialize in turning marketing data into acquisition strategies.",
        "bullets": [
            "Built a centralized marketing analytics dashboard (BigQuery + Streamlit + Cloud Run) tracking CAC, ROAS, and funnel metrics across 4 platforms, enabling data-driven acquisition decisions",
            "Automated daily marketing data pipelines via Cloud Functions + Cloud Scheduler, eliminating 10+ hrs/week of manual gathering and enabling real-time campaign optimization",
            "Partnered with marketing, product, and leadership to translate engagement data into actionable growth strategies at a YC-backed fintech startup",
        ],
    },
    "data": {
        "opener": "I'm a data analyst with 2+ years building automated dashboards, ETL pipelines, and analytical systems using SQL, Python, BigQuery, and Tableau.",
        "bullets": [
            "Built an end-to-end analytics platform (BigQuery + Streamlit + Cloud Run) with automated data ingestion from 4 APIs, real-time dashboards, and anomaly detection",
            "Wrote complex SQL queries (CTEs, window functions, aggregations) to compute KPIs, improving reporting accuracy by 30%+ and enabling real-time decision-making",
            "Developed a Python anomaly detection model identifying 98% of data inconsistencies, reducing manual corrections from 120 to 30 errors/month",
        ],
    },
    "bi": {
        "opener": "I'm a BI developer with 2+ years building data warehouses, ETL pipelines, and executive dashboards using SQL, Python, BigQuery, Tableau, and Power BI.",
        "bullets": [
            "Designed and optimized a BigQuery data warehouse with partitioned/clustered tables, improving query performance and reducing compute costs significantly",
            "Built automated Tableau dashboards consolidating 15+ KPIs, reducing manual reporting by 30% and enabling real-time decision-making for leadership",
            "Automated ETL workflows using Python and SQL, reducing batch processing time from 5 hours to 3 hours per cycle",
        ],
    },
    "digital": {
        "opener": "I'm a digital marketing analyst with 2+ years turning campaign data into optimization strategies using SQL, Python, Tableau, and cloud-native analytics tools.",
        "bullets": [
            "Built a marketing analytics dashboard tracking engagement rates, growth trends, and content performance across YouTube, Instagram, LinkedIn, and X",
            "Used SQL and Python to compute campaign ROI, ROAS, and attribution metrics, directly informing digital marketing spend decisions",
            "Created 11 reusable visualization functions for standardized reporting across all marketing platform dashboards",
        ],
    },
    "social": {
        "opener": "I'm a social media and content analyst with 2+ years building analytics systems that turn engagement data into content strategy.",
        "bullets": [
            "Built a social media analytics dashboard consolidating data from YouTube, Instagram, LinkedIn, and X with real-time engagement tracking and QoQ comparison",
            "Automated daily social data collection pipelines, eliminating 10+ hrs/week of manual data gathering across 4 platforms",
            "Created standardized visualization functions for content performance analysis, enabling data-driven social media strategy",
        ],
    },
}


def get_template_key(title: str) -> str:
    t = title.lower()
    if any(w in t for w in ["growth", "marketing manager", "field marketing", "integrated", "regional", "demand"]):
        return "growth"
    if any(w in t for w in ["bi ", "business intelligence"]):
        return "bi"
    if "digital" in t:
        return "digital"
    if any(w in t for w in ["social", "content"]):
        return "social"
    return "data"


def find_resume_pdf(resume_key: str) -> str | None:
    """Find the best matching PDF resume."""
    search_dirs = [
        Path.home() / "Desktop" / "PDFs",
        Path.home() / "Projects" / "job-agent" / "data" / "resumes",
    ]
    for d in search_dirs:
        if not d.exists():
            continue
        for f in d.glob("*.pdf"):
            if resume_key.replace("_", " ").lower() in f.stem.replace("_", " ").lower():
                return str(f)
    # Fallback to generic Data Analyst
    for d in search_dirs:
        for f in d.glob("*Data_Analyst*"):
            return str(f)
    return None


def build_email(role: str, company: str, template_key: str) -> str:
    tpl = TEMPLATES[template_key]
    return f"""Hi Hiring Team,

I came across the {role} opening at {company} and wanted to reach out directly.

{tpl['opener']}

A few highlights relevant to this role:
• {tpl['bullets'][0]}
• {tpl['bullets'][1]}
• {tpl['bullets'][2]}

I hold an M.S. in Data Analytics from Baruch College (Zicklin School of Business) and have experience with SQL, Python, BigQuery, Tableau, and AI/ML tools. I'm on STEM OPT and available to start immediately — no sponsorship needed for the next 2+ years.

I've attached my resume tailored for this role. Would love to chat if there's a fit.

Best,
Shrinija Kummari
+1 (201) 241-5870
linkedin.com/in/shrinija-kummari
github.com/Shrinija17
shrinija17.github.io"""


def send_email(to_addr: str, subject: str, body: str, pdf_path: str | None = None):
    msg = MIMEMultipart()
    msg["From"] = GMAIL
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if pdf_path and Path(pdf_path).exists():
        with open(pdf_path, "rb") as f:
            attachment = MIMEApplication(f.read(), _subtype="pdf")
            attachment.add_header(
                "Content-Disposition", "attachment", filename=Path(pdf_path).name
            )
            msg.attach(attachment)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL, APP_PASSWORD)
        server.send_message(msg)


# Jobs to email (from the Auto-Apply Notion page)
JOBS = [
    {"role": "Field Marketing Manager", "company": "Bretton AI", "resume": "Growth_Marketer", "url": "https://builtin.com/job/field-marketing-manager/8894082"},
    {"role": "Growth Marketing Manager", "company": "Atticus", "resume": "Growth_Marketer", "url": "https://builtin.com/job/growth-marketing-manager/8644562"},
    {"role": "Social Media Content Creator", "company": "Intryc", "resume": "Social_Media_Analyst", "url": "https://www.workatastartup.com/companies/intryc"},
    {"role": "Growth Marketing Manager", "company": "Prolific", "resume": "Growth_Marketer", "url": ""},
    {"role": "Growth Marketing Manager", "company": "TekStream Solutions", "resume": "Growth_Marketer", "url": ""},
    {"role": "Growth Marketing Manager", "company": "New Wave Recruiting", "resume": "Growth_Marketer", "url": ""},
    {"role": "Growth Marketing Analyst (E-Commerce)", "company": "Sunkissed Party Co", "resume": "Growth_Marketer", "url": ""},
    {"role": "Growth Marketing Manager", "company": "Robert Half", "resume": "Growth_Marketer", "url": ""},
    {"role": "Digital Marketing Analytics Manager", "company": "Monday Talent", "resume": "Digital_Marketing_Analyst", "url": ""},
    {"role": "Business Intelligence Developer", "company": "FAIRWINDS Credit Union", "resume": "Business_Intelligence_Analyst", "url": ""},
    {"role": "Integrated Marketing Manager", "company": "Flex", "resume": "Growth_Marketer", "url": ""},
    {"role": "Regional Marketing Manager", "company": "Nutrabolt", "resume": "Growth_Marketer", "url": ""},
    {"role": "Growth & Demand Marketing Manager", "company": "Jobgether", "resume": "Growth_Marketer", "url": ""},
    {"role": "Associate Digital Marketing Manager", "company": "Dexcom", "resume": "Growth_Marketer", "url": ""},
    {"role": "Digital Marketing Manager", "company": "Robert Half", "resume": "Digital_Marketing_Analyst", "url": ""},
    {"role": "Digital Marketing Manager", "company": "Phigora", "resume": "Digital_Marketing_Analyst", "url": ""},
    {"role": "Data Analyst, Economics", "company": "Chainlink Labs", "resume": "Data_Analyst", "url": ""},
    {"role": "Business Intelligence Developer", "company": "Haystack", "resume": "Business_Intelligence_Analyst", "url": ""},
    {"role": "Business Intelligence Developer", "company": "Akkodis", "resume": "Business_Intelligence_Analyst", "url": ""},
    {"role": "Business Intelligence Developer", "company": "accel bi corporation", "resume": "Business_Intelligence_Analyst", "url": ""},
    {"role": "Business Intelligence Developer", "company": "Sibitalent Corp", "resume": "Business_Intelligence_Analyst", "url": ""},
    {"role": "BI Analyst", "company": "Akraya, Inc.", "resume": "Business_Intelligence_Analyst", "url": ""},
    {"role": "BI Developer (Power BI)", "company": "Konnex4", "resume": "Business_Intelligence_Analyst", "url": ""},
    {"role": "BI Developer", "company": "OKAYA INFOCOM", "resume": "Business_Intelligence_Analyst", "url": ""},
]


def get_approved_jobs_from_notion():
    """Fetch jobs with 'Approved' status from the Auto-Apply Notion database."""
    token = os.getenv("NOTION_API_KEY", "").strip()
    if not token:
        print("No NOTION_API_KEY — falling back to local JOBS list")
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    db_id = "ad67fcfd-24a9-4bef-bdb6-28592dc736e1"

    resp = requests.post(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        headers=headers,
        json={
            "filter": {
                "property": "Auto-Apply",
                "select": {"equals": "Approved"},
            }
        },
        timeout=15,
    )

    if resp.status_code != 200:
        print(f"Notion query failed: {resp.status_code}")
        return None

    jobs = []
    for page in resp.json().get("results", []):
        props = page["properties"]
        title = props["Role"]["title"][0]["plain_text"] if props["Role"]["title"] else ""
        company = props["Company"]["rich_text"][0]["plain_text"] if props["Company"]["rich_text"] else ""
        resume = props["Resume Used"]["rich_text"][0]["plain_text"] if props["Resume Used"]["rich_text"] else "Data_Analyst"

        jobs.append({
            "role": title,
            "company": company,
            "resume": resume,
            "page_id": page["id"],
        })

    return jobs


def mark_email_sent(page_id: str):
    """Update Notion page status to 'Email Sent'."""
    token = os.getenv("NOTION_API_KEY", "").strip()
    if not token:
        return
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=headers,
        json={"properties": {"Auto-Apply": {"select": {"name": "Email Sent"}}}},
        timeout=15,
    )


import requests


def main():
    if not APP_PASSWORD:
        print("ERROR: GMAIL_APP_PASSWORD not set in .env")
        return

    # Try to get approved jobs from Notion first
    approved = get_approved_jobs_from_notion()

    if approved is not None:
        if not approved:
            print("No jobs with 'Approved' status in Notion. Change status to 'Approved' on jobs you want me to apply to.")
            return
        jobs_to_send = approved
        print(f"Found {len(jobs_to_send)} approved jobs in Notion.\n")
    else:
        jobs_to_send = [dict(j, page_id=None) for j in JOBS]
        print(f"Using local list: {len(jobs_to_send)} jobs.\n")

    sent = 0
    for job in jobs_to_send:
        tpl_key = get_template_key(job["role"])
        subject = f"{job['role']} — Shrinija Kummari | Available Immediately"
        body = build_email(job["role"], job["company"], tpl_key)
        pdf = find_resume_pdf(job["resume"])

        company_slug = job["company"].lower().replace(" ", "").replace(",", "").replace(".", "").replace("'", "")
        to_addr = f"careers@{company_slug}.com"

        try:
            send_email(to_addr, subject, body, pdf)
            sent += 1
            print(f"  ✓ [{sent}] {job['role']} @ {job['company']} → {to_addr}")
            if pdf:
                print(f"    📎 {Path(pdf).name}")

            # Mark as sent in Notion
            if job.get("page_id"):
                mark_email_sent(job["page_id"])
                print(f"    ✓ Notion updated: Email Sent")
        except Exception as e:
            print(f"  ✗ {job['role']} @ {job['company']}: {e}")

        time.sleep(30)

    print(f"\n🎯 Done! {sent}/{len(jobs_to_send)} emails sent.")


if __name__ == "__main__":
    main()
