import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from config import config

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
) -> bool:
    """
    Send an email via Gmail SMTP using an App Password.
    Returns True on success, False on failure.

    Setup:
      1. Enable 2FA on your Google account.
      2. Go to myaccount.google.com → Security → App Passwords.
      3. Generate a password for "Mail" and set it as GMAIL_APP_PASSWORD.
    """
    if not config.gmail_sender or not config.gmail_app_password:
        logger.error("Gmail credentials not configured.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.gmail_sender
    msg["To"] = to
    if cc:
        msg["Cc"] = cc

    msg.attach(MIMEText(body, "plain"))

    recipients = [to] + ([cc] if cc else [])

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(config.gmail_sender, config.gmail_app_password)
            server.sendmail(config.gmail_sender, recipients, msg.as_string())
        logger.info(f"Email sent to {to} | subject: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return False
