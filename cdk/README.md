# BGMI Downloader — AWS CDK (Python)

Automated pipeline that downloads BGMI APK+OBB from Google Play and uploads to Telegram, with version tracking.

## Architecture

```
EventBridge (daily cron)
    ├── bgmi-version-check-32bit (Lambda, ~5s)
    │       ├── Scrapes Play Store for current version
    │       ├── Compares with DynamoDB
    │       ├── If new → triggers download Lambda
    │       └── bgmi-download-32bit (Lambda, ~10 min)
    │               ├── Downloads APK+OBB via apkeep
    │               ├── Uploads to S3
    │               └── bgmi-upload-32bit (Lambda, ~10 min)
    │                       └── Downloads from S3 → uploads to Telegram
    └── bgmi-version-check-64bit (Lambda, ~5s)
            └── Same flow, different device profile
```

- Version check is lightweight (no apkeep needed, just scrapes Play Store)
- Download only happens when a new version is detected
- S3 is intermediate storage (auto-expires after 3 days)
- DynamoDB tracks version per variant
- SSM Parameter Store holds all secrets

## Setup

### 1. Build the Lambda layer (apkeep + pyrogram)

```bash
cd cdk
docker run --rm -v $(pwd):/build -w /build amazonlinux:2023 bash layer/build-layer.sh
```

### 2. Publish the layer and store ARN

```bash
LAYER_ARN=$(aws lambda publish-layer-version \
  --layer-name bgmi-deps \
  --zip-file fileb://layer/lambda-layer.zip \
  --compatible-runtimes python3.11 \
  --compatible-architectures x86_64 \
  --query LayerVersionArn --output text)

aws ssm put-parameter --name "/bgmi/layer-arn" --value "$LAYER_ARN" --type String --overwrite
```

### 3. Store secrets in SSM

```bash
aws ssm put-parameter --name "/bgmi/google-email" --value "YOUR_EMAIL" --type SecureString
aws ssm put-parameter --name "/bgmi/aas-token" --value "YOUR_TOKEN" --type SecureString
aws ssm put-parameter --name "/bgmi/api-id" --value "YOUR_API_ID" --type SecureString
aws ssm put-parameter --name "/bgmi/api-hash" --value "YOUR_API_HASH" --type SecureString
aws ssm put-parameter --name "/bgmi/tg-session-string" --value "YOUR_SESSION" --type SecureString
aws ssm put-parameter --name "/bgmi/tg-chat-id" --value "YOUR_CHAT_ID" --type SecureString
```

### 4. Deploy the stack

```bash
cd cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cdk bootstrap   # first time only
cdk deploy
```

### 5. Test manually

```bash
# Test version check (lightweight, safe to run anytime)
aws lambda invoke --function-name bgmi-version-check-64bit /dev/stdout
aws lambda invoke --function-name bgmi-version-check-32bit /dev/stdout
```

## Cost estimate

| Service | Monthly cost |
|---------|-------------|
| Lambda version checks (2 × 30s/day) | < $0.01 |
| Lambda download+upload (only on new version) | ~$0.10/update |
| DynamoDB (2 items, pay-per-request) | < $0.01 |
| S3 (1-2 GB, 3-day lifecycle) | < $0.05 |
| SSM Parameters | Free |
| EventBridge | Free |
| **Total** | **< $0.20/month** |
