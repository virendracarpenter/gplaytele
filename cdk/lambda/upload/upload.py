"""
Upload Lambda — Downloads files from S3 and uploads them to Telegram.
Triggered asynchronously by the Download Lambda when a new version is detected.
"""

import asyncio
import json
import os

import boto3

ssm = boto3.client("ssm")
s3 = boto3.client("s3")

VARIANT = os.environ["VARIANT"]
CAPTION = os.environ["CAPTION"]
S3_BUCKET = os.environ["S3_BUCKET"]

TMP_DIR = "/tmp/upload"


def get_secret(name):
    resp = ssm.get_parameter(Name=f"/bgmi/{name}", WithDecryption=True)
    return resp["Parameter"]["Value"]


def download_from_s3(s3_keys):
    """Download files from S3 to /tmp."""
    os.makedirs(TMP_DIR, exist_ok=True)
    local_files = []

    for key in s3_keys:
        local_path = os.path.join(TMP_DIR, os.path.basename(key))
        print(f"Downloading s3://{S3_BUCKET}/{key} -> {local_path}")
        s3.download_file(S3_BUCKET, key, local_path)
        local_files.append(local_path)

    return local_files


async def upload_to_telegram(files, api_id, api_hash, session_string, chat_id):
    """Upload files to Telegram channel."""
    from pyrogram import Client

    app = Client(
        "upload_session",
        api_id=api_id,
        api_hash=api_hash,
        session_string=session_string,
        in_memory=True,
    )

    await app.start()
    print("Telegram client connected")

    for file_path in files:
        filename = os.path.basename(file_path)
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        print(f"Uploading {filename} ({size_mb:.1f} MB)...")

        try:
            await app.send_document(
                chat_id,
                file_path,
                caption=CAPTION,
                progress=lambda c, t: print(f"  {c * 100 / t:.1f}%"),
            )
            print(f"Uploaded: {filename}")
        except Exception as e:
            print(f"Failed to upload {filename}: {e}")
            raise

    await app.stop()
    print("All files uploaded successfully")


def lambda_handler(event, context):
    print(f"=== BGMI {VARIANT} Upload to Telegram ===")
    print(f"Event: {json.dumps(event)}")

    s3_keys = event["s3_keys"]
    version_hash = event.get("version_hash", "unknown")

    # Fetch Telegram credentials
    api_id = get_secret("api-id")
    api_hash = get_secret("api-hash")
    session_string = get_secret("tg-session-string")
    chat_id = get_secret("tg-chat-id")

    # Download from S3
    local_files = download_from_s3(s3_keys)
    print(f"Files ready for upload: {[os.path.basename(f) for f in local_files]}")

    # Upload to Telegram
    asyncio.run(
        upload_to_telegram(local_files, api_id, api_hash, session_string, chat_id)
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Upload complete",
            "variant": VARIANT,
            "version_hash": version_hash,
            "files": [os.path.basename(f) for f in local_files],
        }),
    }
