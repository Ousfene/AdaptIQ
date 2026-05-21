"""
services/email_service.py — Async SMTP email sender for OTP delivery.

When SMTP is configured (SMTP_HOST is set), sends emails via aiosmtplib.
When SMTP is not configured, falls back to logging the OTP to console.

Usage:
    from services.email_service import send_otp_email
    await send_otp_email(recipient="user@example.com", otp_code="123456")
"""

import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib

from config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_USE_TLS,
    ENVIRONMENT,
)

logger = logging.getLogger(__name__)


def is_smtp_configured() -> bool:
    """Check whether SMTP credentials are present in config."""
    return bool(SMTP_HOST and SMTP_FROM_EMAIL and SMTP_PASSWORD)


def _smtp_username() -> str | None:
    """Return the SMTP login name, preferring a full email address for providers like Gmail."""
    username = (SMTP_USERNAME or "").strip()
    from_email = (SMTP_FROM_EMAIL or "").strip()

    if username and "@" in username:
        return username

    if from_email:
        return from_email

    return username or None


def _build_otp_message(recipient: str, otp_code: str) -> MIMEMultipart:
    """Build a simple HTML+text OTP email."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"AdaptIQ — Password Reset Code: {otp_code}"
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg["To"] = recipient

    text_body = (
        f"Your AdaptIQ password reset code is: {otp_code}\n\n"
        "This code expires in 5 minutes.\n"
        "If you did not request a password reset, you can safely ignore this email."
    )

    html_body = f"""
    <div style="font-family: Georgia, serif; max-width: 480px; margin: 0 auto;
                padding: 32px; background: #FDFCF7; border: 1px solid #2D1B14;">
        <h2 style="color: #2D1B14; margin-top: 0;">Password Reset</h2>
        <p style="color: #2D1B14;">Your verification code is:</p>
        <div style="font-size: 32px; font-weight: bold; letter-spacing: 6px;
                    text-align: center; padding: 16px; background: #2D1B14;
                    color: #D4AF37; margin: 16px 0;">
            {otp_code}
        </div>
        <p style="color: #2D1B14; font-size: 14px;">
            This code expires in 5 minutes.<br>
            If you did not request a reset, ignore this email.
        </p>
        <hr style="border: none; border-top: 1px solid #D4AF37; margin: 24px 0;">
        <p style="color: #2D1B14; font-size: 12px; opacity: 0.6;">
            AdaptIQ — The Digital Scriptorium
        </p>
    </div>
    """

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg


async def send_otp_email(recipient: str, otp_code: str) -> bool:
    """Send an OTP email to the recipient.

    Returns True if sent successfully, False on failure.
    Falls back to console logging when SMTP is not configured.
    """
    # ── Fallback: no SMTP configured → log to console ──
    if not is_smtp_configured():
        if ENVIRONMENT.lower() != "production":
            logger.info("[DEV OTP] Code for %s: %s (SMTP not configured)", recipient, otp_code)
        else:
            logger.warning("SMTP not configured in production; OTP for %s cannot be delivered", recipient)
        return False

    # ── Send via SMTP ──
    msg = _build_otp_message(recipient, otp_code)

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=_smtp_username(),
            password=SMTP_PASSWORD or None,
            start_tls=SMTP_USE_TLS,
            timeout=10,
        )
        logger.info("OTP email sent to %s", recipient)
        return True
    except Exception as exc:
        logger.error("Failed to send OTP email to %s: %s", recipient, exc)
        # Never let email failure break the forgot-password flow.
        # Log the OTP as fallback so dev/staging users can still reset.
        if ENVIRONMENT.lower() != "production":
            logger.info("[SMTP FALLBACK] OTP for %s: %s", recipient, otp_code)
            if SMTP_USERNAME and "@" not in SMTP_USERNAME:
                logger.warning(
                    "SMTP_USERNAME does not look like a full email address; using SMTP_FROM_EMAIL as the login name"
                )
        return False
