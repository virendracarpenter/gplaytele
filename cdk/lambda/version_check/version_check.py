"""
Version Check Lambda — Scrapes Google Play Store for current BGMI version.
If version differs from stored, triggers both downloads in parallel.
Downloads store their S3 keys in DynamoDB.
Only 32-bit triggers its upload. After 32-bit upload completes,
it chains to 64-bit upload (reads keys from DynamoDB).
This prevents AUTH_KEY_DUPLICATED from concurrent Telegram sessions.
"""

import json
import os

import boto3
from google_play_scraper import app as gplay_app

dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

VERSION_TABLE = os.environ["VERSION_TABLE"]
DOWNLOAD_32_FUNCTION_ARN = os.environ["DOWNLOAD_32_FUNCTION_ARN"]
DOWNLOAD_64_FUNCTION_ARN = os.environ["DOWNLOAD_64_FUNCTION_ARN"]
PACKAGE_NAME = os.environ["PACKAGE_NAME"]


def get_stored_version():
    table = dynamodb.Table(VERSION_TABLE)
    resp = table.get_item(Key={"variant": "current"})
    item = resp.get("Item")
    return item.get("version") if item else None


def store_version(version):
    table = dynamodb.Table(VERSION_TABLE)
    table.put_item(Item={"variant": "current", "version": version})


def get_play_store_version():
    result = gplay_app(PACKAGE_NAME, lang="en", country="in")
    return result.get("version")


def lambda_handler(event, context):
    print("=== BGMI Version Check ===")

    current_version = get_play_store_version()
    print(f"Play Store version: {current_version}")

    stored_version = get_stored_version()
    print(f"Stored version: {stored_version}")

    if current_version == stored_version:
        print("No new version. Skipping.")
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "No update", "version": current_version}),
        }

    print(f"New version detected! {stored_version} → {current_version}")
    store_version(current_version)

    # Trigger 64-bit download (skip_upload=True, just stores files in S3+DynamoDB)
    print(f"Invoking 64-bit download: {DOWNLOAD_64_FUNCTION_ARN}")
    lambda_client.invoke(
        FunctionName=DOWNLOAD_64_FUNCTION_ARN,
        InvocationType="Event",
        Payload=json.dumps({
            "variant": "64bit",
            "version": current_version,
            "skip_upload": True,
        }),
    )

    # Trigger 32-bit download (will trigger upload, which chains to 64-bit upload)
    print(f"Invoking 32-bit download: {DOWNLOAD_32_FUNCTION_ARN}")
    lambda_client.invoke(
        FunctionName=DOWNLOAD_32_FUNCTION_ARN,
        InvocationType="Event",
        Payload=json.dumps({
            "variant": "32bit",
            "version": current_version,
        }),
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "New version found, downloads triggered",
            "old_version": stored_version,
            "new_version": current_version,
        }),
    }
