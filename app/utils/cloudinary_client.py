import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
from flask import current_app


def init_cloudinary():
    """
    Initialize Cloudinary with credentials from the Flask app config.
    Safe to call multiple times; cloudinary maintains global config.
    """
    cloud_name = current_app.config.get('CLOUDINARY_CLOUD_NAME')
    api_key = current_app.config.get('CLOUDINARY_API_KEY')
    api_secret = current_app.config.get('CLOUDINARY_API_SECRET')

    if not cloud_name or not api_key or not api_secret:
        return False

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True
    )
    return True


def upload_media(
    file_stream,
    folder="lost_found_app/items",
    public_id=None,
    resource_type="image",
    eager_options=None
):
    """
    Upload an image or video to Cloudinary.
    Returns (True, {...}) on success or (False, error_message) on failure.
    """
    try:
        if not init_cloudinary():
            return False, "Cloudinary is not configured"

        options = {
            "folder": folder,
            "resource_type": resource_type,
            "unique_filename": True,
            "overwrite": False,
        }

        if eager_options:
            options["eager"] = eager_options

        if public_id:
            options["public_id"] = public_id

        result = cloudinary.uploader.upload(file_stream, **options)

        media_url = result.get("secure_url")
        public_id = result.get("public_id")
        format_ext = result.get("format")

        # Generate a blurred preview URL for protected viewing
        preview_url = media_url
        if public_id:
            if resource_type == "image":
                preview_url, _ = cloudinary_url(
                    public_id,
                    format=format_ext,
                    effect="blur:120",
                    quality=50,
                    secure=True,
                )
            elif resource_type == "video":
                # Generate a blurred poster image for video
                preview_url, _ = cloudinary_url(
                    public_id,
                    format="jpg",
                    resource_type="video",
                    effect="blur:200",
                    secure=True,
                )

        return True, {
            "url": media_url,
            "preview_url": preview_url,
            "public_id": public_id,
            "resource_type": resource_type,
            "format": format_ext,
        }
    except Exception as e:
        return False, str(e)


def upload_image(file_stream, folder="lost_found_app/items", public_id=None):
    """
    Backwards compatible helper for uploading images.
    """
    success, data = upload_media(
        file_stream=file_stream,
        folder=folder,
        public_id=public_id,
        resource_type="image",
    )
    if not success:
        return success, data
    return success, data.get("url")
