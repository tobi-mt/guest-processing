"""AI-powered intelligent assistant for guest management workflows.

This module provides LLM-powered features for:
- Smart email draft generation
- Automated guest research
- Intelligent recommendations
- Follow-up reminders
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from guest_database_manager.db_connection import connect_database

logger = logging.getLogger(__name__)


class AIAssistant:
    """AI-powered assistant for intelligent guest management."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        """Initialize AI assistant with OpenAI API key."""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.last_error: Optional[str] = None
        self.last_error_supports_json_fallback = False
    
    def _call_openai(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        response_format: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Make API call to OpenAI."""
        if not self.api_key:
            logger.warning("OpenAI API key not configured")
            self.last_error = "OpenAI API key is not configured"
            return None

        self.last_error = None
        self.last_error_supports_json_fallback = False
        try:
            request_payload: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                **({"response_format": response_format} if response_format else {}),
            }
            # GPT-5 and reasoning-model Chat Completions requests reject custom
            # sampling settings.  Omitting temperature uses the provider default
            # and keeps the assistant compatible with the model configured at run
            # time, rather than assuming the legacy gpt-4o-mini default.
            model_name = self.model.lower()
            if not model_name.startswith(("gpt-5", "o1", "o3", "o4")):
                request_payload["temperature"] = temperature
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=request_payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except requests.HTTPError as exc:
            # The status alone is not actionable (a 400 can mean an invalid model,
            # parameter, or project policy).  Log only OpenAI's structured error
            # metadata, never the prompt, response payload, or credentials.
            error_payload: Dict[str, Any] = {}
            if exc.response is not None:
                try:
                    error_payload = exc.response.json().get("error") or {}
                except (ValueError, AttributeError):
                    pass
            logger.error(
                "OpenAI API request rejected: status=%s type=%s code=%s message=%s",
                exc.response.status_code if exc.response is not None else "unknown",
                error_payload.get("type", "unknown"),
                error_payload.get("code", "unknown"),
                error_payload.get("message", "No provider error message returned"),
            )
            error_type = str(error_payload.get("type") or "request_error")
            error_code = str(error_payload.get("code") or "unknown")
            self.last_error = f"OpenAI rejected the request ({error_type}: {error_code})"
            self.last_error_supports_json_fallback = bool(
                response_format
                and error_type == "invalid_request_error"
                and error_code in {"unsupported_parameter", "unsupported_value"}
            )
            return None
        except requests.RequestException as exc:
            logger.error("OpenAI API request failed: %s", exc)
            self.last_error = "OpenAI could not be reached"
            return None
        except (KeyError, TypeError, ValueError) as exc:
            logger.error("OpenAI API returned an unexpected response shape: %s", exc)
            self.last_error = "OpenAI returned an unexpected response"
            return None

    @staticmethod
    def _guest_context(guest_data: Dict[str, Any]) -> str:
        """Return the complete, non-empty application context using persisted field names.

        Older import paths still use a few legacy aliases, so accept those as a
        compatibility measure.  The AI must see the same information an editor sees.
        """
        fields = (
            ("Name", ("full_name", "name")),
            ("Profession", ("profession",)),
            ("Background", ("background",)),
            ("Why they want to appear", ("motivation",)),
            ("Life experiences", ("life_experiences",)),
            ("Core values", ("core_values",)),
            ("Faith or spiritual practice", ("faith_practice", "faith")),
            ("Alignment with the show", ("beliefs_align", "alignment")),
            ("Favourite quote", ("favorite_quote",)),
            ("Passionate topics", ("passionate_topics",)),
            ("Message they want listeners to take away", ("message_takeaway", "message")),
            ("Podcast experience", ("podcast_experience", "experience")),
            ("Additional information", ("additional_info",)),
            ("Website", ("website",)),
            ("Social media", ("social_media_handles", "social_handles")),
        )
        lines = []
        for label, keys in fields:
            value = next((str(guest_data.get(key)).strip() for key in keys if guest_data.get(key) and str(guest_data[key]).strip()), "")
            if value:
                lines.append(f"- {label}: {value}")
        return "\n".join(lines) or "- No application details were provided beyond the guest record."
    
    def generate_acceptance_email(
        self,
        guest_data: Dict[str, Any],
        podcast_name: str = "Mirror Talk",
        host_name: str = "Tobi",
        custom_message: Optional[str] = None
    ) -> Optional[str]:
        """Generate a personalized acceptance email for a guest."""
        application_context = self._guest_context(guest_data)
        
        prompt = f"""You are writing a warm, authentic acceptance email for the {podcast_name} podcast.

Guest application (use only details present here; do not invent achievements or facts):
{application_context}

{f"Host's Custom Note: {custom_message}" if custom_message else ""}

Write a personalized acceptance email that:
1. Warmly welcomes them as a guest
2. Shows genuine interest in their background or topics (mention something specific)
3. Explains what Mirror Talk is about (soulful conversations, faith, purpose, resilience)
4. Mentions next steps (scheduling, preparation)
5. Sounds authentic and conversational, not corporate
6. Keep it concise (2-3 short paragraphs), while including one concrete application detail and why it belongs on Mirror Talk

The email should feel personal, not templated. Sign it from {host_name}."""
        
        messages = [
            {"role": "system", "content": "You are a warm, thoughtful podcast host writing personal emails to potential guests."},
            {"role": "user", "content": prompt}
        ]
        
        return self._call_openai(messages, temperature=0.8)

    def generate_partner_strategy(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a grounded partner assessment and several outreach variants."""
        prompt = f"""You are the partnership editor for Mirror Talk: Soulful Conversations.
Use only the supplied evidence. Do not invent a person, email address, audience metric,
relationship, achievement, or claim. Return JSON with these keys:
- score: integer 0-100
- confidence: one of low, medium, high
- rationale: concise evidence-grounded explanation
- risks: array of concise strings
- angles: array of exactly three objects with title, value_exchange, episode_connection
- emails: array of exactly three objects with angle_title, angle_rationale, subject, body

Each email must be genuinely specific, warm, concise, and written from Tobi. Mention a
verified detail, explain the mutual audience value, make one clear low-friction request,
and avoid generic praise. If a named recipient is unavailable, address the partnerships
or communications team. Never imply that the message has been sent.
Follow the requested template objective and tone in the context while keeping facts grounded.

Context:
{json.dumps(context, ensure_ascii=False, sort_keys=True)}"""
        raw = self._call_openai(
            [
                {"role": "system", "content": "You produce conservative, source-grounded partnership intelligence as strict JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            self.last_error = "OpenAI returned invalid partner strategy JSON"
            return None
        return value if isinstance(value, dict) else None
    
    def generate_rejection_email(
        self,
        guest_data: Dict[str, Any],
        podcast_name: str = "Mirror Talk",
        host_name: str = "Tobi",
        custom_message: Optional[str] = None,
        reason: Optional[str] = None
    ) -> Optional[str]:
        """Generate a kind, respectful rejection email."""
        guest_name = guest_data.get("full_name") or guest_data.get("name", "there")
        
        prompt = f"""Write a kind, respectful email declining a podcast guest application.

Guest Name: {guest_name}
Podcast: {podcast_name}

{f"Reason (internal, don't state directly): {reason}" if reason else ""}
{f"Host's Custom Note: {custom_message}" if custom_message else ""}

The email should:
1. Thank them for their interest and time
2. Politely decline without going into specific reasons
3. Encourage them to keep sharing their message in other ways
4. Be warm and respectful, maintaining goodwill
5. Keep it brief (1-2 short paragraphs)

DO NOT make false promises like "we'll keep you in mind for the future" unless the host specified that.
Be honest but kind. Sign from {host_name}."""
        
        messages = [
            {"role": "system", "content": "You are a compassionate podcast host writing respectful rejection emails."},
            {"role": "user", "content": prompt}
        ]
        
        return self._call_openai(messages, temperature=0.7)
    
    def generate_follow_up_email(
        self,
        guest_data: Dict[str, Any],
        context: str,
        days_since_last_contact: int = 7
    ) -> Optional[str]:
        """Generate a follow-up email based on context."""
        guest_name = guest_data.get("full_name") or guest_data.get("name", "there")
        
        prompt = f"""Write a friendly follow-up email to a podcast guest.

Guest Name: {guest_name}
Context: {context}
Days Since Last Contact: {days_since_last_contact}

The email should:
1. Reference the previous interaction
2. Gently check in on next steps
3. Be brief and non-pushy
4. Sound natural and friendly

Keep it to 2-3 sentences."""
        
        messages = [
            {"role": "system", "content": "You are writing friendly follow-up emails."},
            {"role": "user", "content": prompt}
        ]
        
        return self._call_openai(messages, temperature=0.7)
    
    def research_guest_from_text(self, guest_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze guest data and generate insights using AI."""
        application_context = self._guest_context(guest_data)
        
        prompt = f"""Analyze this podcast guest application and provide insights.

Guest application (treat missing information as unknown, not a negative):
{application_context}

Provide:
1. A 2-4 sentence evidence-grounded summary
2. Key themes (3-5 specific topics)
3. Fit score (1-10 for Mirror Talk: faith, purpose, healing, resilience, authentic stories) and a short rationale tied to application facts
4. Conversation angles (3 specific, non-generic angles)
5. Concerns or clarification questions (empty list if none; missing information is a clarification, never a red flag)
6. Best timing (or "No evidence for a timing hook")

Return a JSON object only, with keys: summary, themes, fit_score, fit_rationale, conversation_angles, concerns, best_timing, evidence_used."""
        
        messages = [
            {"role": "system", "content": "You are an expert podcast producer analyzing guest applications."},
            {"role": "user", "content": prompt}
        ]
        
        result = self._call_openai(messages, temperature=0.5, response_format={"type": "json_object"})
        # Keep the feature usable when an intentionally configured legacy model
        # does not support Chat Completions JSON mode.
        if not result and self.last_error_supports_json_fallback:
            result = self._call_openai(messages, temperature=0.5)

        if not result:
            return {}

        try:
            # Try to parse JSON response
            # Be tolerant of responses from older models that wrap valid JSON in fences.
            clean_result = re.sub(r"^```(?:json)?\s*|\s*```$", "", result.strip(), flags=re.IGNORECASE)
            research_data = json.loads(clean_result)
            if not isinstance(research_data, dict):
                raise ValueError("Analysis response was not a JSON object")
            research_data["analyzed_at"] = datetime.now().isoformat()
            return research_data
        except (json.JSONDecodeError, TypeError, ValueError):
            # Fallback to text format
            return {
                "summary": result,
                "analyzed_at": datetime.now().isoformat()
            }
    
    def web_search_guest(self, guest_data: Dict[str, Any]) -> Dict[str, Any]:
        """Search for guest information online (placeholder for future implementation)."""
        guest_name = guest_data.get("full_name", "")
        website = guest_data.get("website", "")
        social_media = guest_data.get("social_media_handles", "")
        
        # This is a placeholder - in production, you'd use a web scraping service
        # or search API like SerpAPI, Bing API, etc.
        
        logger.info(f"Web search for guest: {guest_name}")
        
        return {
            "guest_name": guest_name,
            "website": website,
            "social_media": social_media,
            "search_performed_at": datetime.now().isoformat(),
            "note": "Web search feature - implement with SerpAPI or similar service"
        }
    
    def generate_interview_questions(self, guest_data: Dict[str, Any], num_questions: int = 10) -> List[str]:
        """Generate thoughtful interview questions based on guest information."""
        guest_name = guest_data.get("full_name") or guest_data.get("name", "the guest")
        application_context = self._guest_context(guest_data)
        
        prompt = f"""Generate {num_questions} thoughtful, deep interview questions for a Mirror Talk podcast episode.

Guest: {guest_name}
Guest application (use only these facts; do not make assumptions):
{application_context}

Mirror Talk focuses on: faith, purpose, healing, resilience, authentic personal stories.

Generate questions that:
1. Go beyond surface-level conversation
2. Invite vulnerability and authenticity
3. Connect to universal human experiences
4. Build on each other naturally
5. Are specific to this guest's story: each question must clearly draw on a concrete detail from the application
6. Progress from origin story, through tension or change, to practical meaning for listeners; avoid duplicate themes and generic prompts

Return ONLY the questions, numbered 1-{num_questions}, one per line."""
        
        messages = [
            {"role": "system", "content": "You are an expert podcast interviewer known for deep, meaningful conversations."},
            {"role": "user", "content": prompt}
        ]
        
        result = self._call_openai(messages, temperature=0.8)
        
        if result:
            # Parse questions from response
            questions = []
            for line in result.split('\n'):
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith('-')):
                    # Remove numbering
                    question = re.sub(r'^\d+[\.\)]\s*', '', line)
                    question = re.sub(r'^-\s*', '', question)
                    if question:
                        questions.append(question)
            return questions[:num_questions]
        
        return []
    
    def suggest_email_subject(self, email_type: str, guest_name: str) -> str:
        """Generate engaging email subject lines."""
        subjects = {
            "acceptance": [
                f"Excited to have you on Mirror Talk, {guest_name}! 🎙️",
                f"Welcome to Mirror Talk, {guest_name}!",
                f"{guest_name}, let's share your story on Mirror Talk",
                f"Your Mirror Talk invitation, {guest_name}"
            ],
            "rejection": [
                f"Thank you for your interest, {guest_name}",
                "Regarding your Mirror Talk application",
                "Mirror Talk Application Update"
            ],
            "follow_up": [
                f"Following up - Mirror Talk with {guest_name}",
                "Checking in about our conversation",
                "Next steps for your Mirror Talk episode"
            ]
        }
        
        import random
        return random.choice(subjects.get(email_type, ["Mirror Talk Podcast"]))
    
    def analyze_guest_fit(self, guest_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze how well a guest fits the podcast using the guest_recommender module."""
        try:
            from guest_database_manager.guest_recommender import score_guest
            
            score_result = score_guest(guest_data)
            
            return {
                "fit_score": score_result.get("total_score", 0),
                "fit_category": score_result.get("category", "Unknown"),
                "strengths": score_result.get("signals", []),
                "concerns": score_result.get("cautions", []),
                "recommendation": score_result.get("recommendation", "")
            }
        except ImportError:
            logger.warning("guest_recommender module not available")
            return {"fit_score": 0, "note": "Scoring unavailable"}


class FollowUpManager:
    """Manage automated follow-ups and reminders."""
    
    def __init__(self, db_path: str):
        """Initialize follow-up manager with database connection."""
        self.db_path = db_path
    
    def get_guests_needing_follow_up(self, days_threshold: int = 7) -> List[Dict[str, Any]]:
        """Find guests who haven't been contacted in specified days."""
        import sqlite3

        with connect_database(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            threshold_date = datetime.now() - timedelta(days=days_threshold)
            
            query = """
                SELECT * FROM guests
                WHERE email_status = 'Accepted'
                AND (email_sent_at IS NULL OR email_sent_at < ?)
                AND is_processed = 1
                ORDER BY email_sent_at ASC
            """
            
            results = conn.execute(query, (threshold_date.isoformat(),)).fetchall()
            return [dict(row) for row in results]
    
    def get_upcoming_interviews(self, days_ahead: int = 3) -> List[Dict[str, Any]]:
        """Get interviews scheduled in the next N days for reminder emails."""
        import sqlite3

        with connect_database(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            now = datetime.now()
            future_date = now + timedelta(days=days_ahead)
            
            query = """
                SELECT * FROM interviews
                WHERE scheduled_for BETWEEN ? AND ?
                AND status = 'scheduled'
                AND reminder_status != 'sent'
                ORDER BY scheduled_for ASC
            """
            
            results = conn.execute(query, (now.isoformat(), future_date.isoformat())).fetchall()
            return [dict(row) for row in results]


# Convenience function to create AI assistant
def create_ai_assistant(api_key: Optional[str] = None) -> AIAssistant:
    """Create and return an AI assistant instance."""
    return AIAssistant(api_key=api_key)
