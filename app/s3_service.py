import os
from typing import List

import boto3  # type: ignore
from botocore.client import Config  # type: ignore


def get_s3_client():
    region = os.getenv("AWS_REGION", "ap-northeast-2")
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4"),
    )


def upload_fileobj(bucket: str, key: str, fileobj) -> str:
    s3 = get_s3_client()
    s3.upload_fileobj(fileobj, bucket, key)
    return key


def list_bucket_objects(bucket: str, prefix: str = "") -> List[str]:
    s3 = get_s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    keys: List[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            keys.append(obj["Key"]) 
    return keys


