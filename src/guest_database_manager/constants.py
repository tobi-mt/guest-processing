"""Constants and configuration for Guest Database Manager."""

from typing import Dict, List

# Database configuration
DEFAULT_DB_PATH = "guest_database.db"
DEFAULT_PORT = 8052

# Column mappings for CSV/Excel import
COLUMN_MAPPINGS: Dict[str, List[str]] = {
    # Basic Information
    "full_name": [
        "Full name", "full_name", "Name", "name", "Full Name", 
        "Guest Name", "guest_name"
    ],
    "email": [
        "Email2", "email2", "Guest's Email", "guest's email", "Guest Email", 
        "guest_email", "Email", "email", "Email Address", "email_address", 
        "E-mail", "e-mail", "Contact Email", "contact_email", 
        "Primary Email", "primary_email"
    ],
    "phone": [
        "Phone", "phone", "Phone Number", "phone_number", "Mobile", "mobile", 
        "Contact Number", "contact_number"
    ],
    "website": [
        "Website", "website", "Website URL", "website_url", "Web", "web", 
        "Site", "site", "Do you have a website?"
    ],
    
    # Social Media
    "instagram": [
        "Instagram", "instagram", "Instagram Handle", "instagram_handle", 
        "IG", "ig", "@instagram", "Social Media - Instagram"
    ],
    "facebook": [
        "Facebook", "facebook", "Facebook Profile", "facebook_profile", 
        "FB", "fb", "Social Media - Facebook"
    ],
    "social_media": [
        "Do you have social media handles?", "has_social_media", 
        "Social media", "Social media handles"
    ],
    "social_handles": [
        "Kindly list your active social media handles?", "social_handles", 
        "Social handles", "Active social media"
    ],
    
    # Location & Business
    "location": [
        "Location", "location", "City", "city", "State", "state", 
        "Country", "country", "Where are you based?", "Based in"
    ],
    "business_type": [
        "Business Type", "business_type", "Industry", "industry", 
        "Business", "business", "What type of business", "Type of business"
    ],
    "business_stage": [
        "Business Stage", "business_stage", "Stage", "stage", 
        "Business Phase", "business_phase", "What stage is your business", 
        "Stage of business"
    ],
    
    # Professional Background
    "background": [
        "A brief overview of your personal and professional background", 
        "background", "Background"
    ],
    "profession": [
        "What is your current profession, and what led you to this career path?", 
        "profession", "Profession", "Current profession"
    ],
    "motivation": [
        "What motivates or inspires you in your work and life?\n", 
        "motivation", "Motivation", "What motivates you"
    ],
    "life_experiences": [
        "What life experiences or pivotal moments have shaped who you are today?\n", 
        "life_experiences", "Life experiences", "Pivotal moments"
    ],
    
    # Values & Philosophy
    "core_values": [
        "What are your core values or guiding principles?\n", 
        "core_values", "Core values", "Values"
    ],
    "faith": [
        "Do you follow a specific faith, spiritual practice, or philosophical tradition?\n", 
        "faith", "Faith", "Spiritual practice"
    ],
    "alignment": [
        "Do you believe your beliefs and values align with the themes of soulful conversations?\n", 
        "alignment", "Alignment", "Values alignment"
    ],
    "favorite_quote": [
        "Do you have a favourite quote or philosophy that guides your life?", 
        "favorite_quote", "Favorite quote", "Quote"
    ],
    
    # Podcast Related
    "passionate_topics": [
        "What topics or themes are you most passionate about discussing?\n", 
        "passionate_topics", "Passionate topics", "Discussion themes"
    ],
    "message": [
        "What message or takeaway would you like to leave with our listeners?\n", 
        "message", "Message", "Takeaway"
    ],
    "experience": [
        "Have you been a guest on podcasts or spoken at events before?\n", 
        "experience", "Experience", "Previous experience"
    ],
    
    # Additional Information
    "topics": [
        "Topics", "topics", "Interview Topics", "interview_topics", 
        "Discussion Topics", "discussion_topics", "What would you like to discuss", 
        "Topics of interest"
    ],
    "challenges": [
        "Challenges", "challenges", "Business Challenges", "business_challenges", 
        "Current Challenges", "current_challenges", "What challenges are you facing", 
        "Main challenges"
    ],
    "goals": [
        "Goals", "goals", "Business Goals", "business_goals", "Objectives", 
        "objectives", "What are your goals", "Main goals"
    ],
    "previous_guest": [
        "Previous Guest", "previous_guest", "Been on podcast before", 
        "Previous Appearance", "previous_appearance"
    ],
    "referral_source": [
        "Referral Source", "referral_source", "How did you hear about us", 
        "Referral", "referral", "Source", "source"
    ],
    "additional_info": [
        "Additional Information", "additional_information", "Additional Info", 
        "additional_info", "Comments", "comments", "Notes", "notes", "Other", 
        "other", "Anything else", "Additional notes", 
        "Is there anything else you'd like us to know about you?\n"
    ],
}

# Database column mapping (cleaned data field -> actual DB column)
DB_COLUMN_MAP: Dict[str, str] = {
    "full_name": "name",  # Maps to both name and full_name in DB
    "email": "email",
    "website": "website",
    "social_handles": "social_media_handles",
    "background": "background",
    "profession": "profession",
    "motivation": "motivation",
    "life_experiences": "life_experiences",
    "core_values": "core_values",
    "faith": "faith_practice",
    "alignment": "beliefs_align",
    "favorite_quote": "favorite_quote",
    "passionate_topics": "passionate_topics",
    "message": "message_takeaway",
    "experience": "podcast_experience",
    "additional_info": "additional_info",
    "has_social_media": "following_us",
}

# Email templates
EMAIL_TEMPLATES = {
    "acceptance": {
        "subject": "🎉 Welcome to Mirror Talk Podcast! Your Guest Spot is Confirmed",
        "body_prefix": "Dear {name},\n\nWe are absolutely thrilled to have you as a guest on the Mirror Talk Podcast! ",
    },
    "rejection": {
        "subject": "Thank You for Your Interest in Mirror Talk Podcast",
        "body_prefix": "Dear {name},\n\nThank you so much for your interest in being a guest on Mirror Talk Podcast. ",
    }
}

# Analytics configuration
ANALYTICS_CONFIG = {
    "max_profession_display": 10,
    "timeline_min_points": 2,
    "default_chart_height": 400,
}

# UI configuration
UI_CONFIG = {
    "page_title": "Guest Database Manager",
    "page_icon": "👥",
    "layout": "wide",
    "items_per_page_options": [10, 25, 50, 100],
    "default_items_per_page": 25,
}

# Status options
STATUS_OPTIONS = {
    "email_status": ["pending", "accepted", "rejected", "skipped"],
    "processing_status": ["processed", "unprocessed"],
}

# Encoding options for file import
ENCODING_OPTIONS = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]
