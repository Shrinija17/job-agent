"""
Apply to jobs on Greenhouse and Lever career pages using requests.

Greenhouse and Lever have standardized form endpoints that accept
multipart form data — no browser automation needed.
"""

import os
import re
import requests
from pathlib import Path


APPLICANT_INFO = {
    "first_name": "Shrinija",
    "last_name": "Kummari",
    "email": "shrinijakummari1997@gmail.com",
    "phone": "+12012419870",
    "location": "Seattle, WA",
    "linkedin": "https://linkedin.com/in/shrinija-kummari",
    "website": "https://shrinija17.github.io",
    "work_auth": "Yes",
    "sponsorship_needed": "No",
}


def apply_greenhouse(job_url: str, resume_path: str) -> dict:
    """
    Apply to a Greenhouse job posting.

    Greenhouse apply URLs look like:
    https://boards.greenhouse.io/company/jobs/12345
    The form submits to: https://boards.greenhouse.io/company/jobs/12345/apply

    Returns: {"success": bool, "message": str}
    """
    try:
        # Extract the apply endpoint
        if "/apply" not in job_url:
            apply_url = job_url.rstrip("/") + "/apply"
        else:
            apply_url = job_url

        # First GET the form to find the token
        resp = requests.get(job_url, timeout=15)
        if resp.status_code != 200:
            return {"success": False, "message": f"Could not load job page: {resp.status_code}"}

        # Find the authenticity token
        token_match = re.search(r'name="authenticity_token"[^>]*value="([^"]+)"', resp.text)
        token = token_match.group(1) if token_match else ""

        # Find the job_application form fields
        form_data = {
            "authenticity_token": token,
            "job_application[first_name]": APPLICANT_INFO["first_name"],
            "job_application[last_name]": APPLICANT_INFO["last_name"],
            "job_application[email]": APPLICANT_INFO["email"],
            "job_application[phone]": APPLICANT_INFO["phone"],
            "job_application[location]": APPLICANT_INFO["location"],
            "job_application[urls][LinkedIn]": APPLICANT_INFO["linkedin"],
            "job_application[urls][Portfolio]": APPLICANT_INFO["website"],
        }

        # Attach resume
        files = {}
        if resume_path and Path(resume_path).exists():
            files["job_application[resume]"] = (
                Path(resume_path).name,
                open(resume_path, "rb"),
                "application/pdf",
            )

        # Submit
        submit_resp = requests.post(
            apply_url,
            data=form_data,
            files=files if files else None,
            headers={"Referer": job_url},
            timeout=30,
        )

        if submit_resp.status_code in (200, 302):
            return {"success": True, "message": "Application submitted via Greenhouse"}
        else:
            return {"success": False, "message": f"Greenhouse returned {submit_resp.status_code}"}

    except Exception as e:
        return {"success": False, "message": str(e)}


def apply_lever(job_url: str, resume_path: str) -> dict:
    """
    Apply to a Lever job posting.

    Lever apply URLs: https://jobs.lever.co/company/job-id/apply
    The form submits via multipart POST.

    Returns: {"success": bool, "message": str}
    """
    try:
        # Construct apply URL
        if "/apply" not in job_url:
            apply_url = job_url.rstrip("/") + "/apply"
        else:
            apply_url = job_url

        form_data = {
            "name": f"{APPLICANT_INFO['first_name']} {APPLICANT_INFO['last_name']}",
            "email": APPLICANT_INFO["email"],
            "phone": APPLICANT_INFO["phone"],
            "org": "JustPaid (YC W23)",
            "urls[LinkedIn]": APPLICANT_INFO["linkedin"],
            "urls[Portfolio]": APPLICANT_INFO["website"],
            "comments": "I am on STEM OPT and available to start immediately. No sponsorship needed for 2+ years.",
        }

        files = {}
        if resume_path and Path(resume_path).exists():
            files["resume"] = (
                Path(resume_path).name,
                open(resume_path, "rb"),
                "application/pdf",
            )

        resp = requests.post(
            apply_url,
            data=form_data,
            files=files if files else None,
            headers={
                "Referer": job_url,
                "Origin": "https://jobs.lever.co",
            },
            timeout=30,
        )

        if resp.status_code in (200, 302):
            return {"success": True, "message": "Application submitted via Lever"}
        else:
            return {"success": False, "message": f"Lever returned {resp.status_code}"}

    except Exception as e:
        return {"success": False, "message": str(e)}


def detect_ats_and_apply(job_url: str, resume_path: str) -> dict:
    """
    Detect which ATS the job uses and apply accordingly.

    Returns: {"success": bool, "message": str, "ats": str}
    """
    url_lower = job_url.lower()

    if "greenhouse.io" in url_lower or "boards.greenhouse" in url_lower:
        result = apply_greenhouse(job_url, resume_path)
        result["ats"] = "greenhouse"
        return result

    elif "lever.co" in url_lower or "jobs.lever" in url_lower:
        result = apply_lever(job_url, resume_path)
        result["ats"] = "lever"
        return result

    else:
        return {
            "success": False,
            "message": f"Unknown ATS — cannot auto-apply to {job_url}",
            "ats": "unknown",
        }
