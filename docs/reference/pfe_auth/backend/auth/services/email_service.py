import logging

logger = logging.getLogger(__name__)

# Import all SMTP settings from config.py so there is one source of truth.
# Change SMTP settings in config.py (or .env) only — do not add os.getenv() here.
from config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_USE_TLS,
)


def is_smtp_configured() -> bool:
    """Check if SMTP settings are configured in environment."""
    return bool(SMTP_HOST and SMTP_USERNAME and SMTP_PASSWORD and SMTP_FROM_EMAIL)


def otp_email_template(otp_code: str, purpose_label: str) -> str:
    """Generate HTML email template for OTP codes."""
    return f"""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"></head>
    <body>
      <h2>AdaptIQ</h2>
      <p>{purpose_label}</p>
      <h3 style="letter-spacing:6px">{otp_code}</h3>
      <p>This code expires in 5 minutes. Do not share it.</p>
    </body></html>
    """


async def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Send an email asynchronously.

    ⚠️  CURRENT STATUS: Email service NOT IMPLEMENTED
    This function does not send emails. It logs them to console and returns True.
    Users cannot reset passwords since emails don't actually arrive.

    Users will see successful responses for password resets, but emails won't be sent.

    TODO: Implement email sending with one of:

    OPTION A - SMTP (Gmail, SendGrid, etc):
    1. Configure in backend/.env:
       - SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL
    2. Install: pip install aiosmtplib
    3. Use the commented example code below

    OPTION B - SendGrid API:
    1. Get API key from https://sendgrid.com
    2. Set SENDGRID_API_KEY in backend/.env
    3. Install: pip install sendgrid
    4. Send via: https://docs.sendgrid.com/for-developers/sending-email/integration-examples/send-email-with-python

    Returns:
        True if email would be sent (or logs in dev mode), False on failure.
        NOTE: Always returns True for now, even though email isn't sent.
    """
    if not is_smtp_configured():
        # DEV MODE: Log email details instead of sending
        logger.warning(
            f"[DEV MODE] SMTP not configured - email NOT sent. "
            f"To: {to_email} | Subject: {subject}"
        )
        # Log OTP code to console for development testing
        if "OTP" in subject or "code" in subject.lower():
            logger.info(f"[DEV MODE] Check server logs above for OTP code")
        return True
    
    # TODO: Implement actual SMTP sending with aiosmtplib
    # Example implementation:
    # import aiosmtplib
    # from email.message import EmailMessage
    # 
    # msg = EmailMessage()
    # msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    # msg["To"] = to_email
    # msg["Subject"] = subject
    # msg.set_content(html_body, subtype="html")
    # 
    # await aiosmtplib.send(
    #     msg,
    #     hostname=SMTP_HOST,
    #     port=SMTP_PORT,
    #     username=SMTP_USERNAME,
    #     password=SMTP_PASSWORD,
    #     start_tls=SMTP_USE_TLS,
    # )
    
    logger.info(f"[STUB] Email would be sent to {to_email}: {subject}")
    return True
