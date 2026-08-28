import os
import re
import uuid

import boto3


AWS_REGION = os.getenv(
    "AWS_REGION",
    "us-east-2",
)

KNOWLEDGE_BUCKET = os.getenv(
    "DIAGLOB_KNOWLEDGE_BUCKET",
    "",
)


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
    )


def safe_filename(
    filename: str,
) -> str:
    cleaned = re.sub(
        r"[^A-Za-z0-9._-]+",
        "-",
        filename.strip(),
    )

    return cleaned or "document"


def build_knowledge_key(
    organization_id: int,
    knowledge_base_id: int,
    filename: str,
) -> str:
    safe_name = safe_filename(
        filename
    )

    document_id = str(
        uuid.uuid4()
    )

    return (
        f"organizations/"
        f"{organization_id}/"
        f"knowledge-bases/"
        f"{knowledge_base_id}/"
        f"documents/"
        f"{document_id}-"
        f"{safe_name}"
    )


def upload_knowledge_file(
    *,
    organization_id: int,
    knowledge_base_id: int,
    filename: str,
    content: bytes,
    content_type: str | None,
):
    if not KNOWLEDGE_BUCKET:
        raise RuntimeError(
            "DIAGLOB_KNOWLEDGE_BUCKET "
            "is not configured"
        )

    key = build_knowledge_key(
        organization_id,
        knowledge_base_id,
        filename,
    )

    extra_args = {}

    if content_type:
        extra_args[
            "ContentType"
        ] = content_type

    get_s3_client().put_object(
        Bucket=KNOWLEDGE_BUCKET,
        Key=key,
        Body=content,
        **extra_args,
    )

    return {
        "bucket": KNOWLEDGE_BUCKET,
        "key": key,
    }


def delete_knowledge_file(
    bucket: str,
    key: str,
):
    get_s3_client().delete_object(
        Bucket=bucket,
        Key=key,
    )
