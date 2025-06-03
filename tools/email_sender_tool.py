# tools/email_sender_tool.py
from crewai.tools import BaseTool
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from utils.logger import logger

load_dotenv()


class EmailSenderTool(BaseTool):
    name: str = "Email Sender Tool"
    description: str = "Sends the job alert digest via email using SMTP."

    def _run(self, subject: str, body: str) -> str:
        logger.info("Starting email sending process...")
        
        smtp_server = os.getenv('SMTP_SERVER')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        email_user = os.getenv('EMAIL_USER')
        email_pass = os.getenv('EMAIL_PASS')
        to_email = os.getenv('EMAIL_TO')

        logger.info("Email configuration:")
        logger.info(f"SMTP_SERVER: {smtp_server}")
        logger.info(f"SMTP_PORT: {smtp_port}")
        logger.info(f"EMAIL_USER: {email_user}")
        logger.info(f"EMAIL_PASS is set: {bool(email_pass)}")
        logger.info(f"EMAIL_TO: {to_email}")

        if not all([smtp_server, smtp_port, email_user, email_pass, to_email]):
            logger.error("Missing one or more email-related environment variables")
            raise ValueError("Missing one or more email-related environment variables.")

        logger.info("Composing multipart email message...")
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = email_user
        msg['To'] = to_email

        # Create both plain text and HTML versions
        text_part = MIMEText("Please view this email in an HTML-enabled client for the best experience.", 'plain')
        html_part = MIMEText(body, 'html')

        msg.attach(text_part)
        msg.attach(html_part)

        try:
            logger.info(f"Connecting to SMTP server {smtp_server}:{smtp_port}...")
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                logger.info("Starting TLS encryption...")
                server.starttls()
                logger.info("Authenticating with SMTP server...")
                server.login(email_user, email_pass)
                logger.info(f"Sending email to {to_email}...")
                server.sendmail(email_user, [to_email], msg.as_string())
            
            success_msg = f"✅ Email sent to {to_email}"
            logger.info(f"Email sent successfully to {to_email}")
            return success_msg
            
        except Exception as e:
            error_msg = f"❌ Failed to send email: {e}"
            logger.error(f"Failed to send email: {e}")
            return error_msg