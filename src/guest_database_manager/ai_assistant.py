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

logger = logging.getLogger(__name__)


class AIAssistant:
    """AI-powered assistant for intelligent guest management."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        """Initialize AI assistant with OpenAI API key."""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.base_url = "https://api.openai.com/v1/chat/completions"
    
    def _call_openai(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> Optional[str]:
        """Make API call to OpenAI."""
        if not self.api_key:
            logger.warning("OpenAI API key not configured")
            return None
        
        try:
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return None
    
    def generate_acceptance_email(
        self,
        guest_data: Dict[str, Any],
        podcast_name: str = "Mirror Talk",
        host_name: str = "Tobi",
        custom_message: Optional[str] = None
    ) -> Optional[str]:
        """Generate a personalized acceptance email for a guest."""
        guest_name = guest_data.get("full_name") or guest_data.get("name", "there")
        background = guest_data.get("background", "")
        passionate_topics = guest_data.get("passionate_topics", "")
        message_takeaway = guest_data.get("message_takeaway", "")
        profession = guest_data.get("profession", "")
        
        prompt = f"""You are writing a warm, authentic acceptance email for the {podcast_name} podcast.

Guest Information:
- Name: {guest_name}
- Profession: {profession}
- Background: {background}
- Passionate Topics: {passionate_topics}
- Message They Want to Share: {message_takeaway}

{f"Host's Custom Note: {custom_message}" if custom_message else ""}

Write a personalized acceptance email that:
1. Warmly welcomes them as a guest
2. Shows genuine interest in their background or topics (mention something specific)
3. Explains what Mirror Talk is about (soulful conversations, faith, purpose, resilience)
4. Mentions next steps (scheduling, preparation)
5. Sounds authentic and conversational, not corporate
6. Keep it concise (2-3 short paragraphs)

The email should feel personal, not templated. Sign it from {host_name}."""
        
        messages = [
            {"role": "system", "content": "You are a warm, thoughtful podcast host writing personal emails to potential guests."},
            {"role": "user", "content": prompt}
        ]
        
        return self._call_openai(messages, temperature=0.8)
    
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
        guest_name = guest_data.get("full_name") or guest_data.get("name", "Unknown")
        background = guest_data.get("background", "")
        profession = guest_data.get("profession", "")
        passionate_topics = guest_data.get("passionate_topics", "")
        message_takeaway = guest_data.get("message_takeaway", "")
        life_experiences = guest_data.get("life_experiences", "")
        core_values = guest_data.get("core_values", "")
        faith_practice = guest_data.get("faith_practice", "")
        
        prompt = f"""Analyze this podcast guest application and provide insights.

Guest: {guest_name}
Profession: {profession}
Background: {background}
Life Experiences: {life_experiences}
Core Values: {core_values}
Faith/Spiritual Practice: {faith_practice}
Passionate Topics: {passionate_topics}
Message: {message_takeaway}

Provide:
1. Key Themes (3-5 bullet points of main topics they could discuss)
2. Fit Score (1-10 for Mirror Talk podcast which focuses on: faith, purpose, healing, resilience, authentic stories)
3. Conversation Angles (3 specific questions or angles to explore)
4. Potential Concerns (any red flags or areas needing clarity)
5. Best Timing (when would their story be most relevant - any seasonal/current event tie-ins)

Format as JSON with keys: themes, fit_score, conversation_angles, concerns, best_timing"""
        
        messages = [
            {"role": "system", "content": "You are an expert podcast producer analyzing guest applications."},
            {"role": "user", "content": prompt}
        ]
        
        result = self._call_openai(messages, temperature=0.5)
        
        try:
            # Try to parse JSON response
            research_data = json.loads(result)
            research_data["analyzed_at"] = datetime.now().isoformat()
            return research_data
        except (json.JSONDecodeError, TypeError):
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
        background = guest_data.get("background", "")
        passionate_topics = guest_data.get("passionate_topics", "")
        life_experiences = guest_data.get("life_experiences", "")
        profession = guest_data.get("profession", "")
        
        prompt = f"""Generate {num_questions} thoughtful, deep interview questions for a Mirror Talk podcast episode.

Guest: {guest_name}
Profession: {profession}
Background: {background}
Life Experiences: {life_experiences}
Passionate Topics: {passionate_topics}

Mirror Talk focuses on: faith, purpose, healing, resilience, authentic personal stories.

Generate questions that:
1. Go beyond surface-level conversation
2. Invite vulnerability and authenticity
3. Connect to universal human experiences
4. Build on each other naturally
5. Are specific to this guest's story

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
        
        with sqlite3.connect(self.db_path) as conn:
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
        
        with sqlite3.connect(self.db_path) as conn:
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
