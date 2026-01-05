"""Email Service - Send notifications on learning events."""

from dataclasses import dataclass
from typing import Any

import structlog

from src.config import Config
from src.core.session import Session
from src.learning.confidence_scorer import ConfidenceMetrics

logger = structlog.get_logger()


@dataclass
class EmailPayload:
    """Email content structure."""

    to: str
    subject: str
    html_body: str


class EmailService:
    """Email notification service supporting multiple providers."""

    def __init__(self, config: Config):
        self.config = config
        self._client = None
        self._gmail_creds = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the email client based on provider."""
        if self.config.email_provider == "resend":
            try:
                import resend
                resend.api_key = self.config.email_api_key
                self._client = resend
            except ImportError:
                logger.warning("Resend not installed, email notifications disabled")
        elif self.config.email_provider == "gmail":
            self._initialize_gmail()
        elif self.config.email_provider == "sendgrid":
            logger.warning("SendGrid not yet implemented")
        else:
            logger.warning("SMTP not yet implemented")

    def _initialize_gmail(self) -> None:
        """Initialize Gmail OAuth credentials."""
        import os
        import pickle
        from pathlib import Path
        
        token_path = Path(self.config.data_dir) / "gmail_token.pickle"
        
        # Check if we have saved credentials
        if token_path.exists():
            with open(token_path, "rb") as token:
                self._gmail_creds = pickle.load(token)
        
        # If no valid credentials, we'll need to authenticate
        if not self._gmail_creds or not self._gmail_creds.valid:
            if self._gmail_creds and self._gmail_creds.expired and self._gmail_creds.refresh_token:
                from google.auth.transport.requests import Request
                self._gmail_creds.refresh(Request())
            else:
                logger.info("Gmail OAuth token not found. Run 'python -m src.main auth-gmail' to authenticate.")
                return
            
            # Save refreshed credentials
            with open(token_path, "wb") as token:
                pickle.dump(self._gmail_creds, token)
        
        logger.info("Gmail OAuth initialized successfully")

    async def send_learning_complete(
        self,
        session: Session,
        metrics: ConfidenceMetrics,
        report: str = "",
    ) -> bool:
        """Send notification when learning is complete."""
        subject = f"[BrowserBot] ✅ Learning Complete: {self._extract_domain(session.target_url)}"

        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #22c55e;">✅ Learning Complete</h1>
            
            <p><strong>Target URL:</strong> <a href="{session.target_url}">{session.target_url}</a></p>
            <p><strong>Session ID:</strong> <code>{session.session_id}</code></p>
            
            <h2>📊 Summary</h2>
            <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 8px 0;"><strong>Total Actions</strong></td>
                    <td style="padding: 8px 0; text-align: right;">{len(session.actions)}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 8px 0;"><strong>Success Rate</strong></td>
                    <td style="padding: 8px 0; text-align: right;">{metrics.success_rate:.0%}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 8px 0;"><strong>Coverage Score</strong></td>
                    <td style="padding: 8px 0; text-align: right;">{metrics.coverage_score:.0%}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 8px 0;"><strong>Final Confidence</strong></td>
                    <td style="padding: 8px 0; text-align: right;"><strong style="color: #22c55e;">{metrics.weighted_score:.0%}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;"><strong>Duration</strong></td>
                    <td style="padding: 8px 0; text-align: right;">{session.duration_seconds:.0f} seconds</td>
                </tr>
            </table>
            
            {f'<h2>🧠 Learning Report</h2><pre style="background: #f3f4f6; padding: 16px; border-radius: 8px; overflow-x: auto;">{report}</pre>' if report else ''}
            
            <hr style="margin: 24px 0; border: none; border-top: 1px solid #e5e7eb;">
            <p style="color: #6b7280; font-size: 14px;">
                This is an automated message from Browser Learning Agent.
            </p>
        </div>
        """

        return await self._send_email(EmailPayload(
            to=self.config.notification_email,
            subject=subject,
            html_body=html_body,
        ))

    async def send_error_alert(
        self,
        session: Session,
        error: str,
    ) -> bool:
        """Send notification when a critical error occurs."""
        subject = f"[BrowserBot] ❌ Error: {self._extract_domain(session.target_url)}"

        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #ef4444;">❌ Learning Error</h1>
            
            <p><strong>Target URL:</strong> <a href="{session.target_url}">{session.target_url}</a></p>
            <p><strong>Session ID:</strong> <code>{session.session_id}</code></p>
            
            <h2>Error Details</h2>
            <pre style="background: #fef2f2; color: #991b1b; padding: 16px; border-radius: 8px; overflow-x: auto;">{error}</pre>
            
            <h2>Session Status</h2>
            <p>Actions completed before error: {len(session.actions)}</p>
            
            <hr style="margin: 24px 0; border: none; border-top: 1px solid #e5e7eb;">
            <p style="color: #6b7280; font-size: 14px;">
                This is an automated message from Browser Learning Agent.
            </p>
        </div>
        """

        return await self._send_email(EmailPayload(
            to=self.config.notification_email,
            subject=subject,
            html_body=html_body,
        ))

    async def _send_email(self, payload: EmailPayload) -> bool:
        """Send email using configured provider."""
        try:
            if self.config.email_provider == "resend":
                if not self._client:
                    logger.warning("Resend client not configured")
                    return False
                result = self._client.Emails.send({
                    "from": "Browser Agent <noreply@resend.dev>",
                    "to": payload.to,
                    "subject": payload.subject,
                    "html": payload.html_body,
                })
                logger.info("Email sent successfully", email_id=result.get("id"))
                return True
            
            elif self.config.email_provider == "gmail":
                return await self._send_gmail(payload)
            
            else:
                logger.warning("Email provider not implemented", provider=self.config.email_provider)
                return False

        except Exception as e:
            logger.error("Failed to send email", error=str(e))
            return False

    async def _send_gmail(self, payload: EmailPayload) -> bool:
        """Send email via Gmail API."""
        if not self._gmail_creds:
            logger.warning("Gmail not authenticated. Run 'python -m src.main auth-gmail' first.")
            return False
        
        try:
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            import base64
            from googleapiclient.discovery import build
            
            service = build("gmail", "v1", credentials=self._gmail_creds)
            
            message = MIMEMultipart("alternative")
            message["to"] = payload.to
            message["subject"] = payload.subject
            
            html_part = MIMEText(payload.html_body, "html")
            message.attach(html_part)
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            service.users().messages().send(
                userId="me",
                body={"raw": raw}
            ).execute()
            
            logger.info("Gmail sent successfully", to=payload.to)
            return True
            
        except Exception as e:
            logger.error("Gmail send failed", error=str(e))
            return False

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc or url[:30]
