"""
Version Check Lambda — Scrapes Google Play Store for current BGMI version.
If version differs from stored, triggers BOTH 32-bit and 64-bit download Lambdas.
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
    """Get the last known version from DynamoDB."""
    table = dynamodb.Table(VERSION_TABLE)
    resp = table.get_item(Key={"variant": "current"})
    item = resp.get("Item")
    return item.get("version") if item else None


def store_version(version):
    """Store the current version in DynamoDB."""
    table = dynamodb.Table(VERSION_TABLE)
    table.put_item(Item={"variant": "current", "version": version})


def get_play_store_version():
    """Fetch current version from Google Play Store."""
    result = gplay_app(PACKAGE_NAME, lang="en", country="in")
    return result.get("version")


def lambda_handler(event, context):
    print("=== BGMI Version Check ===")

    # Get current version from Play Store
    current_version = get_play_store_version()
    print(f"Play Store version: {current_version}")

    # Get stored version
    stored_version = get_stored_version()
    print(f"Stored version: {stored_version}")

    if current_version == stored_version:
        print("No new version. Skipping.")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "No update",
                "version": current_version,
            }),
        }

    print(f"New version detected! {stored_version} → {current_version}")

    # Update stored version
    store_version(current_version)

    # Trigger both download Lambdas
    for arn, variant in [
        (DOWNLOAD_32_FUNCTION_ARN, "32bit"),
        (DOWNLOAD_64_FUNCTION_ARN, "64bit"),
    ]:
        payload = {"variant": variant, "version": current_version}
        print(f"Invoking {variant} download: {arn}")
        lambda_client.invoke(
            FunctionName=arn,
            InvocationType="Event",
            Payload=json.dumps(payload),
        )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "New version found, both downloads triggered",
            "old_version": stored_version,
            "new_version": current_version,
        }),
    }
