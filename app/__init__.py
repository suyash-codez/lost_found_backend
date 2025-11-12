from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.config import Config

db = SQLAlchemy()
jwt = JWTManager()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"],
    storage_uri="memory://",
    enabled=True
)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    jwt.init_app(app)
    CORS(app)
    
    # Initialize rate limiter
    if app.config.get('RATELIMIT_ENABLED', True):
        limiter.init_app(app)
        if app.config.get('RATELIMIT_STORAGE_URL'):
            limiter.storage_uri = app.config.get('RATELIMIT_STORAGE_URL')
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.items import items_bp
    from app.routes.claims import claims_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(items_bp, url_prefix='/api/items')
    app.register_blueprint(claims_bp, url_prefix='/api/claims')
    
    # Initialize database connection and create tables
    with app.app_context():
        try:
            # Test database connection
            db.engine.connect()
            print("✅ Database connection successful!")
            
            # Create all tables if they don't exist
            db.create_all()
            print("✅ Database tables verified/created successfully!")
            
        except Exception as e:
            # Database connection failed - show helpful message but don't crash
            error_msg = str(e)
            if "Access denied" in error_msg or "password" in error_msg.lower():
                print("⚠️  Warning: Database connection failed - Invalid credentials or database not configured.")
                print("   The app will continue running, but database operations will fail.")
                print("   To fix: Update your .env file with correct database credentials.")
            elif "Unknown database" in error_msg or "doesn't exist" in error_msg.lower():
                print("⚠️  Warning: Database does not exist.")
                print(f"   Please create the database: CREATE DATABASE {app.config.get('DB_NAME', 'lost_found_db')};")
            elif "Can't connect" in error_msg or "Connection refused" in error_msg:
                print("⚠️  Warning: Cannot connect to MySQL server.")
                print("   Please ensure MySQL is running and check DB_HOST and DB_PORT in .env file.")
            else:
                print(f"⚠️  Warning: Database connection error: {error_msg}")
                print("   The app will continue running, but database operations will fail.")
            print("   This is OK for development - configure your database when ready.\n")
    
    return app

