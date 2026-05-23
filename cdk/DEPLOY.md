# Deploy & Test Guide

## Prerequisites

- AWS CLI configured (`aws configure`)
- Docker installed (for building the Lambda layer)
- Python 3.11+
- Node.js (CDK requires it)
- AWS CDK CLI: `npm install -g aws-cdk`

---

## Step 1: Build the Lambda Layer

This compiles `apkeep` and bundles `pyrogram` + `tgcrypto` for Lambda.

```bash
cd cdk
docker run --rm -v $(pwd):/build -w /build amazonlinux:2023 bash layer/build-layer.sh
```

Verify the zip was created:
```bash
ls -lh layer/lambda-layer.zip
```

---

## Step 2: Publish the Layer to AWS

```bash
LAYER_ARN=$(aws lambda publish-layer-version \
  --layer-name bgmi-deps \
  --zip-file fileb://layer/lambda-layer.zip \
  --compatible-runtimes python3.11 \
  --compatible-architectures x86_64 \
  --query LayerVersionArn --output text)

echo "Layer ARN: $LAYER_ARN"

# Store it in SSM so CDK can reference it
aws ssm put-parameter --name "/bgmi/layer-arn" --value "$LAYER_ARN" --type String --overwrite
```

---

## Step 3: Store Secrets in SSM

```bash
aws ssm put-parameter --name "/bgmi/google-email" --value "your-email@gmail.com" --type SecureString
aws ssm put-parameter --name "/bgmi/aas-token" --value "your-aas-token" --type SecureString
aws ssm put-parameter --name "/bgmi/api-id" --value "12345678" --type SecureString
aws ssm put-parameter --name "/bgmi/api-hash" --value "your-api-hash" --type SecureString
aws ssm put-parameter --name "/bgmi/tg-session-string" --value "your-session-string" --type SecureString
aws ssm put-parameter --name "/bgmi/tg-chat-id" --value "-100xxxxxxxxxx" --type SecureString
```

Verify:
```bash
aws ssm get-parameters-by-path --path "/bgmi/" --query "Parameters[].Name"
```

---

## Step 4: Deploy the CDK Stack

```bash
cd cdk

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Bootstrap CDK (first time only, sets up CDK staging bucket)
cdk bootstrap

# Preview what will be created
cdk synth
cdk diff

# Deploy
cdk deploy
```

You'll see a list of IAM changes — type `y` to confirm.

---

## Step 5: Test Each Lambda Individually

### Test 1: Version Check (safe, no downloads)

```bash
# 64-bit
aws lambda invoke \
  --function-name bgmi-version-check-64bit \
  --log-type Tail \
  --query 'LogResult' \
  --output text response.json | base64 -d

cat response.json
```

Expected output:
```json
{"statusCode": 200, "body": "{\"message\": \"New version found, download triggered\", ...}"}
```

On first run it will always trigger download (no stored version yet).
On second run it should say "No update".

```bash
# 32-bit
aws lambda invoke \
  --function-name bgmi-version-check-32bit \
  --log-type Tail \
  --query 'LogResult' \
  --output text response.json | base64 -d

cat response.json
```

### Test 2: Download Lambda (downloads APK+OBB, uploads to S3)

```bash
# Invoke directly with a test event
aws lambda invoke \
  --function-name bgmi-download-64bit \
  --payload '{"variant": "64bit", "version": "test-manual"}' \
  --log-type Tail \
  --query 'LogResult' \
  --output text response.json | base64 -d

cat response.json
```

Verify files landed in S3:
```bash
aws s3 ls s3://bgmi-apk-<ACCOUNT_ID>-<REGION>/64bit/
```

### Test 3: Upload Lambda (reads from S3, sends to Telegram)

```bash
# Use the s3_keys from the download response
aws lambda invoke \
  --function-name bgmi-upload-64bit \
  --payload '{"variant": "64bit", "s3_keys": ["64bit/com.pubg.imobile.apk", "64bit/com.pubg.imobile.obb"], "version": "test"}' \
  --log-type Tail \
  --query 'LogResult' \
  --output text response.json | base64 -d

cat response.json
```

Check your Telegram channel — files should appear.

---

## Step 6: Verify the Full Chain (end-to-end)

Reset the stored version to force a full run:
```bash
aws dynamodb delete-item \
  --table-name bgmi-versions \
  --key '{"variant": {"S": "64bit"}}'
```

Then trigger the version check:
```bash
aws lambda invoke --function-name bgmi-version-check-64bit response.json
```

This should cascade: version check → download → upload → files in Telegram.

Monitor in real-time:
```bash
# Watch version check logs
aws logs tail /aws/lambda/bgmi-version-check-64bit --follow

# Watch download logs (in another terminal)
aws logs tail /aws/lambda/bgmi-download-64bit --follow

# Watch upload logs (in another terminal)
aws logs tail /aws/lambda/bgmi-upload-64bit --follow
```

---

## Step 7: Verify Cron is Working

Check the EventBridge rule:
```bash
aws events describe-rule --name bgmi-daily-check
```

List targets:
```bash
aws events list-targets-by-rule --rule bgmi-daily-check
```

---

## Troubleshooting

### Check Lambda logs
```bash
aws logs tail /aws/lambda/bgmi-version-check-64bit --since 1h
aws logs tail /aws/lambda/bgmi-download-64bit --since 1h
aws logs tail /aws/lambda/bgmi-upload-64bit --since 1h
```

### Check DynamoDB stored versions
```bash
aws dynamodb scan --table-name bgmi-versions
```

### Check S3 contents
```bash
aws s3 ls s3://bgmi-apk-<ACCOUNT_ID>-<REGION>/ --recursive
```

### Force re-run (clear stored version)
```bash
aws dynamodb delete-item --table-name bgmi-versions --key '{"variant": {"S": "64bit"}}'
aws dynamodb delete-item --table-name bgmi-versions --key '{"variant": {"S": "32bit"}}'
```

### Destroy everything
```bash
cdk destroy
```

---

## Updating Lambda Code

After changing Lambda code, redeploy:
```bash
cdk deploy
```

CDK detects code changes automatically and updates the functions.
