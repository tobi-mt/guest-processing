#!/usr/bin/env python3
"""
Create a sample Excel file for testing the import functionality
"""

import pandas as pd
import sys

def create_sample_excel():
    """Create a sample Excel file with questionnaire data."""
    
    # Sample data matching the Excel structure
    sample_data = {
        'ID': [1, 2, 3],
        'Start time': ['2025-01-01 10:00', '2025-01-02 11:00', '2025-01-03 12:00'],
        'Completion time': ['2025-01-01 10:30', '2025-01-02 11:30', '2025-01-03 12:30'],
        'Email': ['anonymous', 'anonymous', 'anonymous'],
        'Name': ['John', 'Jane', 'Bob'],
        'Last modified time': ['2025-01-01 10:30', '2025-01-02 11:30', '2025-01-03 12:30'],
        'Full name': ['John Smith', 'Jane Doe', 'Bob Johnson'],
        'Email2': ['john.smith@example.com', 'jane.doe@example.com', 'bob.johnson@example.com'],
        'Do you have a website?': ['Yes', 'No', 'Yes'],
        'Website': ['https://johnsmith.com', None, 'https://bobjohnson.com'],
        'Do you have social media handles?': ['Yes', 'Yes', 'No'],
        'Kindly list your active social media handles?': ['@johnsmith', '@janedoe', None],
        'A brief overview of your personal and professional background': [
            'I am a software engineer with 10 years of experience...',
            'I am a marketing professional who loves helping businesses grow...',
            'I am a chef and restaurant owner passionate about sustainable food...'
        ],
        'What is your current profession, and what led you to this career path?': [
            'Software Engineer - I started coding in college and fell in love with problem solving',
            'Marketing Director - I discovered my passion for storytelling in my first job',
            'Chef and Restaurant Owner - Cooking has been my passion since childhood'
        ],
        'What motivates or inspires you in your work and life?\n': [
            'Creating solutions that help people and make their lives easier',
            'Helping small businesses find their voice and connect with customers',
            'Bringing people together through food and creating memorable experiences'
        ],
        'What life experiences or pivotal moments have shaped who you are today?\n': [
            'Moving to a new country taught me resilience and adaptability',
            'Losing my job during the pandemic made me appreciate stability and relationships',
            'Opening my first restaurant was terrifying but taught me to trust my instincts'
        ],
        'What are your core values or guiding principles?\n': [
            'Integrity, continuous learning, and helping others',
            'Authenticity, empathy, and creative collaboration',
            'Sustainability, community, and craftsmanship'
        ],
        'Do you follow a specific faith, spiritual practice, or philosophical tradition?\n': [
            'I practice mindfulness meditation and follow Buddhist principles',
            'I am Christian and find strength in my faith community',
            'I follow stoic philosophy and practice gratitude daily'
        ],
        'Do you believe your beliefs and values align with the themes of soulful conversations?\n': [
            'Absolutely - I believe technology should serve humanity',
            'Yes - marketing should be about authentic human connection',
            'Definitely - food is about nourishing both body and soul'
        ],
        'Do you have a favourite quote or philosophy that guides your life?': [
            '"Be the change you wish to see in the world" - Gandhi',
            '"The best way to find yourself is to lose yourself in service to others" - Gandhi',
            '"Cooking is love made visible" - Unknown'
        ],
        'What topics or themes are you most passionate about discussing?\n': [
            'Technology ethics, digital wellness, and human-centered design',
            'Authentic marketing, brand storytelling, and customer empathy',
            'Sustainable food systems, local sourcing, and culinary traditions'
        ],
        'What message or takeaway would you like to leave with our listeners?\n': [
            'Technology should enhance our humanity, not replace it',
            'Authentic connection is the foundation of all successful relationships',
            'Food is a universal language that brings people together'
        ],
        'Have you been a guest on podcasts or spoken at events before?\n': [
            'Yes, I have been on 3 tech podcasts and spoken at 2 conferences',
            'No, this would be my first podcast experience',
            'Yes, I have appeared on several food shows and local podcasts'
        ],
        "Is there anything else you'd like us to know about you?\n": [
            'I volunteer teach coding to underprivileged youth',
            'I am a single mother of two amazing kids',
            'I donate 10% of restaurant profits to local food banks'
        ],
        'Are you following us on podcast platforms and social media?': [
            'Yes, I follow on Spotify and Instagram',
            'I just started following on Apple Podcasts',
            'Yes, I follow on all platforms'
        ],
        'Do you confirm that all questions and fields have been answered fully and accurately?': [
            'Yes', 'Yes', 'Yes'
        ]
    }
    
    # Create DataFrame
    df = pd.DataFrame(sample_data)
    
    # Save to Excel
    excel_filename = 'sample_questionnaire.xlsx'
    df.to_excel(excel_filename, index=False)
    
    print(f"✅ Created sample Excel file: {excel_filename}")
    print(f"📊 Contains {len(df)} sample guests with full questionnaire data")
    print(f"📋 Columns: {len(df.columns)}")
    
    return excel_filename

if __name__ == '__main__':
    create_sample_excel()
