"""
Download Lambda — Downloads APK+OBB from Google Play via apkeep,
uploads files to S3, then triggers the Upload Lambda.
Only invoked when Version Check Lambda detects a new version.
"""

import json
import glob
import os
import subprocess

import boto3

ssm = boto3.client("ssm")
s3 = boto3.client("s3")
lambda_client = boto3.client("lambda")

DEVICE = os.environ["DEVICE"]
VARIANT = os.environ["VARIANT"]
PACKAGE = os.environ["PACKAGE_NAME"]
S3_BUCKET = os.environ["S3_BUCKET"]
UPLOAD_FUNCTION_ARN = os.environ["UPLOAD_FUNCTION_ARN"]

DOWNLOAD_DIR = "/tmp/pubg_files"


def get_secret(name):
    resp = ssm.get_parameter(Name=f"/bgmi/{name}", WithDecryption=True)
    return resp["Parameter"]["Value"]


def download_apk(google_email, aas_token):
    """Download APK+OBB using apkeep."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    cmd = [
        "/opt/bin/apkeep",
        "-a", PACKAGE,
        "-d", "google-play",
        "-o", f"device={DEVICE},locale=en_IN,include_additional_files=true",
        "-e", google_email,
        "-t", aas_token,
        DOWNLOAD_DIR,
    ]

    print(f"Running apkeep for {VARIANT} (device: {DEVICE})")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        raise RuntimeError(f"apkeep failed with code {result.returncode}")

    print(f"Download complete: {result.stdout}")


def upload_to_s3(files):
    """Upload downloaded files to S3 under variant prefix."""
    s3_keys = []
    for f in files:
        if os.path.isfile(f):
            key = f"{VARIANT}/{os.path.basename(f)}"
            print(f"Uploading {f} -> s3://{S3_BUCKET}/{key}")
            s3.upload_file(f, S3_BUCKET, key)
            s3_keys.append(key)
    return s3_keys


def lambda_handler(event, context):
    print(f"=== BGMI {VARIANT} Download ({DEVICE}) ===")
    print(f"Event: {json.dumps(event)}")

    version = event.get("version", "unknown")

    # Fetch credentials
    google_email = get_secret("google-email")
    aas_token = get_secret("aas-token")

    # Download APK + OBB
    download_apk(google_email, aas_token)

    # Find downloaded files
    files = glob.glob(f"{DOWNLOAD_DIR}/{PACKAGE}/*")
    if not files:
        raise FileNotFoundError(f"No files found in {DOWNLOAD_DIR}/{PACKAGE}/")

    # Verify APK exists
    apk_path = f"{DOWNLOAD_DIR}/{PACKAGE}/{PACKAGE}.apk"
    if not os.path.isfile(apk_path):
        raise FileNotFoundError(f"APK not found at {apk_path}")

    print(f"Downloaded: {[os.path.basename(f) for f in files]}")

    # Upload to S3
    s3_keys = upload_to_s3(files)

    # Trigger upload Lambda
    payload = {
        "variant": VARIANT,
        "s3_keys": s3_keys,
        "version": version,
    }

    print(f"Invoking upload Lambda: {UPLOAD_FUNCTION_ARN}")
    lambda_client.invoke(
        FunctionName=UPLOAD_FUNCTION_ARN,
        InvocationType="Event",
        Payload=json.dumps(payload),
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Download complete, upload triggered",
            "variant": VARIANT,
            "version": version,
            "s3_keys": s3_keys,
        }),
    }
