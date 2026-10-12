import smtplib
from email.message import EmailMessage
from app.core.config import settings

def send_email_sync(to_email: str, subject: str, body: str):
    """
    Sends an email synchronously using SMTP.
    Should be called via BackgroundTasks or asyncio.to_thread in FastAPI.
    """
    if not settings.SMTP_HOST:
        print(f"Mock Email to {to_email} | Subject: {subject} | Body: {body}")
        return

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = to_email

    try:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        server.starttls()
        
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
