"""
Upload Lambda — Downloads files from S3 and uploads them to Telegram.
Triggered asynchronously by the Download Lambda when a new version is detected.
Uses pyrofork with tgcrypto-pyrofork for speed and uvloop for async performance.

Uploads run sequentially (not in parallel) to avoid AUTH_KEY_DUPLICATED errors
from Telegram when the same session is used simultaneously.
"""

import asyncio
import json
import os

import uvloop
import boto3

ssm = boto3.client("ssm")
s3 = boto3.client("s3")
lambda_client = boto3.client("lambda")

VARIANT = os.environ["VARIANT"]
CAPTION = os.environ["CAPTION"]
S3_BUCKET = os.environ["S3_BUCKET"]
# Optional: ARN of next upload Lambda to trigger after this one completes
NEXT_UPLOAD_ARN = os.environ.get("NEXT_UPLOAD_ARN", "")

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


async def upload_to_telegram(files, api_id, api_hash, session_string, chat_id, variant, version):
    """Upload files to Telegram channel with formatted captions."""
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

    bit_label = "32 BIT" if "32" in variant else "64 BIT"

    for file_path in files:
        filename = os.path.basename(file_path)
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        print(f"Uploading {filename} ({size_mb:.1f} MB)...")

        # Determine file type for caption
        if filename.endswith(".obb"):
            file_type = "OBB"
            # Extract SRC number from OBB filename (e.g., main.21120.com.pubg.imobile.obb)
            parts = filename.split(".")
            src_number = parts[1] if len(parts) > 1 else "N/A"
        else:
            file_type = "APK"
            src_number = None

        # Build caption
        caption = f"""PUBG BGMI 🇮🇳 {file_type} ⚡️
➖➖➖➖➖➖➖➖➖
🔸 VERSION {version} ✓
🔹 {bit_label} 🇮🇳 {file_type} ✓"""

        if src_number:
            caption += f"\n🔸 SRC ‌➲ [ {src_number} ]"

        caption += f"""
🔹 WITHOUT VPN ✓
🔸 ORIGINAL 🇮🇳 {file_type}
╔═.🔸.═════════╗
     @BGMI_apk
╚═════════.🔹.═╝"""

        try:
            await app.send_document(
                chat_id,
                file_path,
                caption=caption,
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
    version = event.get("version", "unknown")
    # Payload for the next upload in the chain (if any)
    next_payload = event.get("next_payload")

    # Fetch Telegram credentials
    api_id = get_secret("api-id")
    api_hash = get_secret("api-hash")
    session_string = get_secret("tg-session-string")
    chat_id = int(get_secret("tg-chat-id"))

    # Download from S3
    local_files = download_from_s3(s3_keys)
    print(f"Files ready for upload: {[os.path.basename(f) for f in local_files]}")

    # Upload to Telegram
    uvloop.install()
    asyncio.run(
        upload_to_telegram(local_files, api_id, api_hash, session_string, chat_id, VARIANT, version)
    )

    # Trigger next upload in chain (if configured)
    if NEXT_UPLOAD_ARN:
        # Read 64-bit S3 keys from DynamoDB
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(os.environ["VERSION_TABLE"])
        resp = table.get_item(Key={"variant": "64bit"})
        item = resp.get("Item")

        if item and "s3_keys" in item:
            next_payload = {
                "variant": "64bit",
                "s3_keys": item["s3_keys"],
                "version": version,
            }
            print(f"Triggering next upload: {NEXT_UPLOAD_ARN}")
            lambda_client.invoke(
                FunctionName=NEXT_UPLOAD_ARN,
                InvocationType="Event",
                Payload=json.dumps(next_payload),
            )
        else:
            print("64-bit S3 keys not yet available in DynamoDB — skipping chain")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Upload complete",
            "variant": VARIANT,
            "version": version,
            "files": [os.path.basename(f) for f in local_files],
        }),
    }
