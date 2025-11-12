from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import and_
from sqlalchemy.orm import foreign

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    enrollment_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default='user')
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    lost_items = db.relationship('LostItem', backref='user', lazy=True, foreign_keys='LostItem.user_id')
    found_items = db.relationship('FoundItem', backref='finder', lazy=True, foreign_keys='FoundItem.finder_id')
    claims = db.relationship('Claim', backref='claimer', lazy=True, foreign_keys='Claim.claimer_id')
    
    def set_password(self, password):
        """Hash and set the password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if the provided password matches the hash"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Convert user to dictionary"""
        return {
            'id': self.id,
            'enrollment_number': self.enrollment_number,
            'name': self.name,
            'email': self.email,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class LostItem(db.Model):
    __tablename__ = 'lost_items'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=True)
    location_lost = db.Column(db.String(200), nullable=True)
    date_lost = db.Column(db.Date, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, claimed, closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    media = db.relationship(
        'ItemMedia',
        primaryjoin="and_(foreign(ItemMedia.item_id)==LostItem.id, ItemMedia.item_type=='lost')",
        lazy='dynamic',
        cascade="all, delete-orphan"
    )

    # Get all claims for this lost item
    def get_claims(self):
        """Get all claims for this lost item"""
        return Claim.query.filter_by(item_id=self.id, item_type='lost').all()
    
    def to_dict(self, include_secure_media=False):
        """Convert lost item to dictionary"""
        media_items = []
        if self.media is not None:
            media_items = [
                media.to_dict(include_secure=include_secure_media)
                for media in self.media.order_by(
                    ItemMedia.is_primary.desc(),
                    ItemMedia.created_at.asc()
                ).all()
            ]

        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': self.user.name if self.user else None,
            'user_email': self.user.email if self.user else None,
            'title': self.title,
            'description': self.description,
            'category': self.category,
            'location_lost': self.location_lost,
            'date_lost': self.date_lost.isoformat() if self.date_lost else None,
            'image_url': self.image_url,
            'status': self.status,
            'item_type': 'lost',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'media': media_items
        }

class FoundItem(db.Model):
    __tablename__ = 'found_items'
    
    id = db.Column(db.Integer, primary_key=True)
    finder_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=True)
    location_found = db.Column(db.String(200), nullable=True)
    date_found = db.Column(db.Date, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), default='available', nullable=False)  # available, claimed, closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    media = db.relationship(
        'ItemMedia',
        primaryjoin="and_(foreign(ItemMedia.item_id)==FoundItem.id, ItemMedia.item_type=='found')",
        lazy='dynamic',
        cascade="all, delete-orphan"
    )

    # Get all claims for this found item
    def get_claims(self):
        """Get all claims for this found item"""
        return Claim.query.filter_by(item_id=self.id, item_type='found').all()
    
    def to_dict(self, include_secure_media=False):
        """Convert found item to dictionary"""
        media_items = []
        if self.media is not None:
            media_items = [
                media.to_dict(include_secure=include_secure_media)
                for media in self.media.order_by(
                    ItemMedia.is_primary.desc(),
                    ItemMedia.created_at.asc()
                ).all()
            ]

        return {
            'id': self.id,
            'finder_id': self.finder_id,
            'finder_name': self.finder.name if self.finder else None,
            'finder_email': self.finder.email if self.finder else None,
            'title': self.title,
            'description': self.description,
            'category': self.category,
            'location_found': self.location_found,
            'date_found': self.date_found.isoformat() if self.date_found else None,
            'image_url': self.image_url,
            'status': self.status,
            'item_type': 'found',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'media': media_items
        }


class ItemMedia(db.Model):
    __tablename__ = 'item_media'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, nullable=False, index=True)
    item_type = db.Column(db.String(10), nullable=False)  # 'lost' or 'found'
    media_type = db.Column(db.String(10), nullable=False)  # 'image' or 'video'
    url = db.Column(db.String(500), nullable=False)
    preview_url = db.Column(db.String(500), nullable=False)
    public_id = db.Column(db.String(255), nullable=True)
    format = db.Column(db.String(50), nullable=True)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self, include_secure=False):
        data = {
            'id': self.id,
            'media_type': self.media_type,
            'preview_url': self.preview_url,
            'is_primary': self.is_primary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'format': self.format,
        }
        if include_secure:
            data['url'] = self.url
        return data

class Claim(db.Model):
    __tablename__ = 'claims'
    
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, nullable=False, index=True)  # Can reference either LostItem or FoundItem
    item_type = db.Column(db.String(10), nullable=False)  # 'lost' or 'found'
    claimer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, verified, returned
    verification_details = db.Column(db.Text, nullable=True)
    claimed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    # Helper method to get the related item (LostItem or FoundItem)
    def get_item(self):
        """Get the related item (LostItem or FoundItem)"""
        if self.item_type == 'lost':
            return LostItem.query.get(self.item_id)
        elif self.item_type == 'found':
            return FoundItem.query.get(self.item_id)
        return None
    
    def to_dict(self, include_secure_media=False):
        """Convert claim to dictionary"""
        item = self.get_item()
        return {
            'id': self.id,
            'item_id': self.item_id,
            'item_type': self.item_type,
            'item_title': item.title if item else None,
            'claimer_id': self.claimer_id,
            'claimer_name': self.claimer.name if self.claimer else None,
            'claimer_email': self.claimer.email if self.claimer else None,
            'status': self.status,
            'verification_details': self.verification_details,
            'claimed_at': self.claimed_at.isoformat() if self.claimed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'item_image_url': item.image_url if item else None,
            'item_status': item.status if item else None,
            'item_media': [
                media.to_dict(include_secure=include_secure_media)
                for media in (item.media.order_by(
                    ItemMedia.is_primary.desc(),
                    ItemMedia.created_at.asc()
                ).all() if item and hasattr(item, 'media') and item.media is not None else [])
            ] if item else []
        }
