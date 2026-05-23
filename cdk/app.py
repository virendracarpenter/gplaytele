#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stacks.bgmi_stack import BgmiDownloaderStack

app = cdk.App()

BgmiDownloaderStack(
    app,
    "BgmiDownloaderStack",
    env=cdk.Environment(
        region=os.environ.get("CDK_DEFAULT_REGION", "ap-south-1"),
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    ),
)

app.synth()
