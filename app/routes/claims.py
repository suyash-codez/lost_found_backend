from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, limiter
from app.models import Claim, LostItem, FoundItem, User, ClaimMedia
from datetime import datetime
from app.utils.validators import (
    validate_integer, validate_enum, validate_string_field,
    sanitize_input
)
from app.utils.cloudinary_client import upload_media

claims_bp = Blueprint('claims', __name__)

@claims_bp.route('', methods=['POST'])
@jwt_required()
@limiter.limit("20 per hour")
def create_claim():
    """Create a new claim (requires JWT authentication)"""
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form.to_dict()
        else:
            data = request.get_json()
        identity = get_jwt_identity()
        try:
            claimer_id = int(identity)
        except (TypeError, ValueError):
            return jsonify({
                'success': False,
                'error': 'Invalid authentication token'
            }), 401
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        item_id = data.get('item_id')
        item_type = sanitize_input(data.get('item_type'))  # 'lost' or 'found'
        verification_details = sanitize_input(data.get('verification_details'))
        proof_images = []
        proof_video = None

        if request.files:
            if 'proof_images' in request.files:
                proof_images = request.files.getlist('proof_images')
            elif 'proof_media' in request.files:
                proof_images = request.files.getlist('proof_media')
            proof_video = request.files.get('proof_video')
        
        # Validate required fields
        if not item_id or not item_type:
            return jsonify({
                'success': False,
                'error': 'item_id and item_type are required'
            }), 400
        
        # Validate item_id
        is_valid, error = validate_integer(item_id, 'Item ID', min_value=1, required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # Validate item_type
        is_valid, error = validate_enum(item_type, 'Item Type', ['lost', 'found'], required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # Validate verification_details if provided
        if verification_details:
            is_valid, error = validate_string_field(
                verification_details, 'Verification Details', 
                min_length=1, max_length=2000, required=False
            )
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        # Verify the item exists (SQL injection protected by SQLAlchemy)
        item = None
        if item_type == 'lost':
            item = LostItem.query.get(item_id)
        elif item_type == 'found':
            item = FoundItem.query.get(item_id)
        
        if not item:
            return jsonify({
                'success': False,
                'error': f'{item_type.capitalize()} item not found'
            }), 404

        # Require at least one piece of proof media
        if not proof_images and not proof_video:
            return jsonify({
                'success': False,
                'error': 'Please provide at least one proof image or video'
            }), 400
        
        # Check if item is already claimed/closed
        if item.status in ['claimed', 'closed']:
            return jsonify({
                'success': False,
                'error': f'Item is already {item.status} and cannot be claimed'
            }), 400
        
        # Check if user already has a pending claim for this item (SQL injection protected)
        existing_claim = Claim.query.filter_by(
            item_id=item_id,
            item_type=item_type,
            claimer_id=claimer_id,
            status='pending'
        ).first()
        
        if existing_claim:
            return jsonify({
                'success': False,
                'error': 'You already have a pending claim for this item'
            }), 400
        
        # Create new claim
        claim = Claim(
            item_id=item_id,
            item_type=item_type,
            claimer_id=claimer_id,
            status='pending',
            verification_details=verification_details
        )
        
        db.session.add(claim)
        db.session.flush()

        primary_media_set = False

        for index, file in enumerate(proof_images or []):
            if not file:
                continue

            ok, upload = upload_media(
                file_stream=file,
                folder="lost_found_app/claims/images",
                resource_type="image"
            )
            if not ok:
                db.session.rollback()
                return jsonify({'success': False, 'error': f'Image upload failed: {upload}'}), 400

            media = ClaimMedia(
                claim_id=claim.id,
                media_type='image',
                url=upload['url'],
                preview_url=upload['preview_url'],
                public_id=upload['public_id'],
                format=upload['format'],
                is_primary=not primary_media_set
            )
            primary_media_set = True
            db.session.add(media)

        if proof_video:
            ok, upload = upload_media(
                file_stream=proof_video,
                folder="lost_found_app/claims/video",
                resource_type="video"
            )
            if not ok:
                db.session.rollback()
                return jsonify({'success': False, 'error': f'Video upload failed: {upload}'}), 400

            media = ClaimMedia(
                claim_id=claim.id,
                media_type='video',
                url=upload['url'],
                preview_url=upload['preview_url'],
                public_id=upload['public_id'],
                format=upload['format'],
                is_primary=not primary_media_set
            )
            primary_media_set = True
            db.session.add(media)

        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Claim created successfully',
            'data': {
                'claim': claim.to_dict()
            }
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Failed to create claim: {str(e)}'
        }), 500

@claims_bp.route('/<int:user_id>', methods=['GET'])
@limiter.limit("100 per hour")
def get_user_claims(user_id):
    """Get all claims for a specific user"""
    try:
        # Validate user_id
        is_valid, error = validate_integer(user_id, 'User ID', min_value=1, required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # Verify user exists (SQL injection protected by SQLAlchemy)
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Get and sanitize optional filter parameters
        status = sanitize_input(request.args.get('status'))
        item_type = sanitize_input(request.args.get('item_type'))
        
        # Validate status if provided
        if status:
            is_valid, error = validate_enum(
                status, 'Status', 
                ['pending', 'verified', 'returned', 'rejected'], 
                required=False
            )
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        # Validate item_type if provided
        if item_type:
            is_valid, error = validate_enum(item_type, 'Item Type', ['lost', 'found'], required=False)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        # Query claims for the user (SQL injection protected by SQLAlchemy)
        query = Claim.query.filter_by(claimer_id=user_id)
        
        # Apply filters
        if status:
            query = query.filter(Claim.status == status)
        if item_type:
            query = query.filter(Claim.item_type == item_type)
        
        # Order by most recent first
        claims = query.order_by(Claim.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'data': {
                'claims': [claim.to_dict() for claim in claims],
                'count': len(claims)
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get claims: {str(e)}'
        }), 500

@claims_bp.route('/admin', methods=['GET'])
@jwt_required()
@limiter.limit("50 per hour")
def get_all_claims():
    """Get all claims (admin only) with optional status filtering"""
    try:
        identity = get_jwt_identity()
        try:
            admin_id = int(identity)
        except (TypeError, ValueError):
            return jsonify({
                'success': False,
                'error': 'Invalid authentication token'
            }), 401

        admin_user = User.query.get(admin_id)

        if not admin_user or admin_user.role != 'admin':
            return jsonify({
                'success': False,
                'error': 'Access denied: admin privileges required'
            }), 403

        status = sanitize_input(request.args.get('status'))

        if status:
            is_valid, error = validate_enum(
                status,
                'Status',
                ['pending', 'verified', 'returned', 'rejected'],
                required=False
            )
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400

        query = Claim.query
        if status:
            query = query.filter(Claim.status == status)

        claims = query.order_by(Claim.created_at.desc()).all()

        return jsonify({
            'success': True,
            'data': {
                'claims': [claim.to_dict() for claim in claims],
                'count': len(claims)
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to fetch claims: {str(e)}'
        }), 500

@claims_bp.route('/<int:claim_id>/verify', methods=['PUT'])
@jwt_required()
@limiter.limit("30 per hour")
def verify_claim(claim_id):
    """Admin verification endpoint to verify/return a claim"""
    try:
        # Validate claim_id
        is_valid, error = validate_integer(claim_id, 'Claim ID', min_value=1, required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # Get admin user (SQL injection protected by SQLAlchemy)
        identity = get_jwt_identity()
        try:
            admin_id = int(identity)
        except (TypeError, ValueError):
            return jsonify({
                'success': False,
                'error': 'Invalid authentication token'
            }), 401

        admin_user = User.query.get(admin_id)
        
        if not admin_user:
            return jsonify({
                'success': False,
                'error': 'Admin user not found'
            }), 404
        if admin_user.role != 'admin':
            return jsonify({
                'success': False,
                'error': 'Access denied: admin privileges required'
            }), 403
        
        # Get the claim (SQL injection protected by SQLAlchemy)
        claim = Claim.query.get(claim_id)
        if not claim:
            return jsonify({
                'success': False,
                'error': 'Claim not found'
            }), 404
        
        data = request.get_json() or {}
        new_status = sanitize_input(data.get('status'))  # 'verified', 'returned', 'rejected'
        verification_details = sanitize_input(data.get('verification_details'))
        
        # Validate status
        is_valid, error = validate_enum(
            new_status, 'Status', 
            ['verified', 'returned', 'rejected'], 
            required=True
        )
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400

        if new_status == claim.status:
            return jsonify({
                'success': False,
                'error': f'Claim is already {claim.status}'
            }), 400

        allowed_transitions = {
            'pending': {'verified', 'returned', 'rejected'},
            'verified': {'returned'},
            'returned': set(),
            'rejected': set(),
        }

        current_status = claim.status
        if new_status not in allowed_transitions.get(current_status, set()):
            return jsonify({
                'success': False,
                'error': f'Cannot transition claim from {current_status} to {new_status}'
            }), 400
        
        # Validate verification_details if provided
        if verification_details:
            is_valid, error = validate_string_field(
                verification_details, 'Verification Details',
                min_length=1, max_length=2000, required=False
            )
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        # Update claim status
        claim.status = new_status
        if verification_details:
            claim.verification_details = verification_details
        claim.updated_at = datetime.utcnow()
        
        # Update the item status if verified
        if new_status == 'verified':
            item = claim.get_item()
            if item:
                item.status = 'claimed'
                item.updated_at = datetime.utcnow()
        elif new_status == 'returned':
            item = claim.get_item()
            if item:
                item.status = 'closed'
                item.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Claim {new_status} successfully',
            'data': {
                'claim': claim.to_dict()
            }
        }), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Failed to verify claim: {str(e)}'
        }), 500

@claims_bp.route('/<int:claim_id>', methods=['GET'])
@limiter.limit("100 per hour")
def get_claim(claim_id):
    """Get a specific claim by ID"""
    try:
        # Validate claim_id
        is_valid, error = validate_integer(claim_id, 'Claim ID', min_value=1, required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # SQL injection protected by SQLAlchemy
        claim = Claim.query.get(claim_id)
        
        if not claim:
            return jsonify({
                'success': False,
                'error': 'Claim not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'claim': claim.to_dict()
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get claim: {str(e)}'
        }), 500


@claims_bp.route('/<int:claim_id>/media', methods=['GET'])
@jwt_required()
@limiter.limit("50 per hour")
def get_claim_media(claim_id):
    """
    Admin-only endpoint to retrieve the full-resolution media for a claim's item.
    Returns blurred previews for non-admin access as a fallback (should not occur due to checks).
    """
    try:
        identity = get_jwt_identity()
        try:
            admin_id = int(identity)
        except (TypeError, ValueError):
            return jsonify({
                'success': False,
                'error': 'Invalid authentication token'
            }), 401

        admin_user = User.query.get(admin_id)
        if not admin_user or admin_user.role != 'admin':
            return jsonify({
                'success': False,
                'error': 'Access denied: admin privileges required'
            }), 403

        # Validate claim_id
        is_valid, error = validate_integer(claim_id, 'Claim ID', min_value=1, required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400

        claim = Claim.query.get(claim_id)
        if not claim:
            return jsonify({
                'success': False,
                'error': 'Claim not found'
            }), 404

        item = claim.get_item()
        if not item:
            return jsonify({
                'success': False,
                'error': 'Associated item not found'
            }), 404

        return jsonify({
            'success': True,
            'data': {
                'claim': claim.to_dict(include_secure_media=True),
                'item': item.to_dict(include_secure_media=True)
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to fetch claim media: {str(e)}'
        }), 500
