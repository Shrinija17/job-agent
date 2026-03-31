"""Send cold emails via Gmail SMTP with throttling."""

import os
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from pathlib import Path


class EmailSender:
    """Send emails via Gmail SMTP with configurable throttling."""

    def __init__(self, batch_size: int = 20, delay_seconds: int = 10):
        self.gmail_address = os.getenv("GMAIL_ADDRESS", "").strip()
        self.gmail_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
        self.batch_size = batch_size
        self.delay_seconds = delay_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.gmail_address and self.gmail_password)

    def send_batch(self, emails: list[dict], resume_path: str = None) -> list[dict]:
        """
        Send a batch of emails.

        Each email dict: {to, name, subject, body, contact_id}
        Returns: [{contact_id, status, error?}]
        """
        if not self.is_configured:
            print("\n  Gmail not configured. Set GMAIL_APP_PASSWORD in .env")
            print("  To get an app password:")
            print("    1. Go to myaccount.google.com/apppasswords")
            print("    2. Generate a password for 'Mail'")
            print("    3. Paste it in .env as GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx\n")
            return [
                {"contact_id": e["contact_id"], "status": "skipped", "error": "not configured"}
                for e in emails
            ]

        results = []
        batch = emails[: self.batch_size]

        def connect():
            s = smtplib.SMTP("smtp.gmail.com", 587)
            s.starttls()
            s.login(self.gmail_address, self.gmail_password)
            return s

        try:
            server = connect()

            for i, email in enumerate(batch):
                try:
                    msg = MIMEMultipart()
                    msg["From"] = f"Shrinija Kummari <{self.gmail_address}>"
                    msg["To"] = email["to"]
                    msg["Subject"] = email["subject"]

                    msg.attach(MIMEText(email["body"], "plain"))

                    # Attach resume PDF if provided
                    if resume_path and Path(resume_path).exists():
                        with open(resume_path, "rb") as f:
                            attachment = MIMEApplication(f.read(), _subtype="pdf")
                            attachment.add_header(
                                "Content-Disposition",
                                "attachment",
                                filename="Shrinija_Kummari_Resume.pdf",
                            )
                            msg.attach(attachment)

                    server.send_message(msg)
                    results.append({"contact_id": email["contact_id"], "status": "sent"})
                    print(f"  [{i + 1}/{len(batch)}] Sent to {email['name']} <{email['to']}>")

                    # Throttle between sends
                    if i < len(batch) - 1:
                        time.sleep(self.delay_seconds)

                except smtplib.SMTPServerDisconnected:
                    # Reconnect and retry this email
                    try:
                        server = connect()
                        server.send_message(msg)
                        results.append({"contact_id": email["contact_id"], "status": "sent"})
                        print(f"  [{i + 1}/{len(batch)}] Sent to {email['name']} <{email['to']}> (reconnected)")
                    except Exception as e2:
                        results.append(
                            {"contact_id": email["contact_id"], "status": "failed", "error": str(e2)}
                        )
                        print(f"  [{i + 1}/{len(batch)}] FAILED: {email['to']} — {e2}")

                except Exception as e:
                    results.append(
                        {"contact_id": email["contact_id"], "status": "failed", "error": str(e)}
                    )
                    print(f"  [{i + 1}/{len(batch)}] FAILED: {email['to']} — {e}")

            try:
                server.quit()
            except Exception:
                pass

        except Exception as e:
            print(f"\n  SMTP connection failed: {e}")
            for email in batch:
                if not any(r["contact_id"] == email["contact_id"] for r in results):
                    results.append(
                        {"contact_id": email["contact_id"], "status": "failed", "error": str(e)}
                    )

        return results
