from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, limiter
from app.models import LostItem, FoundItem, User, ItemMedia
from datetime import datetime
from sqlalchemy import or_
from app.utils.validators import (
    validate_string_field, validate_date_format, validate_url,
    validate_integer, sanitize_input, validate_enum
)
from app.utils.cloudinary_client import upload_media

items_bp = Blueprint('items', __name__)

# Lost Items Routes

@items_bp.route('/lost', methods=['POST'])
@jwt_required()
@limiter.limit("20 per hour")
def report_lost_item():
    """Report a lost item"""
    try:
        # Support both JSON and multipart form-data
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form.to_dict()
        else:
            data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        # Get user_id from request or JWT token
        user_id = data.get('user_id') or get_jwt_identity()
        
        # Sanitize and validate inputs
        title = sanitize_input(data.get('title'))
        description = sanitize_input(data.get('description'))
        category = sanitize_input(data.get('category'))
        location = sanitize_input(data.get('location'))
        date = data.get('date')
        image_url = sanitize_input(data.get('image_url'))
        image_files = []
        video_file = None

        if request.files:
            if 'images' in request.files:
                image_files = request.files.getlist('images')
            elif 'image' in request.files:
                image_files = [request.files.get('image')]
            video_file = request.files.get('video')
        
        # Validate required fields
        is_valid, error = validate_string_field(title, 'Title', min_length=1, max_length=200, required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # Validate user_id
        is_valid, error = validate_integer(user_id, 'User ID', min_value=1, required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # Validate optional fields
        if description:
            is_valid, error = validate_string_field(description, 'Description', min_length=1, max_length=2000, required=False)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        if category:
            is_valid, error = validate_string_field(category, 'Category', min_length=1, max_length=50, required=False)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        if location:
            is_valid, error = validate_string_field(location, 'Location', min_length=1, max_length=200, required=False)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        if date:
            is_valid, error = validate_date_format(date)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        if image_url:
            is_valid, error = validate_url(image_url)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        # Verify user exists (SQL injection protected by SQLAlchemy)
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Parse date if provided
        date_lost = None
        if date:
            try:
                date_lost = datetime.strptime(date, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid date format. Use YYYY-MM-DD'
                }), 400
        
        # Create lost item
        lost_item = LostItem(
            user_id=user_id,
            title=title,
            description=description,
            category=category,
            location_lost=location,
            date_lost=date_lost,
            image_url=None,
            status='pending'
        )
        
        db.session.add(lost_item)
        db.session.flush()

        primary_image_url = None

        # Handle uploaded image files
        for index, file in enumerate(image_files):
            if not file:
                continue

            ok, data = upload_media(
                file_stream=file,
                folder="lost_found_app/lost_items/images",
                resource_type="image"
            )
            if not ok:
                db.session.rollback()
                return jsonify({'success': False, 'error': f'Image upload failed: {data}'}), 400

            media = ItemMedia(
                item_id=lost_item.id,
                item_type='lost',
                media_type='image',
                url=data['url'],
                preview_url=data['preview_url'],
                public_id=data['public_id'],
                format=data['format'],
                is_primary=index == 0
            )
            db.session.add(media)

            if index == 0:
                primary_image_url = data['url']

        # Handle existing image URL (fallback for legacy clients)
        if image_url and not image_files:
            primary_image_url = image_url
            media = ItemMedia(
                item_id=lost_item.id,
                item_type='lost',
                media_type='image',
                url=image_url,
                preview_url=image_url,
                is_primary=True
            )
            db.session.add(media)

        # Handle optional video upload
        if video_file:
            ok, data = upload_media(
                file_stream=video_file,
                folder="lost_found_app/lost_items/video",
                resource_type="video"
            )
            if not ok:
                db.session.rollback()
                return jsonify({'success': False, 'error': f'Video upload failed: {data}'}), 400

            media = ItemMedia(
                item_id=lost_item.id,
                item_type='lost',
                media_type='video',
                url=data['url'],
                preview_url=data['preview_url'],
                public_id=data['public_id'],
                format=data['format'],
                is_primary=False
            )
            db.session.add(media)

        lost_item.image_url = primary_image_url
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Lost item reported successfully',
            'data': {
                'item': lost_item.to_dict()
            }
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Failed to report lost item: {str(e)}'
        }), 500

@items_bp.route('/lost', methods=['GET'])
@limiter.limit("100 per hour")
def get_lost_items():
    """Get all lost items with optional filters"""
    try:
        # Get and sanitize filter parameters
        status = sanitize_input(request.args.get('status'))
        category = sanitize_input(request.args.get('category'))
        location = sanitize_input(request.args.get('location'))
        keyword = sanitize_input(request.args.get('keyword'))
        user_id = request.args.get('user_id', type=int)
        
        # Validate status if provided
        if status:
            is_valid, error = validate_enum(status, 'Status', ['pending', 'claimed', 'closed'], required=False)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        # Validate user_id if provided
        if user_id:
            is_valid, error = validate_integer(user_id, 'User ID', min_value=1, required=False)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        # Build query (SQL injection protected by SQLAlchemy ORM)
        query = LostItem.query
        
        if status:
            query = query.filter(LostItem.status == status)
        if category:
            query = query.filter(LostItem.category.ilike(f'%{category}%'))
        if location:
            query = query.filter(LostItem.location_lost.ilike(f'%{location}%'))
        if user_id:
            query = query.filter(LostItem.user_id == user_id)
        if keyword:
            # Search in title and description (SQL injection protected)
            query = query.filter(
                or_(
                    LostItem.title.ilike(f'%{keyword}%'),
                    LostItem.description.ilike(f'%{keyword}%')
                )
            )
        
        # Order by most recent first
        lost_items = query.order_by(LostItem.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'data': {
                'items': [item.to_dict() for item in lost_items],
                'count': len(lost_items)
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get lost items: {str(e)}'
        }), 500

@items_bp.route('/lost/<int:item_id>', methods=['GET'])
@limiter.limit("100 per hour")
def get_lost_item(item_id):
    """Get a specific lost item by ID"""
    try:
        # Validate item_id
        is_valid, error = validate_integer(item_id, 'Item ID', min_value=1, required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # SQL injection protected by SQLAlchemy
        lost_item = LostItem.query.get(item_id)
        
        if not lost_item:
            return jsonify({
                'success': False,
                'error': 'Lost item not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'item': lost_item.to_dict()
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get lost item: {str(e)}'
        }), 500

# Found Items Routes

@items_bp.route('/found', methods=['POST'])
@jwt_required()
@limiter.limit("20 per hour")
def report_found_item():
    """Report a found item"""
    try:
        # Support both JSON and multipart form-data
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form.to_dict()
        else:
            data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        # Get finder_id from request or JWT token
        finder_id = data.get('finder_id') or get_jwt_identity()
        
        # Sanitize and validate inputs
        title = sanitize_input(data.get('title'))
        description = sanitize_input(data.get('description'))
        category = sanitize_input(data.get('category'))
        location = sanitize_input(data.get('location'))
        date = data.get('date')
        image_url = sanitize_input(data.get('image_url'))
        image_files = []
        video_file = None

        if request.files:
            if 'images' in request.files:
                image_files = request.files.getlist('images')
            elif 'image' in request.files:
                image_files = [request.files.get('image')]
            video_file = request.files.get('video')
        
        # Validate required fields
        is_valid, error = validate_string_field(title, 'Title', min_length=1, max_length=200, required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # Validate finder_id
        is_valid, error = validate_integer(finder_id, 'Finder ID', min_value=1, required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # Validate optional fields
        if description:
            is_valid, error = validate_string_field(description, 'Description', min_length=1, max_length=2000, required=False)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        if category:
            is_valid, error = validate_string_field(category, 'Category', min_length=1, max_length=50, required=False)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        if location:
            is_valid, error = validate_string_field(location, 'Location', min_length=1, max_length=200, required=False)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        if date:
            is_valid, error = validate_date_format(date)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        if image_url:
            is_valid, error = validate_url(image_url)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        # Verify user exists (SQL injection protected by SQLAlchemy)
        user = User.query.get(finder_id)
        if not user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Parse date if provided
        date_found = None
        if date:
            try:
                date_found = datetime.strptime(date, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid date format. Use YYYY-MM-DD'
                }), 400
        
        # Create found item
        found_item = FoundItem(
            finder_id=finder_id,
            title=title,
            description=description,
            category=category,
            location_found=location,
            date_found=date_found,
            image_url=None,
            status='available'
        )
        
        db.session.add(found_item)
        db.session.flush()

        primary_image_url = None

        for index, file in enumerate(image_files):
            if not file:
                continue

            ok, data = upload_media(
                file_stream=file,
                folder="lost_found_app/found_items/images",
                resource_type="image"
            )
            if not ok:
                db.session.rollback()
                return jsonify({'success': False, 'error': f'Image upload failed: {data}'}), 400

            media = ItemMedia(
                item_id=found_item.id,
                item_type='found',
                media_type='image',
                url=data['url'],
                preview_url=data['preview_url'],
                public_id=data['public_id'],
                format=data['format'],
                is_primary=index == 0
            )
            db.session.add(media)

            if index == 0:
                primary_image_url = data['url']

        if image_url and not image_files:
            primary_image_url = image_url
            media = ItemMedia(
                item_id=found_item.id,
                item_type='found',
                media_type='image',
                url=image_url,
                preview_url=image_url,
                is_primary=True
            )
            db.session.add(media)

        if video_file:
            ok, data = upload_media(
                file_stream=video_file,
                folder="lost_found_app/found_items/video",
                resource_type="video"
            )
            if not ok:
                db.session.rollback()
                return jsonify({'success': False, 'error': f'Video upload failed: {data}'}), 400

            media = ItemMedia(
                item_id=found_item.id,
                item_type='found',
                media_type='video',
                url=data['url'],
                preview_url=data['preview_url'],
                public_id=data['public_id'],
                format=data['format'],
                is_primary=False
            )
            db.session.add(media)

        found_item.image_url = primary_image_url
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Found item reported successfully',
            'data': {
                'item': found_item.to_dict()
            }
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Failed to report found item: {str(e)}'
        }), 500

@items_bp.route('/found', methods=['GET'])
@limiter.limit("100 per hour")
def get_found_items():
    """Get all found items with optional filters (category, location, keyword)"""
    try:
        # Get and sanitize filter parameters
        status = sanitize_input(request.args.get('status'))
        category = sanitize_input(request.args.get('category'))
        location = sanitize_input(request.args.get('location'))
        keyword = sanitize_input(request.args.get('keyword'))
        finder_id = request.args.get('finder_id', type=int)
        
        # Validate status if provided
        if status:
            is_valid, error = validate_enum(status, 'Status', ['available', 'claimed', 'closed'], required=False)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        # Validate finder_id if provided
        if finder_id:
            is_valid, error = validate_integer(finder_id, 'Finder ID', min_value=1, required=False)
            if not is_valid:
                return jsonify({'success': False, 'error': error}), 400
        
        # Build query (SQL injection protected by SQLAlchemy ORM)
        query = FoundItem.query
        
        if status:
            query = query.filter(FoundItem.status == status)
        if category:
            query = query.filter(FoundItem.category.ilike(f'%{category}%'))
        if location:
            query = query.filter(FoundItem.location_found.ilike(f'%{location}%'))
        if finder_id:
            query = query.filter(FoundItem.finder_id == finder_id)
        if keyword:
            # Search in title and description (SQL injection protected)
            query = query.filter(
                or_(
                    FoundItem.title.ilike(f'%{keyword}%'),
                    FoundItem.description.ilike(f'%{keyword}%')
                )
            )
        
        # Order by most recent first
        found_items = query.order_by(FoundItem.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'data': {
                'items': [item.to_dict() for item in found_items],
                'count': len(found_items)
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get found items: {str(e)}'
        }), 500

@items_bp.route('/found/<int:item_id>', methods=['GET'])
@limiter.limit("100 per hour")
def get_found_item(item_id):
    """Get a specific found item by ID"""
    try:
        # Validate item_id
        is_valid, error = validate_integer(item_id, 'Item ID', min_value=1, required=True)
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 400
        
        # SQL injection protected by SQLAlchemy
        found_item = FoundItem.query.get(item_id)
        
        if not found_item:
            return jsonify({
                'success': False,
                'error': 'Found item not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'item': found_item.to_dict()
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get found item: {str(e)}'
        }), 500
