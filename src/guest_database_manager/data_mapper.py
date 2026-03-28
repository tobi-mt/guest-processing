"""Data mapping utilities for CSV/Excel import."""

import pandas as pd
from typing import Dict, List, Any, Optional

try:
    from .constants import COLUMN_MAPPINGS
except ImportError as exc:
    if "attempted relative import" not in str(exc):
        raise
    from constants import COLUMN_MAPPINGS


class DataMapper:
    """Handles mapping of CSV/Excel data to database schema."""
    
    @staticmethod
    def get_column_value(row: pd.Series, possible_columns: List[str]) -> str:
        """
        Get value from row using possible column names.
        
        Args:
            row: Pandas Series representing a row
            possible_columns: List of possible column names to try
            
        Returns:
            The value as a string, or empty string if not found
        """
        # Try exact match first
        for col in possible_columns:
            if col in row.index and pd.notna(row[col]):
                return str(row[col]).strip()
        
        # Try case-insensitive match
        for col in possible_columns:
            for actual_col in row.index:
                if actual_col.lower().strip() == col.lower().strip():
                    if pd.notna(row[actual_col]):
                        return str(row[actual_col]).strip()
        
        return ""
    
    @staticmethod
    def clean_guest_data(row: pd.Series) -> Dict[str, Any]:
        """
        Clean and normalize guest data from a pandas Series.
        
        Args:
            row: Pandas Series representing a row from CSV/Excel
            
        Returns:
            Dictionary with cleaned and normalized data
        """
        return {
            'full_name': DataMapper.get_column_value(row, COLUMN_MAPPINGS["full_name"]),
            'email': DataMapper.get_column_value(row, COLUMN_MAPPINGS["email"]),
            'phone': DataMapper.get_column_value(row, COLUMN_MAPPINGS["phone"]),
            'instagram': DataMapper.get_column_value(row, COLUMN_MAPPINGS["instagram"]),
            'facebook': DataMapper.get_column_value(row, COLUMN_MAPPINGS["facebook"]),
            'website': DataMapper.get_column_value(row, COLUMN_MAPPINGS["website"]),
            'location': DataMapper.get_column_value(row, COLUMN_MAPPINGS["location"]),
            'business_type': DataMapper.get_column_value(row, COLUMN_MAPPINGS["business_type"]),
            'business_stage': DataMapper.get_column_value(row, COLUMN_MAPPINGS["business_stage"]),
            'topics': DataMapper.get_column_value(row, COLUMN_MAPPINGS["topics"]),
            'challenges': DataMapper.get_column_value(row, COLUMN_MAPPINGS["challenges"]),
            'goals': DataMapper.get_column_value(row, COLUMN_MAPPINGS["goals"]),
            'previous_guest': DataMapper.get_column_value(row, COLUMN_MAPPINGS["previous_guest"]),
            'referral_source': DataMapper.get_column_value(row, COLUMN_MAPPINGS["referral_source"]),
            'additional_info': DataMapper.get_column_value(row, COLUMN_MAPPINGS["additional_info"]),
            'background': DataMapper.get_column_value(row, COLUMN_MAPPINGS["background"]),
            'profession': DataMapper.get_column_value(row, COLUMN_MAPPINGS["profession"]),
            'motivation': DataMapper.get_column_value(row, COLUMN_MAPPINGS["motivation"]),
            'life_experiences': DataMapper.get_column_value(row, COLUMN_MAPPINGS["life_experiences"]),
            'core_values': DataMapper.get_column_value(row, COLUMN_MAPPINGS["core_values"]),
            'faith': DataMapper.get_column_value(row, COLUMN_MAPPINGS["faith"]),
            'alignment': DataMapper.get_column_value(row, COLUMN_MAPPINGS["alignment"]),
            'favorite_quote': DataMapper.get_column_value(row, COLUMN_MAPPINGS["favorite_quote"]),
            'passionate_topics': DataMapper.get_column_value(row, COLUMN_MAPPINGS["passionate_topics"]),
            'message': DataMapper.get_column_value(row, COLUMN_MAPPINGS["message"]),
            'experience': DataMapper.get_column_value(row, COLUMN_MAPPINGS["experience"]),
            'has_social_media': DataMapper.get_column_value(row, COLUMN_MAPPINGS["social_media"]),
            'social_handles': DataMapper.get_column_value(row, COLUMN_MAPPINGS["social_handles"]),
            'is_processed': False
        }
    
    @staticmethod
    def validate_guest_data(guest_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate guest data before insertion.
        
        Args:
            guest_data: Dictionary containing guest information
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not guest_data.get('full_name'):
            return False, "Missing required field: full_name"
        
        # Email is optional, but if provided should have basic format
        email = guest_data.get('email', '')
        if email and '@' not in email:
            return False, f"Invalid email format: {email}"
        
        return True, None
    
    @staticmethod
    def should_update_email(existing_email: Optional[str], new_email: Optional[str]) -> bool:
        """
        Determine if email should be updated.
        
        Args:
            existing_email: Current email in database
            new_email: New email from import
            
        Returns:
            True if email should be updated
        """
        if not new_email or new_email == 'anonymous':
            return False
        
        if not existing_email or existing_email == 'anonymous':
            return True
        
        return False
