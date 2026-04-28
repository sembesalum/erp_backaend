import mimetypes
import uuid
from pathlib import Path

import boto3
from django.conf import settings
from rest_framework.exceptions import ValidationError


def _get_s3_client():
    if not settings.AWS_STORAGE_BUCKET_NAME:
        raise ValidationError({"detail": "AWS bucket is not configured."})
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise ValidationError({"detail": "AWS credentials are not configured."})
    return boto3.client(
        "s3",
        region_name=settings.AWS_DEFAULT_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


def upload_request_image(uploaded_file, *, reference: str, image_kind: str) -> tuple[str, str]:
    ext = Path(uploaded_file.name or "").suffix.lower() or ".jpg"
    content_type = uploaded_file.content_type or mimetypes.guess_type(uploaded_file.name)[0] or "application/octet-stream"

    object_key = (
        f"{settings.AWS_UPLOAD_FOLDER}/mvfo/{reference}/{image_kind}/"
        f"{uuid.uuid4().hex}{ext}"
    )
    client = _get_s3_client()
    client.upload_fileobj(
        uploaded_file,
        settings.AWS_STORAGE_BUCKET_NAME,
        object_key,
        ExtraArgs={
            "ContentType": content_type,
        },
    )
    url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_DEFAULT_REGION}.amazonaws.com/{object_key}"
    return object_key, url
