"""
Contact form validation and handling utilities.
"""
import re
from datetime import datetime
from typing import Optional, Tuple


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """
    Validate email address format.
    
    Args:
        email: Email address to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    email = email.strip()
    
    # Basic email regex pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not email:
        return False, "Email cannot be empty"
    
    if not re.match(pattern, email):
        return False, "Please provide a valid email address (e.g., name@example.com)"
    
    return True, None


def validate_phone(phone: str) -> Tuple[bool, Optional[str]]:
    """
    Validate phone number with country code.
    
    Args:
        phone: Phone number to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    phone = phone.strip()
    
    # Remove spaces and dashes for validation
    cleaned_phone = phone.replace(' ', '').replace('-', '')
    
    # Must start with + and have 10-15 digits
    pattern = r'^\+\d{10,15}$'
    
    if not phone:
        return False, "Phone number cannot be empty"
    
    if not cleaned_phone.startswith('+'):
        return False, "Phone number must include country code (e.g., +1234567890)"
    
    if not re.match(pattern, cleaned_phone):
        return False, "Please provide a valid phone number with country code (e.g., +911234567890)"
    
    return True, None


def validate_datetime(datetime_str: str) -> Tuple[bool, Optional[str]]:
    """
    Validate datetime string - accepts flexible natural language input.
    
    Args:
        datetime_str: Datetime string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    datetime_str = datetime_str.strip()
    
    if not datetime_str:
        return False, "Date and time cannot be empty"
    
    # Accept any reasonable input - user can specify in natural language
    # Examples: "1 December 2025 at 11pm", "2025-12-01 14:00", "tomorrow at 3pm"
    if len(datetime_str) < 5:
        return False, "Please provide more details about your preferred date and time"
    
    return True, None


def validate_timezone(timezone_str: str) -> Tuple[bool, Optional[str]]:
    """
    Validate timezone string.
    
    Args:
        timezone_str: Timezone string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    timezone_str = timezone_str.strip()
    
    if not timezone_str:
        return False, "Timezone cannot be empty"
    
    # Accept common timezone formats: IST, UTC+5:30, EST, GMT, Asia/Kolkata, etc.
    if len(timezone_str) < 2:
        return False, "Please provide a valid timezone (e.g., IST, UTC+5:30, EST)"
    
    return True, None



def validate_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate name.
    
    Args:
        name: Name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    name = name.strip()
    
    if not name:
        return False, "Name cannot be empty"
    
    if len(name) < 2:
        return False, "Name must be at least 2 characters long"
    
    if len(name) > 100:
        return False, "Name is too long (maximum 100 characters)"
    
    return True, None
