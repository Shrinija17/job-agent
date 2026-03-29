import os
from pathlib import Path
from google import genai


class ResumeTailor:
    """Tailor a base resume for a specific job description using Gemini."""

    def __init__(self, base_resume_text: str):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .env")

        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.5-flash"
        self.base_resume = base_resume_text

    def tailor(self, job_title: str, company: str, job_description: str) -> str:
        """Return a tailored resume (plain text, same format as base)."""
        prompt = f"""You are an expert ATS resume optimizer. Your job is to tailor a resume
for a specific job posting while keeping it 100% truthful.

RULES:
1. Keep the EXACT same format — plain text with ===== section headers
2. Keep the same contact info, education, and project titles
3. Rewrite the SUMMARY to mirror the job description's language
4. Reorder and rewrite SKILLS to front-load what the job asks for
5. Rewrite bullet points in EXPERIENCE to emphasize relevant achievements
6. Use the EXACT keywords and phrases from the job description naturally
7. Keep it truthful — don't invent experience, just reframe existing work
8. Match the job's verb style (e.g., if they say "drive growth", use "drove growth")
9. Keep it to the same length — no longer than the original
10. The job title at JustPaid should be adjusted to match the role being applied for
    (e.g., if applying for "Growth Marketing Analyst", use "Growth Marketing Analyst" as the JustPaid title)

JOB POSTING:
Title: {job_title}
Company: {company}
Description:
{job_description[:4000]}

BASE RESUME:
{self.base_resume}

OUTPUT the tailored resume in the EXACT same plain text format. Nothing else — no commentary, no markdown code fences, just the resume text."""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        text = response.text.strip()

        # Clean up any accidental markdown fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3].strip()

        return text

    def quick_match_analysis(self, job_description: str) -> str:
        """Return a brief analysis of how well the resume matches the job."""
        prompt = f"""Compare this resume against this job description. Be brief (3-4 lines max).

Format:
Match: X/10
Strengths: (1-2 key matches)
Gaps: (1-2 missing skills/experiences)

JOB: {job_description[:2000]}

RESUME: {self.base_resume[:2000]}"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return response.text.strip()
