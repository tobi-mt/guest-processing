# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Email functionality for Guest Database Manager."""

import base64
import html
import json
import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Mapping, Optional, Sequence, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from .intake_receipt_pdf import build_intake_receipt_pdf

try:
    import streamlit as st
    from streamlit.runtime.scriptrunner import get_script_run_ctx
except ImportError:  # pragma: no cover - streamlit is available in app env, but keep backend-safe fallback
    st = None

    def get_script_run_ctx() -> None:
        return None

try:
    from .config_manager import ConfigManager
except ImportError as exc:
    if "attempted relative import" not in str(exc):
        raise
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
        self.cc_email: Optional[str] = None
        self.resend_api_key: Optional[str] = None
        self.last_error: str = ""

        # Initialize config manager for persistent settings
        self.config_manager = ConfigManager()

        # Load saved settings if available
        self.load_saved_config()

    def configure_smtp(
        self,
        smtp_server: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        from_name: str = "",
        cc_email: str = "",
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
        self.cc_email = cc_email or None
        self.resend_api_key = None

    def configure_resend(self, api_key: str, from_email: str, from_name: str = "", cc_email: str = "") -> None:
        """Configure Resend API delivery."""
        self.resend_api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self.cc_email = cc_email or None
        self.smtp_server = None
        self.smtp_port = None
        self.username = None
        self.password = None

    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        resend_ready = all([self.resend_api_key, self.from_email])
        smtp_ready = all([self.smtp_server, self.smtp_port, self.username, self.password, self.from_email])
        return resend_ready or smtp_ready

    def _can_report_with_streamlit(self) -> bool:
        """Return whether streamlit UI feedback is safe in this execution context."""
        return st is not None and get_script_run_ctx() is not None

    def _report_send_failure(self, error_msg: str) -> None:
        """Optionally mirror email failures into the Streamlit UI when one exists."""
        if not self._can_report_with_streamlit():
            return

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
            if self.smtp_server and "gmail" in self.smtp_server.lower():
                st.info("💡 For Gmail: Make sure you're using an App Password, not your regular password")
        else:
            st.error(f"❌ **Failed to send email:** {error_msg}")

    EMAIL_TEMPLATE_VARIANTS = {
        "accepted": (("warm", "Warm and welcoming"), ("concise", "Warm and concise")),
        "rejected": (("considered", "Considered and compassionate"), ("concise", "Kind and concise")),
        "reminder": (("gentle", "Gentle confirmation"), ("concise", "Clear and concise")),
        "booking_confirmation": (("warm", "Warm and welcoming"), ("concise", "Clear and concise")),
        "cancellation": (("thoughtful", "Thoughtful and accountable"), ("concise", "Direct and considerate")),
        "appreciation": (("reflective", "Reflective and grateful"), ("concise", "Warm and concise")),
        "intake_confirmation": (("reassuring", "Reassuring and clear"), ("concise", "Clear and concise")),
        "application_request": (("personal", "Personal invitation"), ("concise", "Clear and concise")),
        "booking_link": (("helpful", "Helpful and reassuring"), ("concise", "Clear and concise")),
        "reschedule": (("supportive", "Supportive and flexible"), ("concise", "Clear and concise")),
        "released_episode": (("celebratory", "Celebratory and collaborative"), ("concise", "Share-ready and concise")),
    }

    @classmethod
    def template_variants(cls, email_type: str) -> list[Dict[str, str]]:
        """Return the operator-visible, reviewed variants for an email type."""
        return [{"id": variant_id, "label": label} for variant_id, label in cls.EMAIL_TEMPLATE_VARIANTS.get(email_type, ())]

    @classmethod
    def _template_variant(cls, email_type: str, variant: str, default: str) -> str:
        """Validate a stable template variant; never silently choose a random one."""
        selected = (variant or default).strip().lower()
        allowed = {item[0] for item in cls.EMAIL_TEMPLATE_VARIANTS.get(email_type, ())}
        if selected not in allowed:
            raise ValueError(f"Unknown {email_type} email template variant.")
        return selected

    @staticmethod
    def _safe_personalization_text(value: Any, *, limit: int = 100) -> str:
        """Return short, single-line copy suitable for reviewed guest email templates."""
        text = " ".join(str(value or "").split()).strip(" -–—.,")
        if not text or "http://" in text.lower() or "https://" in text.lower():
            return ""
        return text[:limit].rstrip()

    @classmethod
    def build_personalization_context(cls, guest: Mapping[str, Any]) -> Dict[str, str]:
        """Derive conservative email context without exposing raw research or inventing claims."""
        research = guest.get("guest_research") or {}
        if isinstance(research, str):
            try:
                research = json.loads(research)
            except (TypeError, ValueError):
                research = {}
        if not isinstance(research, Mapping) or research.get("cache_status") == "failed":
            research = {}
        topics = research.get("likely_topics") or []
        if not isinstance(topics, list):
            topics = []
        topic = next((cls._safe_personalization_text(item, limit=72) for item in topics if cls._safe_personalization_text(item, limit=72)), "")
        if not topic:
            topic = cls._safe_personalization_text(
                guest.get("topic") or guest.get("proposed_topic") or guest.get("category"), limit=72
            )
        role = cls._safe_personalization_text(
            guest.get("job_title") or guest.get("profession") or guest.get("role"), limit=72
        )
        organisation = cls._safe_personalization_text(
            guest.get("company") or guest.get("organization") or guest.get("organisation"), limit=72
        )
        return {key: value for key, value in {"topic": topic, "role": role, "organisation": organisation}.items() if value}

    @classmethod
    def _personalized_topic_line(cls, personalization: Optional[Mapping[str, Any]], *, purpose: str) -> str:
        topic = cls._safe_personalization_text((personalization or {}).get("topic"), limit=72)
        if not topic:
            return ""
        if purpose == "invitation":
            return f"Your perspective on {topic} feels especially relevant to the thoughtful conversations we create.\n\n"
        if purpose == "preparation":
            return f"We’re especially looking forward to exploring {topic} with you; there is nothing scripted to prepare.\n\n"
        if purpose == "thanks":
            return f"Your perspective on {topic} brought something distinctive and valuable to the conversation.\n\n"
        if purpose == "release":
            return f"I’m delighted that our conversation around {topic} can now reach the Mirror Talk community.\n\n"
        return ""

    def get_acceptance_template(self, guest_name: str, custom_message: str = "", booking_url: str = "", variant: str = "warm", personalization: Optional[Mapping[str, Any]] = None) -> Dict[str, str]:
        """Get the email template for guest acceptance.

        Args:
            guest_name: Name of the guest
            custom_message: Custom message to include

        Returns:
            Dictionary with subject and body
        """
        variant = self._template_variant("accepted", variant, "warm")
        subject = "Your Mirror Talk Podcast application has been accepted" if variant == "warm" else "You’re invited to join Mirror Talk Podcast"
        booking_line = booking_url or "https://mirrortalkpodcast.com/be-our-next-guest/"
        personal_line = self._personalized_topic_line(personalization, purpose="invitation")

        if variant == "concise":
            body = f"""Hi {guest_name},

{custom_message + chr(10) + chr(10) if custom_message else ""}{personal_line}Thank you for sharing your story with Mirror Talk. We’d be delighted to welcome you as a guest.

Please choose a recording time that works for you:
{booking_line}

Once you’re booked, we’ll send everything you need to prepare. We’re looking forward to our conversation.

Warmly,
Mirror Talk Podcast"""
        elif custom_message:
            body = f"""Hi {guest_name},

{custom_message}

{personal_line.rstrip()}

We are delighted to let you know that your application to join Mirror Talk Podcast has been accepted.

Your story, perspective, and voice feel like a strong fit for the kind of soulful conversation we want to create for our listeners, and we would love to welcome you onto the show.

Next steps:
- Please choose a suitable time for recording here: {booking_line}
- If helpful, you can also learn more about the podcast and our wider work on the site.

Thank you again for taking the time to share your story with us. We are looking forward to the conversation ahead.

Warmly,
Mirror Talk Podcast"""
        else:
            body = f"""Hi {guest_name},

We are delighted to let you know that your application to join Mirror Talk Podcast has been accepted.

{personal_line}We were moved by what you shared, and we believe your voice and lived experience would make for a meaningful conversation with our audience.

Next steps:
- Please choose a suitable time for recording here: {booking_line}
- Once your booking is in place, we will take it from there and prepare for the conversation with you.

Thank you for trusting us with your story. We are genuinely looking forward to having you as a guest on Mirror Talk.

Warmly,
Mirror Talk Podcast"""

        return {"subject": subject, "body": body}

    def get_rejection_template(self, guest_name: str, custom_message: str = "", variant: str = "considered") -> Dict[str, str]:
        """Get the email template for guest rejection.

        Args:
            guest_name: Name of the guest
            custom_message: Custom message to include

        Returns:
            Dictionary with subject and body
        """
        variant = self._template_variant("rejected", variant, "considered")
        subject = "Thank you for your Mirror Talk Podcast application"

        if variant == "concise":
            body = f"""Hi {guest_name},

{custom_message + chr(10) + chr(10) if custom_message else ""}Thank you for taking the time to apply to Mirror Talk and share your story.

After careful consideration, we will not be moving forward with your application at this time. This decision reflects our current programme needs and timing, not the value of your work or voice.

We appreciate your interest and wish you every success.

Warmly,
Mirror Talk Podcast"""
        elif custom_message:
            body = f"""Hi {guest_name},

{custom_message}

Thank you for taking the time to apply to be a guest on Mirror Talk Podcast and for sharing your story with us.

After careful review, we will not be moving forward with your application at this time.

Please know this decision is not a judgment on your value or the importance of your work. We receive many thoughtful submissions, and sometimes the decision simply comes down to fit, timing, and the direction of upcoming conversations.

We sincerely appreciate your interest in Mirror Talk, and we wish you the very best in all that lies ahead.

Warmly,
Mirror Talk Podcast"""
        else:
            body = f"""Hi {guest_name},

Thank you for your interest in being a guest on Mirror Talk Podcast and for taking the time to complete the application so thoughtfully.

After careful consideration, we will not be moving forward with your application at this time.

This kind of decision is never a simple one. We receive many strong submissions, and our final choices often come down to fit, timing, and the shape of the conversations we are planning for the season ahead.

Please know this does not diminish the value of your story, your work, or your voice. We are grateful that you shared them with us.

Thank you again for considering Mirror Talk, and we wish you every success in the journey ahead.

Warmly,
Mirror Talk Podcast"""

        return {"subject": subject, "body": body}

    def get_interview_reminder_template(
        self,
        guest_name: str,
        scheduled_for: datetime,
        timezone_label: str,
        join_url: str, variant: str = "gentle", personalization: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, str]:
        """Build the weekly confirmation reminder template for an upcoming interview."""
        variant = self._template_variant("reminder", variant, "gentle")
        localized = self._localize_datetime(scheduled_for, timezone_label)
        subject = f"Please confirm our Soulful Conversation on {localized.strftime('%A %d %B')}"
        formatted_date = localized.strftime("%A %d %B, %Y")
        formatted_time = localized.strftime("%H:%M")
        timezone_display = f"{timezone_label} (your local time)"
        join_line = join_url or "https://riverside.fm/studio/soulful-conversations?t=db1988c6212f0c5f39db"
        preparation_line = self._personalized_topic_line(personalization, purpose="preparation")

        body = f"""Hi {guest_name},

I hope you are doing well.

I’m writing to gently confirm our upcoming Soulful Conversation on Mirror Talk, scheduled for {formatted_date} at {formatted_time} {timezone_display}.

When you have a moment, please reply to this email to confirm that the time still works for you.

We’ll be recording on Riverside FM, and you can join the session here:
{join_line}

{preparation_line}I’m really looking forward to the conversation.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast

If you’d like to stay connected with the show, you can find Mirror Talk here:
https://mirrortalkpodcast.com/join-our-family/

Ask Mirror Talk:
https://mirrortalkpodcast.com/ask-mirror-talk/
"""
        if variant == "concise":
            body = f"""Hi {guest_name},

Please confirm that our Mirror Talk conversation on {formatted_date} at {formatted_time} {timezone_display} still works for you.

Join us on Riverside FM:
{join_line}

{preparation_line}If you need to change the time, simply reply to this email.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""

        return {"subject": subject, "body": body}

    def get_interview_cancellation_template(
        self,
        guest_name: str,
        scheduled_for: datetime,
        timezone_label: str,
        variant: str = "thoughtful",
    ) -> Dict[str, str]:
        """Build a thoughtful cancellation email for an interview that will not go ahead as planned."""
        variant = self._template_variant("cancellation", variant, "thoughtful")
        localized = self._localize_datetime(scheduled_for, timezone_label)
        subject = f"An update about our Soulful Conversation on {localized.strftime('%A %d %B')}"
        formatted_date = localized.strftime("%A %d %B, %Y")
        formatted_time = localized.strftime("%H:%M")
        timezone_display = f"{timezone_label} (your local time)"

        body = f"""Hi {guest_name},

I wanted to reach out personally with an update about our Soulful Conversation on Mirror Talk, originally scheduled for {formatted_date} at {formatted_time} {timezone_display}.

Unfortunately, we need to cancel this booking on our side.

I’m sorry for the inconvenience, and I truly appreciate your time and willingness to join the podcast.

If you would still be open to the conversation at a later date, please feel free to reply to this email and we’ll gladly find a new time together.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""

        if variant == "concise":
            body = f"""Hi {guest_name},

We need to cancel our Mirror Talk conversation scheduled for {formatted_date} at {formatted_time} {timezone_display}. I’m sorry for the inconvenience.

If you would like to find another time, please reply and we’ll gladly help.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""

        return {"subject": subject, "body": body}

    def get_booking_confirmation_template(
        self,
        guest_name: str,
        scheduled_for: datetime,
        timezone_label: str,
        join_url: str, variant: str = "warm", personalization: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, str]:
        """Build the initial booking confirmation email for a newly scheduled interview."""
        variant = self._template_variant("booking_confirmation", variant, "warm")
        localized = self._localize_datetime(scheduled_for, timezone_label)
        subject = f"Your Soulful Conversation is booked for {localized.strftime('%A %d %B')}"
        formatted_date = localized.strftime("%A %d %B, %Y")
        formatted_time = localized.strftime("%H:%M")
        timezone_display = f"{timezone_label} (your local time)"
        join_line = join_url or "https://riverside.fm/studio/soulful-conversations?t=db1988c6212f0c5f39db"
        preparation_line = self._personalized_topic_line(personalization, purpose="preparation")

        body = f"""Hi {guest_name},

Thank you for booking your Soulful Conversation on Mirror Talk.

Your interview is now scheduled for {formatted_date} at {formatted_time} {timezone_display}.

We’ll be recording on Riverside FM, and you can join the session here:
{join_line}

{preparation_line}If anything changes and you need to reschedule, just reply to this email and we’ll sort it out together.

Looking forward to the conversation.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""
        if variant == "concise":
            body = f"""Hi {guest_name},

Your Soulful Conversation is confirmed for {formatted_date} at {formatted_time} {timezone_display}.

Join the Riverside FM session here:
{join_line}

{preparation_line}We’ve also attached a calendar invitation. If you need to reschedule, please reply to this email.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""

        return {"subject": subject, "body": body}

    def get_reschedule_link_template(
        self,
        guest_name: str,
        scheduled_for: datetime,
        timezone_label: str,
        reschedule_url: str,
        proposed_times: Optional[list[datetime]] = None,
        proposal_mode: str = "open_calendar",
        variant: str = "supportive",
    ) -> Dict[str, str]:
        """Build the email that invites a guest to choose a new interview time."""
        variant = self._template_variant("reschedule", variant, "supportive")
        localized = self._localize_datetime(scheduled_for, timezone_label)
        subject = "Choose a new time for your Soulful Conversation"
        formatted_date = localized.strftime("%A %d %B, %Y")
        formatted_time = localized.strftime("%H:%M")
        timezone_display = f"{timezone_label} (your local time)"

        proposal_copy = ""
        localized_options = [self._localize_datetime(value, timezone_label) for value in (proposed_times or [])]
        if proposal_mode == "specific" and localized_options:
            proposed = localized_options[0]
            proposal_copy = (
                "\nWe would like to propose this new time:\n"
                f"- {proposed.strftime('%A %d %B, %Y')} at {proposed.strftime('%H:%M')} {timezone_display}\n"
            )
        elif proposal_mode == "alternatives" and localized_options:
            lines = "\n".join(
                f"- {value.strftime('%A %d %B, %Y')} at {value.strftime('%H:%M')} {timezone_display}"
                for value in localized_options
            )
            proposal_copy = f"\nWe would like to offer these alternative times:\n{lines}\n"

        body = f"""Hi {guest_name},

Thank you again for your willingness to join Mirror Talk.

Your previous Soulful Conversation slot on {formatted_date} at {formatted_time} {timezone_display} is no longer active.

You are not currently booked for a new interview time yet.
{proposal_copy}
Proposed times remain subject to availability until you confirm a new booking.

You can confirm an offered time if it is still available, or choose another time, using your personal rescheduling link here:
{reschedule_url}

If the available options still do not work for you, just reply to this email and we’ll gladly find a better time together.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""

        if variant == "concise":
            body = f"""Hi {guest_name},

Your previous Mirror Talk slot on {formatted_date} at {formatted_time} {timezone_display} is no longer active.
{proposal_copy}
Choose and confirm a new available time here:
{reschedule_url}

If none of the options work, please reply and we’ll help.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""

        return {"subject": subject, "body": body}

    @staticmethod
    def _localize_datetime(value: datetime, timezone_label: str) -> datetime:
        """Return a datetime rendered in the guest-facing timezone when possible."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        normalized_timezone = (timezone_label or "").strip()
        if not normalized_timezone:
            return value
        try:
            return value.astimezone(ZoneInfo(normalized_timezone))
        except ZoneInfoNotFoundError:
            return value

    def get_post_interview_appreciation_template(self, guest_name: str, variant: str = "reflective", personalization: Optional[Mapping[str, Any]] = None) -> Dict[str, str]:
        """Build a refined thank-you email for guests after recording."""
        variant = self._template_variant("appreciation", variant, "reflective")
        subject = "Thank you for your Soulful Conversation"
        thanks_line = self._personalized_topic_line(personalization, purpose="thanks")

        body = f"""Hi {guest_name},

Thank you again for joining me on Mirror Talk.

It was a real pleasure to share that conversation with you. I’m genuinely grateful for your openness, your time, and the perspective you brought to the episode.

{thanks_line.rstrip()}

Conversations like this are at the heart of what we hope to create with Mirror Talk, and I truly appreciate the care you brought into it.

If you’d like to support the podcast in a simple but meaningful way, here are three lovely ways to do that:
- subscribe to Mirror Talk on Spotify:
  https://open.spotify.com/show/0trwqguYCic32smqh3Ny60
- subscribe to Mirror Talk on Apple Podcasts:
  https://podcasts.apple.com/podcast/mirror-talk/id1518394292
- share the show or your episode with someone who would genuinely enjoy it
- explore our new AI experience, Ask Mirror Talk: https://mirrortalkpodcast.com/ask-mirror-talk/

You can also stay connected with the wider Mirror Talk community here:
https://mirrortalkpodcast.com/join-our-family/

Thank you once again. I’m really glad we had this conversation.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast
"""

        if variant == "concise":
            body = f"""Hi {guest_name},

Thank you for joining me on Mirror Talk. {thanks_line}I’m grateful for the care and perspective you brought to our conversation.

We’ll be in touch as the episode moves toward release.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""

        return {"subject": subject, "body": body}

    def get_intake_confirmation_template(self, guest_name: str, variant: str = "reassuring") -> Dict[str, str]:
        """Build a polished confirmation email after a guest submits the intake form."""
        variant = self._template_variant("intake_confirmation", variant, "reassuring")
        subject = "We received your Mirror Talk guest application"

        body = f"""Hi {guest_name},

Thank you for taking the time to apply to be a guest on Mirror Talk.

We’ve received your application successfully and will review it with care. If your story feels like a strong fit for an upcoming soulful conversation, we will reach out by email with the next steps.

For your records, we have attached a PDF copy of the answers you shared.

In the meantime, you are warmly invited to stay connected with Mirror Talk here:
- Website: https://mirrortalkpodcast.com/
- Podcast platforms and social links: https://lnkfi.re/mirrortalk
- Ask Mirror Talk: https://mirrortalkpodcast.com/ask-mirror-talk/

Thank you again for sharing your story with us.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast
"""

        if variant == "concise":
            body = f"""Hi {guest_name},

We’ve received your Mirror Talk guest application. A PDF copy of your answers is attached for your records.

We’ll review your submission carefully and email you if it is a fit for an upcoming conversation.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""

        return {"subject": subject, "body": body}

    def get_personal_application_request_template(
        self,
        guest_name: str,
        intake_url: str,
        agency_name: str = "",
        variant: str = "personal",
    ) -> Dict[str, str]:
        """Build the email that invites a guest to complete their own personal intake."""
        variant = self._template_variant("application_request", variant, "personal")
        subject = "Please complete your personal Mirror Talk guest application"
        intro_line = (
            f"{agency_name} shared your details with us and thought you could be a meaningful fit for Mirror Talk."
            if agency_name
            else "Your details were shared with us as someone who could be a meaningful fit for Mirror Talk."
        )
        body = f"""Hi {guest_name},

{intro_line}

To keep Mirror Talk personal and intentional, we ask each guest to complete their own application in their own voice.

Please use your personal application link here:
{intake_url}

The form is short, thoughtful, and designed to help us understand your story directly from you.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast
"""
        if variant == "concise":
            body = f"""Hi {guest_name},

Please complete your personal Mirror Talk guest application in your own voice:
{intake_url}

This helps us understand your story directly from you.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""
        return {"subject": subject, "body": body}

    def get_booking_link_template(self, guest_name: str, booking_url: str, variant: str = "helpful") -> Dict[str, str]:
        """Build a polished email for resending a guest's personal booking link."""
        variant = self._template_variant("booking_link", variant, "helpful")
        subject = "Your personal Mirror Talk booking link"
        body = f"""Hi {guest_name},

I’m glad to share your personal Mirror Talk booking link again.

You can use it here to choose a time that suits you best:
{booking_url}

If we have already arranged a custom availability window for you, this link will reflect that automatically.

If anything feels off or you need a different option, just reply to this email and we’ll gladly help.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast
"""
        if variant == "concise":
            body = f"""Hi {guest_name},

Choose your Mirror Talk recording time using your personal link:
{booking_url}

If you need help, reply to this email.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""
        return {"subject": subject, "body": body}

    def get_released_episode_template(self, guest_name: str, show_notes_url: str, files_url: str, variant: str = "celebratory", personalization: Optional[Mapping[str, Any]] = None) -> Dict[str, str]:
        """Build a polished release-notification email for a guest."""
        variant = self._template_variant("released_episode", variant, "celebratory")
        subject = "Your Mirror Talk episode is now live"
        release_line = self._personalized_topic_line(personalization, purpose="release")

        body = f"""Hi {guest_name},

I hope you are doing well.

I’m happy to let you know that your Mirror Talk episode is now live, and I want to thank you again for being part of it.

{release_line.rstrip()}

Here are the links for you:
- Show notes: {show_notes_url}
- Files (download link expires in 2 days): {files_url}

When you have a moment, I’d genuinely love to hear what you and your loved ones think of the episode.

If you’d like to support the conversation further, here are three meaningful ways to help:
- subscribe to Mirror Talk on Spotify:
  https://open.spotify.com/show/0trwqguYCic32smqh3Ny60
- subscribe to Mirror Talk on Apple Podcasts:
  https://podcasts.apple.com/podcast/mirror-talk/id1518394292
- subscribe on YouTube:
  https://www.youtube.com/@mirrortalkpodcast
- share the episode with people who would truly appreciate it
- try Ask Mirror Talk: https://mirrortalkpodcast.com/ask-mirror-talk/

You can also stay connected here:
https://lnkfi.re/mirrortalk

Thank you again for your presence, your voice, and your contribution to Mirror Talk.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast
"""

        if variant == "concise":
            body = f"""Hi {guest_name},

Your Mirror Talk episode is now live. {release_line}Thank you again for sharing the conversation with us.

- Show notes: {show_notes_url}
- Files (download link expires in 2 days): {files_url}

If it feels right, we’d love you to share the episode with your community.

Warm regards,
Tobi Ojekunle
Mirror Talk Podcast"""

        return {"subject": subject, "body": body}

    @staticmethod
    def build_calendar_invite(
        *,
        guest_name: str,
        scheduled_for: datetime,
        timezone_label: str,
        join_url: str,
        duration_minutes: int = 60,
    ) -> bytes:
        """Build a simple ICS calendar invite for booking confirmations."""
        if scheduled_for.tzinfo is None:
            scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)
        start_utc = scheduled_for.astimezone(timezone.utc)
        end_utc = start_utc + timedelta(minutes=duration_minutes)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        uid = f"mirror-talk-{int(start_utc.timestamp())}@mirrortalkpodcast.com"
        summary = f"Soulful Conversation with {guest_name}"
        description = "\\n".join(
            part
            for part in [
                f"Your Soulful Conversation with {guest_name}.",
                f"Timezone: {timezone_label}" if timezone_label else "",
                f"Join link: {join_url}" if join_url else "",
            ]
            if part
        )
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Mirror Talk Podcast//Guest Booking//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:REQUEST",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{timestamp}",
            f"DTSTART:{start_utc.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{end_utc.strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            f"LOCATION:{join_url or 'Mirror Talk Riverside Studio'}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        return "\r\n".join(lines).encode("utf-8")

    def _resend_from_address(self) -> str:
        """Format the Resend sender address."""
        if self.from_name:
            return f"{self.from_name} <{self.from_email}>"
        return self.from_email or ""

    def _build_html_body(self, body: str) -> str:
        """Render safe, responsive Mirror Talk HTML while preserving the plain-text alternative."""
        paragraphs = [segment.strip() for segment in body.split("\n\n") if segment.strip()]
        if not paragraphs:
            return "<p></p>"

        rendered = []
        for paragraph in paragraphs:
            escaped = html.escape(paragraph).replace("\n", "<br />")
            escaped = re.sub(
                r"(https://[^\s<]+)",
                r'<a href="\1" style="color:#d94b12;font-weight:700;overflow-wrap:anywhere">\1</a>',
                escaped,
            )
            rendered.append(f'<p style="margin:0 0 18px;line-height:1.65">{escaped}</p>')
        content = "".join(rendered)
        return (
            '<!doctype html><html><body style="margin:0;background:#f4efe9;color:#241b18;'
            'font-family:Arial,sans-serif"><div style="display:none;max-height:0;overflow:hidden">'
            'A message from Mirror Talk Podcast</div><table role="presentation" width="100%" '
            'cellspacing="0" cellpadding="0" style="background:#f4efe9"><tr><td align="center" '
            'style="padding:24px 12px"><table role="presentation" width="100%" cellspacing="0" '
            'cellpadding="0" style="max-width:640px;background:#fffaf3;border:1px solid #e1d6cb;'
            'border-radius:20px;overflow:hidden"><tr><td style="background:#151219;padding:24px 30px;'
            'border-top:4px solid #ff6422;color:#fff8ef"><strong style="font-family:Georgia,serif;'
            'font-size:24px">Mirror Talk</strong><br><span style="color:#ff9a6b;font-size:12px;'
            'letter-spacing:2px;text-transform:uppercase">Soulful Conversations</span></td></tr>'
            f'<tr><td style="padding:30px;font-size:16px">{content}</td></tr>'
            '<tr><td style="padding:18px 30px;background:#211a22;color:#c9bbb0;font-size:12px;'
            'line-height:1.5">Mirror Talk Podcast · Thoughtful conversations, shared with care.</td>'
            '</tr></table></td></tr></table></body></html>'
        )

    def _send_via_resend(
        self,
        to_email: Union[str, Sequence[str]],
        subject: str,
        body: str,
        attachments: Optional[Sequence[Dict[str, object]]] = None,
        idempotency_key: str = "",
    ) -> bool:
        """Send an email through the Resend HTTPS API."""
        if not self.resend_api_key or not self.from_email:
            self.last_error = "Resend is not configured."
            return False

        recipients = self._normalize_recipients(to_email)
        payload = {
            "from": self._resend_from_address(),
            "to": recipients,
            "subject": subject,
            "text": body,
            "html": self._build_html_body(body),
        }
        if self.cc_email:
            payload["cc"] = [self.cc_email]
        if attachments:
            payload["attachments"] = [
                {
                    "filename": str(item["filename"]),
                    "content": base64.b64encode(bytes(item["content"])).decode("ascii"),
                }
                for item in attachments
            ]

        try:
            headers = {
                "Authorization": f"Bearer {self.resend_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "guest-database-manager/0.1.0",
            }
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key[:256]
            response = requests.post(
                "https://api.resend.com/emails",
                headers=headers,
                json=payload,
                timeout=20,
            )
        except requests.RequestException as exc:
            self.last_error = str(exc)
            return False

        if response.ok:
            self.last_error = ""
            return True

        error_message = ""
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = {}

        if isinstance(error_payload, dict):
            error_message = (
                error_payload.get("message")
                or error_payload.get("error")
                or error_payload.get("name")
                or ""
            )
            if isinstance(error_message, dict):
                error_message = error_message.get("message", "")

        self.last_error = error_message or response.text.strip() or f"Resend returned HTTP {response.status_code}"
        return False

    def send_email(
        self,
        to_email: Union[str, Sequence[str]],
        subject: str,
        body: str,
        attachments: Optional[Sequence[Dict[str, object]]] = None,
        idempotency_key: str = "",
    ) -> bool:
        """Send an email.

        Args:
            to_email: Recipient email address or a sequence of recipient addresses
            subject: Email subject
            body: Email body

        Returns:
            True if email sent successfully, False otherwise
        """
        self.last_error = ""

        if not self.is_configured():
            self.last_error = "Email not configured. Please configure SMTP settings first."
            raise ValueError(self.last_error)

        if self.resend_api_key:
            sent = self._send_via_resend(
                to_email,
                subject,
                body,
                attachments=attachments,
                idempotency_key=idempotency_key,
            )
            if not sent:
                self._report_send_failure(self.last_error)
            return sent

        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = f"{self.from_name} <{self.from_email}>" if self.from_name else self.from_email
            recipients = self._normalize_recipients(to_email)
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject
            if idempotency_key:
                # Resend's SMTP gateway honors this header. Other SMTP servers
                # preserve it for traceability even when they cannot deduplicate.
                msg['Resend-Idempotency-Key'] = idempotency_key[:256]
            if self.cc_email:
                msg['Cc'] = self.cc_email

            # Attach body
            msg.attach(MIMEText(body, 'plain'))
            for attachment in attachments or []:
                part = MIMEApplication(bytes(attachment["content"]), Name=str(attachment["filename"]))
                part["Content-Disposition"] = f'attachment; filename="{attachment["filename"]}"'
                msg.attach(part)

            # Create SMTP session
            context = ssl.create_default_context()

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.username, self.password)
                envelope_recipients = list(recipients)
                if self.cc_email:
                    envelope_recipients.append(self.cc_email)
                server.send_message(msg, to_addrs=envelope_recipients)

            return True

        except (smtplib.SMTPException, ssl.SSLError, OSError) as e:
            error_msg = str(e)
            self.last_error = error_msg
            self._report_send_failure(error_msg)
            return False

    @staticmethod
    def _normalize_recipients(to_email: Union[str, Sequence[str]]) -> list[str]:
        """Return a non-empty, ordered, case-insensitively deduplicated recipient list."""
        raw_recipients = [to_email] if isinstance(to_email, str) else list(to_email)
        recipients: list[str] = []
        seen: set[str] = set()
        for value in raw_recipients:
            recipient = str(value).strip()
            normalized = recipient.casefold()
            if recipient and normalized not in seen:
                recipients.append(recipient)
                seen.add(normalized)
        if not recipients:
            raise ValueError("At least one recipient email address is required.")
        return recipients

    def send_acceptance_email(self, guest_name: str, to_email: str, custom_message: str = "", booking_url: str = "", idempotency_key: str = "") -> bool:
        """Send acceptance email to a guest.

        Args:
            guest_name: Name of the guest
            to_email: Guest's email address
            custom_message: Custom message to include

        Returns:
            True if email sent successfully, False otherwise
        """
        template = self.get_acceptance_template(guest_name, custom_message, booking_url=booking_url)
        return self.send_email(to_email, template["subject"], template["body"], idempotency_key=idempotency_key)

    def send_booking_confirmation_email(
        self,
        guest_name: str,
        to_email: str,
        scheduled_for: datetime,
        timezone_label: str,
        join_url: str,
        idempotency_key: str = "",
        personalization: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """Send the first booking confirmation email after a guest books a slot."""
        template = self.get_booking_confirmation_template(
            guest_name, scheduled_for, timezone_label, join_url, personalization=personalization
        )
        invite_attachment = {
            "filename": "mirror-talk-booking.ics",
            "content": self.build_calendar_invite(
                guest_name=guest_name,
                scheduled_for=scheduled_for,
                timezone_label=timezone_label,
                join_url=join_url,
            ),
        }
        return self.send_email(to_email, template["subject"], template["body"], attachments=[invite_attachment], idempotency_key=idempotency_key)

    def send_rejection_email(self, guest_name: str, to_email: str, custom_message: str = "", idempotency_key: str = "") -> bool:
        """Send rejection email to a guest.

        Args:
            guest_name: Name of the guest
            to_email: Guest's email address
            custom_message: Custom message to include

        Returns:
            True if email sent successfully, False otherwise
        """
        template = self.get_rejection_template(guest_name, custom_message)
        return self.send_email(to_email, template["subject"], template["body"], idempotency_key=idempotency_key)

    def send_intake_confirmation_email(
        self,
        guest_name: str,
        to_email: str,
        intake_submission: Optional[Mapping[str, Any]] = None,
        idempotency_key: str = "",
    ) -> bool:
        """Send a submission-confirmation email to an intake applicant."""
        template = self.get_intake_confirmation_template(guest_name)
        receipt_submission = intake_submission or {"full_name": guest_name, "email": to_email}
        attachments = [{"filename": "mirror-talk-application.pdf", "content": build_intake_receipt_pdf(receipt_submission)}]
        return self.send_email(
            to_email,
            template["subject"],
            template["body"],
            attachments=attachments,
            idempotency_key=idempotency_key,
        )

    def send_personal_application_request_email(
        self,
        guest_name: str,
        to_email: str,
        intake_url: str,
        agency_name: str = "",
        idempotency_key: str = "",
    ) -> bool:
        """Send a guest their own personal intake link after an agency referral."""
        template = self.get_personal_application_request_template(guest_name, intake_url, agency_name)
        return self.send_email(to_email, template["subject"], template["body"], idempotency_key=idempotency_key)

    def send_booking_link_email(self, guest_name: str, to_email: str, booking_url: str, idempotency_key: str = "") -> bool:
        """Send a guest their personal booking link again."""
        template = self.get_booking_link_template(guest_name, booking_url)
        return self.send_email(to_email, template["subject"], template["body"], idempotency_key=idempotency_key)

    def send_reschedule_link_email(
        self,
        guest_name: str,
        to_email: str,
        scheduled_for: datetime,
        timezone_label: str,
        reschedule_url: str,
        idempotency_key: str = "",
        proposed_times: Optional[list[datetime]] = None,
        proposal_mode: str = "open_calendar",
    ) -> bool:
        """Send a guest their personal rescheduling link."""
        template = self.get_reschedule_link_template(
            guest_name,
            scheduled_for,
            timezone_label,
            reschedule_url,
            proposed_times=proposed_times,
            proposal_mode=proposal_mode,
        )
        return self.send_email(to_email, template["subject"], template["body"], idempotency_key=idempotency_key)

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
