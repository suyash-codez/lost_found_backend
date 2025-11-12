"""
Input validation utilities for security and data integrity
"""
import re
from flask import jsonify

def validate_email(email):
    """Validate email format"""
    if not email:
        return False, "Email is required"
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    
    if len(email) > 120:
        return False, "Email must be less than 120 characters"
    
    return True, None

def validate_password(password):
    """Validate password strength"""
    if not password:
        return False, "Password is required"
    
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
    
    if len(password) > 128:
        return False, "Password must be less than 128 characters"
    
    return True, None

def validate_enrollment_number(enrollment_number):
    """Validate enrollment number format"""
    if not enrollment_number:
        return False, "Enrollment number is required"
    
    if len(enrollment_number) > 50:
        return False, "Enrollment number must be less than 50 characters"
    
    # Allow alphanumeric and common separators
    if not re.match(r'^[a-zA-Z0-9\-_]+$', enrollment_number):
        return False, "Enrollment number contains invalid characters"
    
    return True, None

def validate_name(name):
    """Validate name format"""
    if not name:
        return False, "Name is required"
    
    if len(name) < 2:
        return False, "Name must be at least 2 characters long"
    
    if len(name) > 100:
        return False, "Name must be less than 100 characters"
    
    # Allow letters, spaces, hyphens, and apostrophes
    if not re.match(r'^[a-zA-Z\s\-\']+$', name):
        return False, "Name contains invalid characters"
    
    return True, None

def validate_string_field(value, field_name, min_length=1, max_length=200, required=True):
    """Generic string field validator"""
    if required and not value:
        return False, f"{field_name} is required"
    
    if value and len(value) > max_length:
        return False, f"{field_name} must be less than {max_length} characters"
    
    if value and len(value) < min_length:
        return False, f"{field_name} must be at least {min_length} characters long"
    
    return True, None

def validate_date_format(date_string):
    """Validate date format (YYYY-MM-DD)"""
    if not date_string:
        return True, None  # Date is optional
    
    pattern = r'^\d{4}-\d{2}-\d{2}$'
    if not re.match(pattern, date_string):
        return False, "Date must be in YYYY-MM-DD format"
    
    try:
        from datetime import datetime
        datetime.strptime(date_string, '%Y-%m-%d')
        return True, None
    except ValueError:
        return False, "Invalid date"

def validate_url(url):
    """Validate URL format"""
    if not url:
        return True, None  # URL is optional
    
    if len(url) > 500:
        return False, "URL must be less than 500 characters"
    
    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    if not re.match(pattern, url):
        return False, "Invalid URL format"
    
    return True, None

def sanitize_input(value):
    """Basic input sanitization to prevent XSS"""
    if not value:
        return value
    
    # Remove potentially dangerous characters
    value = str(value).strip()
    
    # Remove null bytes
    value = value.replace('\x00', '')
    
    return value

def validate_integer(value, field_name, min_value=None, max_value=None, required=True):
    """Validate integer field"""
    if required and value is None:
        return False, f"{field_name} is required"
    
    if value is not None:
        try:
            int_value = int(value)
            if min_value is not None and int_value < min_value:
                return False, f"{field_name} must be at least {min_value}"
            if max_value is not None and int_value > max_value:
                return False, f"{field_name} must be at most {max_value}"
        except (ValueError, TypeError):
            return False, f"{field_name} must be a valid integer"
    
    return True, None

def validate_enum(value, field_name, allowed_values, required=True):
    """Validate enum/choice field"""
    if required and not value:
        return False, f"{field_name} is required"
    
    if value and value not in allowed_values:
        return False, f"{field_name} must be one of: {', '.join(allowed_values)}"
    
    return True, None

