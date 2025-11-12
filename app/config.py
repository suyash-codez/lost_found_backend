import os
from datetime import timedelta
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load .env only for LOCAL development
load_dotenv()


class Config:
    # ✅ Flask secret keys
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback_secret_key')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'fallback_jwt_key')

    # ✅ Read ALL DB variables directly from environment (Railway sets these)
    DB_HOST = os.environ.get('DB_HOST')
    DB_PORT = os.environ.get('DB_PORT', 3306)
    DB_USER = os.environ.get('DB_USER')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_NAME = os.environ.get('DB_NAME')

    # ✅ Encode username/password properly
    encoded_user = quote_plus(DB_USER) if DB_USER else ""
    encoded_password = quote_plus(DB_PASSWORD) if DB_PASSWORD else ""

    # ✅ Build SQLAlchemy database URI dynamically
    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{encoded_user}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    # ✅ SQLAlchemy settings
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
        'connect_args': {
            'charset': 'utf8mb4',
            'connect_timeout': 10,
            'read_timeout': 30,
            'write_timeout': 30
        }
    }

    # ✅ JWT expiry
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_ALGORITHM = 'HS256'

    # ✅ Rate limiting (Railway compatible)
    RATELIMIT_ENABLED = os.environ.get('RATELIMIT_ENABLED', 'True').lower() == 'true'
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'memory://')

    # ✅ Cloudinary (Optional)
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

    # ✅ Admin configuration
    ADMIN_EMAILS = [
        email.strip().lower()
        for email in os.environ.get('ADMIN_EMAILS', '').split(',')
        if email.strip()
    ]
    ADMIN_ENROLLMENTS = [
        enrollment.strip().lower()
        for enrollment in os.environ.get('ADMIN_ENROLLMENTS', '').split(',')
        if enrollment.strip()
    ]