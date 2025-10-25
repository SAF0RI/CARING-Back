import os
from typing import List

import boto3  # type: ignore
from botocore.client import Config  # type: ignore


def get_s3_client():
    region = os.getenv("AWS_REGION", "ap-northeast-2")
    kwargs = {
        "region_name": region,
        "config": Config(signature_version="s3v4"),
    }
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    session_token = os.getenv("AWS_SESSION_TOKEN")
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token
    return boto3.client("s3", **kwargs)


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


