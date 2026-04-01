#!/usr/bin/env python3
"""
Daily Job Report — sends a morning summary email.

Reports:
- New jobs found today
- Jobs applied (by Wall-E vs Shrinija)
- Response rate
- Jobs to follow up on
- Top new matches to apply to
"""

import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY", "").strip()
GMAIL = os.getenv("GMAIL_ADDRESS", "shrinijakummari1997@gmail.com")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip()
DB_ID = "37ee728874894648b4a3f0a8b973dd74"


def get_all_jobs():
    """Fetch all jobs from the Job Command Center."""
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    all_pages = []
    has_more = True
    start_cursor = None

    while has_more:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        resp = requests.post(
            f"https://api.notion.com/v1/databases/{DB_ID}/query",
            headers=headers,
            json=body,
            timeout=15,
        )
        data = resp.json()
        all_pages.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return all_pages


def build_report(jobs):
    """Build the daily report HTML."""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Categorize
    total = len(jobs)
    new_today = 0
    applied_total = 0
    applied_walle = 0
    applied_shrinija = 0
    interviews = 0
    rejections = 0
    no_response = 0
    sponsorship_jobs = []
    top_new = []

    for page in jobs:
        props = page["properties"]
        created = page.get("created_time", "")[:10]
        status = props.get("Status", {}).get("select", {})
        status_name = status.get("name", "New") if status else "New"
        applied_by = props.get("Applied By", {}).get("select", {})
        applied_name = applied_by.get("name", "") if applied_by else ""
        response = props.get("Response", {}).get("select", {})
        response_name = response.get("name", "") if response else ""
        sponsor = props.get("Sponsorship", {}).get("select", {})
        sponsor_name = sponsor.get("name", "") if sponsor else ""
        score = props.get("Score", {}).get("number", 0) or 0

        title_data = props.get("Role", {}).get("title", [])
        title = title_data[0]["plain_text"] if title_data else "?"
        company_data = props.get("Company", {}).get("rich_text", [])
        company = company_data[0]["plain_text"] if company_data else "?"
        url_data = props.get("Apply Link", {})
        url = url_data.get("url", "") if isinstance(url_data, dict) else ""

        if created >= yesterday:
            new_today += 1

        if status_name == "Applied":
            applied_total += 1
            if applied_name == "Wall-E":
                applied_walle += 1
            elif applied_name == "Shrinija":
                applied_shrinija += 1

        if response_name == "Interview" or status_name == "Interview":
            interviews += 1
        if response_name == "Rejected" or status_name == "Rejected":
            rejections += 1
        if applied_total > 0 and response_name == "No Response":
            no_response += 1

        if sponsor_name in ("Sponsors", "E-Verify") and status_name == "New":
            sponsorship_jobs.append((score, title, company, url))

        if status_name == "New" and score >= 40:
            top_new.append((score, title, company, url))

    top_new.sort(reverse=True)
    sponsorship_jobs.sort(reverse=True)

    # Build HTML
    response_rate = f"{((interviews / applied_total) * 100):.0f}%" if applied_total > 0 else "N/A"

    top_new_rows = ""
    for score, title, company, url in top_new[:10]:
        top_new_rows += f'<tr><td>{score:.0f}</td><td><a href="{url}">{title}</a></td><td>{company}</td></tr>'

    sponsor_rows = ""
    for score, title, company, url in sponsorship_jobs[:5]:
        sponsor_rows += f'<tr><td><a href="{url}">{title}</a></td><td>{company}</td></tr>'

    html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;">
        <h2>Job Agent Daily Report — {today}</h2>

        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <tr style="background:#f1f5f9;">
                <td style="padding:12px;font-size:24px;font-weight:bold;color:#2563eb;">{total}</td>
                <td style="padding:12px;">Total jobs tracked</td>
            </tr>
            <tr>
                <td style="padding:12px;font-size:24px;font-weight:bold;color:#22c55e;">{new_today}</td>
                <td style="padding:12px;">New jobs found (last 24h)</td>
            </tr>
            <tr style="background:#f1f5f9;">
                <td style="padding:12px;font-size:24px;font-weight:bold;color:#8b5cf6;">{applied_total}</td>
                <td style="padding:12px;">Total applied ({applied_walle} by Wall-E, {applied_shrinija} by you)</td>
            </tr>
            <tr>
                <td style="padding:12px;font-size:24px;font-weight:bold;color:#eab308;">{interviews}</td>
                <td style="padding:12px;">Interviews / Phone screens</td>
            </tr>
            <tr style="background:#f1f5f9;">
                <td style="padding:12px;font-size:24px;font-weight:bold;">{response_rate}</td>
                <td style="padding:12px;">Response rate</td>
            </tr>
        </table>

        <h3>Top New Jobs to Apply To</h3>
        <table style="width:100%;border-collapse:collapse;">
            <thead><tr style="background:#f1f5f9;">
                <th style="padding:8px;text-align:left;">Score</th>
                <th style="padding:8px;text-align:left;">Role</th>
                <th style="padding:8px;text-align:left;">Company</th>
            </tr></thead>
            <tbody>{top_new_rows}</tbody>
        </table>

        <h3>Sponsorship Jobs — Apply Yourself</h3>
        <table style="width:100%;border-collapse:collapse;">
            <thead><tr style="background:#f1f5f9;">
                <th style="padding:8px;text-align:left;">Role</th>
                <th style="padding:8px;text-align:left;">Company</th>
            </tr></thead>
            <tbody>{sponsor_rows if sponsor_rows else '<tr><td colspan="2">None pending</td></tr>'}</tbody>
        </table>

        <p style="color:#94a3b8;font-size:12px;margin-top:24px;">
            Generated by Wall-E Job Agent • Next scan in 4 hours
        </p>
    </body>
    </html>
    """
    return html


def send_report(html):
    """Send the report via Gmail."""
    if not GMAIL_PASSWORD:
        print("No GMAIL_APP_PASSWORD — saving locally instead")
        with open("output/daily_report.html", "w") as f:
            f.write(html)
        return

    today = datetime.now().strftime("%B %d, %Y")
    msg = MIMEMultipart()
    msg["From"] = GMAIL
    msg["To"] = GMAIL
    msg["Subject"] = f"Job Agent Report — {today}"
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL, GMAIL_PASSWORD)
            server.send_message(msg)
        print(f"Report sent to {GMAIL}")
    except Exception as e:
        print(f"Failed to send: {e}")
        with open("output/daily_report.html", "w") as f:
            f.write(html)


def main():
    print("Generating daily report...")
    jobs = get_all_jobs()
    html = build_report(jobs)
    send_report(html)


if __name__ == "__main__":
    main()
