from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app import db, limiter
from app.models import User
from app.utils.validators import (
    validate_email, validate_password, validate_enrollment_number,
    validate_name, sanitize_input
)

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
@limiter.limit("5 per minute")  # Rate limit registration
def register():
    """Register a new user"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        # Sanitize and get input
        name = sanitize_input(data.get('name'))
        enrollment_number = sanitize_input(data.get('enrollment_number'))
        email = sanitize_input(data.get('email'))
        password = data.get('password')  # Don't sanitize password
        
        # Validate all required fields
        if not name or not enrollment_number or not email or not password:
            return jsonify({
                'success': False,
                'error': 'All fields are required: name, enrollment_number, email, and password'
            }), 400
        
        # Enhanced input validation
        is_valid, error = validate_name(name)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        is_valid, error = validate_enrollment_number(enrollment_number)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        is_valid, error = validate_email(email)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        is_valid, error = validate_password(password)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # Check if enrollment number already exists (SQL injection protected by SQLAlchemy)
        if User.query.filter_by(enrollment_number=enrollment_number).first():
            return jsonify({
                'success': False,
                'error': 'Enrollment number already exists'
            }), 400
        
        # Check if email already exists (SQL injection protected by SQLAlchemy)
        if User.query.filter_by(email=email).first():
            return jsonify({
                'success': False,
                'error': 'Email already exists'
            }), 400
        
        # Create new user
        user = User(
            name=name,
            enrollment_number=enrollment_number,
            email=email
        )

        admin_emails = current_app.config.get('ADMIN_EMAILS', [])
        admin_enrollments = current_app.config.get('ADMIN_ENROLLMENTS', [])
        if (email and email.lower() in admin_emails) or (
            enrollment_number and enrollment_number.lower() in admin_enrollments
        ):
            user.role = 'admin'
        # Hash password using werkzeug.security (via User model method)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Create JWT access token
        access_token = create_access_token(identity=str(user.id))

        
        return jsonify({
            'success': True,
            'message': 'User registered successfully',
            'data': {
                'user': user.to_dict(),
                'access_token': access_token
            }
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Registration failed: {str(e)}'
        }), 500

@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")  # Rate limit login attempts
def login():
    """Login user and return JWT token"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        # Sanitize input
        identifier = sanitize_input(data.get('enrollment_number') or data.get('email'))
        password = data.get('password')  # Don't sanitize password
        
        if not identifier or not password:
            return jsonify({
                'success': False,
                'error': 'Enrollment number (or email) and password are required'
            }), 400
        
        # Validate password
        is_valid, error = validate_password(password)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # Find user by enrollment_number or email (SQL injection protected by SQLAlchemy)
        user = User.query.filter(
            (User.enrollment_number == identifier) | (User.email == identifier)
        ).first()
        
        # Verify password using werkzeug.security (via User model method)
        if not user or not user.check_password(password):
            return jsonify({
                'success': False,
                'error': 'Invalid enrollment number/email or password'
            }), 401
        
        # Create JWT access token
        access_token = create_access_token(identity=str(user.id))

        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'data': {
                'user': user.to_dict(),
                'access_token': access_token
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}'
        }), 500

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
@limiter.limit("30 per minute")
def get_current_user():
    """Get current authenticated user"""
    try:
        user_id = get_jwt_identity()
        # SQL injection protected by SQLAlchemy - using parameterized query
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'user': user.to_dict()
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get user: {str(e)}'
        }), 500
