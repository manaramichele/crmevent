"""Object storage portabile (S3-compatible) per CRMEvent.

Versione per server esterno (Aruba): usa boto3 verso un endpoint S3-compatibile.
Mantiene invariata l'interfaccia pubblica usata da server.py:
  - put_object(path, data, content_type) -> {"path": <path>, "size": <int>}
  - get_object(path) -> (bytes, content_type)
Nessun fallback a integrations.emergentagent.com.
"""
import os
import boto3
from botocore.config import Config

APP_NAME = "crmevent"

S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")
S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY")
S3_BUCKET = os.environ.get("S3_BUCKET")
S3_REGION = os.environ.get("S3_REGION")

_client = None


def _s3():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY_ID,
            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
            region_name=S3_REGION,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
    return _client


def put_object(path: str, data: bytes, content_type: str) -> dict:
    _s3().put_object(Bucket=S3_BUCKET, Key=path, Body=data, ContentType=content_type)
    return {"path": path, "size": len(data)}


def get_object(path: str):
    obj = _s3().get_object(Bucket=S3_BUCKET, Key=path)
    return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")
