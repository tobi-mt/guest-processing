# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Email functionality for Guest Database Manager."""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Optional

import streamlit as st

try:
    from .config_manager import ConfigManager
except ImportError:
    from config_manager import ConfigManager


class EmailManager:
    """Manages email sending for guest acceptance/rejection notifications."""

    def __init__(self):
        """Initialize the email manager."""
        self.smtp_server: Optional[str] = None
        self.smtp_port: Optional[int] = None
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.from_email: Optional[str] = None
        self.from_name: Optional[str] = None

        # Initialize config manager for persistent settings
        self.config_manager = ConfigManager()

        # Load saved settings if available
        self.load_saved_config()

    def configure_smtp(
        self, smtp_server: str, smtp_port: int, username: str, password: str, from_email: str, from_name: str = ""
    ) -> None:
        """Configure SMTP settings.

        Args:
            smtp_server: SMTP server hostname
            smtp_port: SMTP server port
            username: SMTP username
            password: SMTP password
            from_email: From email address
            from_name: From name (optional)
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.from_name = from_name

    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return all([self.smtp_server, self.smtp_port, self.username, self.password, self.from_email])

    def get_acceptance_template(self, guest_name: str, custom_message: str = "") -> Dict[str, str]:
        """Get the email template for guest acceptance.

        Args:
            guest_name: Name of the guest
            custom_message: Custom message to include

        Returns:
            Dictionary with subject and body
        """
        subject = "🎉 Welcome to Our Podcast - Application Accepted!"

        if custom_message:
            body = f"""Dear {guest_name},

{custom_message}

We are excited to have you as a guest on our podcast! Your application has been accepted, and we look forward to sharing your story with our audience.

Next Steps:
• Be our guest on the show: https://mirrortalkpodcast.com/be-our-next-guest/
• Kindly select a suitable time for recording
• Donation is optional but appreciated: https://mirrortalkpodcast.com/feed-the-children/

Thank you for your interest in being part of our podcast family!

Best regards,
Your Favorite Podcast"""
        else:
            body = f"""Dear {guest_name},

Congratulations! We are thrilled to inform you that your application to be a guest on our podcast has been accepted.

We were impressed by your background and story, and we believe our audience would greatly benefit from hearing your insights and experiences.

Next Steps:
• Be our guest on the show: https://mirrortalkpodcast.com/be-our-next-guest/
• Kindly select a suitable time for recording
• Donation is optional but appreciated: https://mirrortalkpodcast.com/feed-the-children/

We are excited to work with you and share your story with our community!

Warm regards,
Your Favorite Podcast"""

        return {"subject": subject, "body": body}

    def get_rejection_template(self, guest_name: str, custom_message: str = "") -> Dict[str, str]:
        """Get the email template for guest rejection.

        Args:
            guest_name: Name of the guest
            custom_message: Custom message to include

        Returns:
            Dictionary with subject and body
        """
        subject = "Thank You for Your Podcast Application"

        if custom_message:
            body = f"""Dear {guest_name},

{custom_message}

We appreciate you taking the time to apply to be a guest on our podcast.

While we won't be moving forward with your application at this time, we encourage you to continue pursuing your passions and sharing your story in other venues.

We wish you all the best in your endeavors!

Best regards,
Your Favorite Podcast"""
        else:
            body = f"""Dear {guest_name},

Thank you for your interest in being a guest on our podcast. We appreciate the time you took to complete our application and share your story with us.

After careful consideration, we have decided not to move forward with your application at this time. This decision was not easy, as we received many compelling applications from remarkable individuals.

Please know that this decision does not reflect on your worth or the value of your story. We simply have limited slots and must make difficult choices based on various factors including content fit, scheduling, and current programming needs.

We encourage you to continue sharing your story and pursuing opportunities that align with your goals and values.

Thank you again for your interest, and we wish you all the best in your future endeavors.

Warm regards,
Your Favorite Podcast"""

        return {"subject": subject, "body": body}

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send an email.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.is_configured():
            raise ValueError("Email not configured. Please configure SMTP settings first.")

        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = f"{self.from_name} <{self.from_email}>" if self.from_name else self.from_email
            msg['To'] = to_email
            msg['Subject'] = subject

            # Attach body
            msg.attach(MIMEText(body, 'plain'))

            # Create SMTP session
            context = ssl.create_default_context()

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.username, self.password)
                server.send_message(msg)

            return True

        except (smtplib.SMTPException, ssl.SSLError, OSError) as e:
            error_msg = str(e)

            # Provide specific guidance for common Gmail errors
            if "Application-specific password required" in error_msg or "InvalidSecondFactor" in error_msg:
                st.error("🔒 **Gmail App Password Required**")
                st.error("Your Gmail account requires an App Password instead of your regular password.")
                st.info("**How to fix this:**")
                st.info("1. Enable 2-Factor Authentication on your Google Account")
                st.info("2. Go to Google Account → Security → App passwords")
                st.info("3. Generate an App Password for 'Mail'")
                st.info("4. Use that 16-character password instead of your regular password")
                st.info("5. Learn more: https://support.google.com/mail/?p=InvalidSecondFactor")
            elif "authentication failed" in error_msg.lower():
                st.error("❌ **Authentication Failed**")
                st.error("Please check your username and password are correct.")
                if "gmail" in self.smtp_server.lower():
                    st.info("💡 For Gmail: Make sure you're using an App Password, not your regular password")
            else:
                st.error(f"❌ **Failed to send email:** {error_msg}")

            return False

    def send_acceptance_email(self, guest_name: str, to_email: str, custom_message: str = "") -> bool:
        """Send acceptance email to a guest.

        Args:
            guest_name: Name of the guest
            to_email: Guest's email address
            custom_message: Custom message to include

        Returns:
            True if email sent successfully, False otherwise
        """
        template = self.get_acceptance_template(guest_name, custom_message)
        return self.send_email(to_email, template["subject"], template["body"])

    def send_rejection_email(self, guest_name: str, to_email: str, custom_message: str = "") -> bool:
        """Send rejection email to a guest.

        Args:
            guest_name: Name of the guest
            to_email: Guest's email address
            custom_message: Custom message to include

        Returns:
            True if email sent successfully, False otherwise
        """
        template = self.get_rejection_template(guest_name, custom_message)
        return self.send_email(to_email, template["subject"], template["body"])

    def load_saved_config(self) -> bool:
        """Load saved email configuration.

        Returns:
            True if configuration was loaded, False otherwise
        """
        config = self.config_manager.load_email_config()
        if config:
            self.smtp_server = config.get("smtp_server")
            self.smtp_port = config.get("smtp_port")
            self.username = config.get("username")
            self.password = config.get("password")
            self.from_email = config.get("from_email")
            self.from_name = config.get("from_name")
            return True
        return False

    def save_config(self, provider: str = "Gmail") -> bool:
        """Save current email configuration.

        Args:
            provider: Email provider name

        Returns:
            True if saved successfully, False otherwise
        """
        if not self.is_configured():
            return False

        return self.config_manager.save_email_config(
            smtp_server=self.smtp_server,
            smtp_port=self.smtp_port,
            username=self.username,
            password=self.password,
            from_email=self.from_email,
            from_name=self.from_name,
            provider=provider,
        )

    def clear_saved_config(self) -> bool:
        """Clear saved email configuration.

        Returns:
            True if cleared successfully, False otherwise
        """
        return self.config_manager.clear_email_config()

    def has_saved_config(self) -> bool:
        """Check if saved email configuration exists.

        Returns:
            True if configuration exists, False otherwise
        """
        return self.config_manager.has_email_config()

    def get_saved_provider(self) -> Optional[str]:
        """Get the saved email provider.

        Returns:
            Provider name or None if not saved
        """
        config = self.config_manager.load_email_config()
        return config.get("provider") if config else None


def get_common_smtp_configs() -> Dict[str, Dict[str, any]]:
    """Get common SMTP configurations for popular email providers.

    Returns:
        Dictionary of provider configurations
    """
    return {
        "Gmail": {
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "note": "⚠️ IMPORTANT: Use App Password, not regular password. Enable 2FA first, then generate App Password in Google Account → Security → App passwords",
        },
        "Outlook/Hotmail": {
            "smtp_server": "smtp-mail.outlook.com",
            "smtp_port": 587,
            "note": "Regular password or App Password",
        },
        "Yahoo": {"smtp_server": "smtp.mail.yahoo.com", "smtp_port": 587, "note": "Use App Password"},
        "Custom": {"smtp_server": "", "smtp_port": 587, "note": "Enter your custom SMTP settings"},
    }
