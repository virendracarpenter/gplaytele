#!/bin/bash
set -e

# Builds the Lambda layer with apkeep binary + Python dependencies.
# Run inside Docker with Amazon Linux 2023 (matches Lambda runtime):
#
#   docker run --rm -v $(pwd):/build -w /build amazonlinux:2023 bash layer/build-layer.sh
#
# After building, publish the layer:
#   aws lambda publish-layer-version \
#     --layer-name bgmi-deps \
#     --zip-file fileb://layer/lambda-layer.zip \
#     --compatible-runtimes python3.11 \
#     --compatible-architectures x86_64
#
# Then store the layer ARN in SSM:
#   aws ssm put-parameter --name "/bgmi/layer-arn" --value "arn:aws:lambda:..." --type String --overwrite

echo "=== Installing build tools ==="
dnf install -y gcc python3.11 python3.11-pip python3.11-devel openssl-devel zip

echo "=== Installing Rust ==="
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source ~/.cargo/env

echo "=== Building apkeep ==="
cargo install apkeep

echo "=== Creating layer structure ==="
mkdir -p /tmp/layer/bin
mkdir -p /tmp/layer/python

cp ~/.cargo/bin/apkeep /tmp/layer/bin/
chmod +x /tmp/layer/bin/apkeep

echo "=== Installing Python dependencies ==="
pip3.11 install pyrogram tgcrypto -t /tmp/layer/python/

echo "=== Packaging layer ==="
cd /tmp/layer
zip -r /build/layer/lambda-layer.zip .

echo "=== Done! ==="
echo "Layer zip: layer/lambda-layer.zip"
echo ""
echo "Next steps:"
echo "  1. aws lambda publish-layer-version --layer-name bgmi-deps --zip-file fileb://layer/lambda-layer.zip --compatible-runtimes python3.11"
echo "  2. aws ssm put-parameter --name /bgmi/layer-arn --value <LAYER_ARN> --type String --overwrite"
