"""
Version Check Lambda — Scrapes Google Play Store for current app version.
If version differs from what's stored in DynamoDB, triggers the Download Lambda.
No heavy dependencies needed (just google-play-scraper + boto3).
"""

import json
import os

import boto3
from google_play_scraper import app as gplay_app

dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

VARIANT = os.environ["VARIANT"]
VERSION_TABLE = os.environ["VERSION_TABLE"]
DOWNLOAD_FUNCTION_ARN = os.environ["DOWNLOAD_FUNCTION_ARN"]
PACKAGE_NAME = os.environ["PACKAGE_NAME"]


def get_stored_version():
    """Get the last known version from DynamoDB."""
    table = dynamodb.Table(VERSION_TABLE)
    resp = table.get_item(Key={"variant": VARIANT})
    item = resp.get("Item")
    return item.get("version") if item else None


def store_version(version):
    """Store the current version in DynamoDB."""
    table = dynamodb.Table(VERSION_TABLE)
    table.update_item(
        Key={"variant": VARIANT},
        UpdateExpression="SET version = :v",
        ExpressionAttributeValues={":v": version},
    )


def get_play_store_version():
    """Fetch current version from Google Play Store (no auth needed)."""
    result = gplay_app(PACKAGE_NAME, lang="en", country="in")
    return result.get("version")


def lambda_handler(event, context):
    print(f"=== BGMI {VARIANT} Version Check ===")

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
                "variant": VARIANT,
                "version": current_version,
            }),
        }

    print(f"New version detected! {stored_version} → {current_version}")

    # Update stored version
    store_version(current_version)

    # Trigger download Lambda
    payload = {"variant": VARIANT, "version": current_version}
    print(f"Invoking download Lambda: {DOWNLOAD_FUNCTION_ARN}")

    lambda_client.invoke(
        FunctionName=DOWNLOAD_FUNCTION_ARN,
        InvocationType="Event",  # async
        Payload=json.dumps(payload),
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "New version found, download triggered",
            "variant": VARIANT,
            "old_version": stored_version,
            "new_version": current_version,
        }),
    }
