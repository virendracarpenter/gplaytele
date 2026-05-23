#!/bin/bash
set -e

# Builds the Lambda layer with apkeep binary + Python dependencies.
# Uses Amazon Linux 2023 to match the Python 3.14 Lambda runtime.
#
# Run with:
#   docker run --rm -v $(pwd):/build -w /build amazonlinux:2023 bash layer/build-layer.sh
#
# After building, publish the layer:
#   aws lambda publish-layer-version \
#     --layer-name bgmi-deps \
#     --zip-file fileb://layer/lambda-layer.zip \
#     --compatible-runtimes python3.14 \
#     --compatible-architectures x86_64

echo "=== Installing build tools ==="
dnf install -y gcc gcc-c++ python3.11 python3.11-pip python3.11-devel openssl-devel zip perl-FindBin perl-File-Compare perl-IPC-Cmd

echo "=== Installing Rust ==="
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source ~/.cargo/env

echo "=== Building apkeep ==="
cargo install apkeep

echo "=== Creating layer structure ==="
mkdir -p /tmp/layer/bin
mkdir -p /tmp/layer/lib
mkdir -p /tmp/layer/python

# Copy apkeep binary
cp ~/.cargo/bin/apkeep /tmp/layer/bin/
chmod +x /tmp/layer/bin/apkeep

# Copy OpenSSL shared libraries
cp /usr/lib64/libssl.so.3 /tmp/layer/lib/
cp /usr/lib64/libcrypto.so.3 /tmp/layer/lib/

echo "=== Installing Python dependencies ==="
pip3.11 install pyrogram tgcrypto google-play-scraper -t /tmp/layer/python/

echo "=== Packaging layer ==="
cd /tmp/layer
zip -r /build/layer/lambda-layer.zip .

echo "=== Done! ==="
ls -lh /build/layer/lambda-layer.zip
echo ""
echo "Next steps:"
echo "  1. aws lambda publish-layer-version --layer-name bgmi-deps --zip-file fileb://layer/lambda-layer.zip --compatible-runtimes python3.14"
echo "  2. aws ssm put-parameter --name /bgmi/layer-arn --value <LAYER_ARN> --type String --overwrite"
