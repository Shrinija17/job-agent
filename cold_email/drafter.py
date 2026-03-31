"""Draft cold emails using a fixed template + Gemini for role alignment."""

import re


def _clean_company_name(name: str) -> str:
    """Strip legal suffixes for natural-sounding emails."""
    suffixes = [
        r",?\s*Inc\.?", r",?\s*LLC\.?", r",?\s*Ltd\.?", r",?\s*Corp\.?",
        r",?\s*L\.?P\.?", r",?\s*Co\.?", r",?\s*PLC\.?", r",?\s*Pvt\.?",
        r",?\s*Incorporated", r",?\s*Corporation", r",?\s*Limited",
    ]
    cleaned = name.strip()
    for suffix in suffixes:
        cleaned = re.sub(suffix + r"$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


EMAIL_TEMPLATE = """Hi {first_name},

2+ years as an AI growth & marketing analyst at JustPaid (YC W23) and EA Games — building automated analytics dashboards, AI-powered marketing pipelines, and data systems that drive growth with Python, SQL, BigQuery, and LLMs. M.S. in Data Analytics from Baruch College.

Would love to chat if there are any open growth, marketing analytics, or AI roles, or if you could point me to the right person on the team.

Thanks,
Shrinija Kummari
(201) 241-5870
www.linkedin.com/in/shrinija-kummari
shrinija17.github.io/portfolio"""


class EmailDrafter:
    """Draft cold emails from a fixed template. No LLM needed."""

    def draft(self, contact) -> tuple[str, str]:
        """Return (subject, body) using the fixed template."""
        company = _clean_company_name(contact.company)
        first_name = contact.hr_name.split()[0].title() if contact.hr_name else "there"

        subject = f"AI Growth & Marketing Analyst — {company}"

        body = EMAIL_TEMPLATE.format(
            first_name=first_name,
        )

        return subject, body

    def draft_followup(self, contact, original_subject: str) -> tuple[str, str]:
        """Short follow-up — no Gemini needed."""
        company = _clean_company_name(contact.company)
        first_name = contact.hr_name.split()[0] if contact.hr_name else "there"

        body = (
            f"Hi {first_name},\n\n"
            f"Just following up on my previous email. I'm still very interested "
            f"in opportunities at {company} and would love to connect "
            f"if you have a few minutes.\n\n"
            f"Thanks,\nShrinija"
        )

        return f"Re: {original_subject}", body

