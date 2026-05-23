from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    Size,
    CfnOutput,
    aws_lambda as _lambda,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_ssm as ssm,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
)
from constructs import Construct
import os


class BgmiDownloaderStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # --- SSM Parameters (secrets) ---
        # params = {
        #     "google-email": "Google Play account email",
        #     "aas-token": "Google Play AAS token",
        #     "api-id": "Telegram API ID",
        #     "api-hash": "Telegram API hash",
        #     "tg-session-string": "Telegram session string",
        #     "tg-chat-id": "Telegram chat ID for uploads",
        # }

        # for name, description in params.items():
        #     ssm.StringParameter(
        #         self,
        #         f"Param-{name}",
        #         parameter_name=f"/bgmi/{name}",
        #         string_value="PLACEHOLDER",
        #         description=description,
        #     )

        # --- SSM Parameters ---
        # Secrets are created manually via CLI (not managed by CDK):
        #   aws ssm put-parameter --name "/bgmi/google-email" --value "..." --type SecureString
        #   aws ssm put-parameter --name "/bgmi/aas-token" --value "..." --type SecureString
        #   aws ssm put-parameter --name "/bgmi/api-id" --value "..." --type SecureString
        #   aws ssm put-parameter --name "/bgmi/api-hash" --value "..." --type SecureString
        #   aws ssm put-parameter --name "/bgmi/tg-session-string" --value "..." --type SecureString
        #   aws ssm put-parameter --name "/bgmi/tg-chat-id" --value "..." --type SecureString

        # --- DynamoDB table for version tracking ---
        version_table = dynamodb.Table(
            self,
            "VersionTable",
            table_name="bgmi-versions",
            partition_key=dynamodb.Attribute(
                name="variant", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # --- S3 bucket for intermediate APK/OBB storage ---
        bucket = s3.Bucket(
            self,
            "ApkBucket",
            bucket_name=f"bgmi-apk-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(expiration=Duration.days(3)),
            ],
        )

        # --- Lambda Layer (apkeep + pyrogram, built separately) ---
        deps_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "DepsLayer",
            ssm.StringParameter.value_for_string_parameter(self, "/bgmi/layer-arn"),
        )

        # --- Shared environment ---
        common_env = {
            "VERSION_TABLE": version_table.table_name,
            "S3_BUCKET": bucket.bucket_name,
            "PACKAGE_NAME": "com.pubg.imobile",
        }

        # --- Single Version Check Lambda (both variants share same version) ---
        version_check = _lambda.Function(
            self,
            "VersionCheck",
            function_name="bgmi-version-check",
            runtime=_lambda.Runtime.PYTHON_3_14,
            handler="version_check.lambda_handler",
            code=_lambda.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../lambda/version_check")
            ),
            layers=[deps_layer],
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={**common_env},
        )

        # --- Download Lambdas (heavy, uses apkeep layer) ---
        download_32 = _lambda.Function(
            self,
            "Download32bit",
            function_name="bgmi-download-32bit",
            runtime=_lambda.Runtime.PYTHON_3_14,
            handler="download.lambda_handler",
            code=_lambda.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../lambda/download")
            ),
            layers=[deps_layer],
            timeout=Duration.minutes(15),
            memory_size=1024,
            ephemeral_storage_size=Size.gibibytes(10),
            environment={**common_env, "DEVICE": "sm_j5_prime", "VARIANT": "32bit"},
        )

        download_64 = _lambda.Function(
            self,
            "Download64bit",
            function_name="bgmi-download-64bit",
            runtime=_lambda.Runtime.PYTHON_3_14,
            handler="download.lambda_handler",
            code=_lambda.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../lambda/download")
            ),
            layers=[deps_layer],
            timeout=Duration.minutes(15),
            memory_size=1024,
            ephemeral_storage_size=Size.gibibytes(10),
            environment={**common_env, "DEVICE": "px_9a", "VARIANT": "64bit"},
        )

        # --- Upload Lambdas (reads from S3, uploads to Telegram) ---
        upload_32 = _lambda.Function(
            self,
            "Upload32bit",
            function_name="bgmi-upload-32bit",
            runtime=_lambda.Runtime.PYTHON_3_14,
            handler="upload.lambda_handler",
            code=_lambda.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../lambda/upload")
            ),
            layers=[deps_layer],
            timeout=Duration.minutes(15),
            memory_size=1024,
            ephemeral_storage_size=Size.gibibytes(10),
            environment={
                **common_env,
                "VARIANT": "32bit",
                "CAPTION": "BGMI 32-bit APK/OBB",
            },
        )

        upload_64 = _lambda.Function(
            self,
            "Upload64bit",
            function_name="bgmi-upload-64bit",
            runtime=_lambda.Runtime.PYTHON_3_14,
            handler="upload.lambda_handler",
            code=_lambda.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../lambda/upload")
            ),
            layers=[deps_layer],
            timeout=Duration.minutes(15),
            memory_size=1024,
            ephemeral_storage_size=Size.gibibytes(10),
            environment={
                **common_env,
                "VARIANT": "64bit",
                "CAPTION": "BGMI 64-bit APK/OBB",
            },
        )

        # --- Permissions ---
        # Version check needs DynamoDB + invoke both download lambdas
        version_table.grant_read_write_data(version_check)
        download_32.grant_invoke(version_check)
        download_64.grant_invoke(version_check)

        # Download lambdas need S3 + SSM + invoke upload
        for fn in [download_32, download_64]:
            version_table.grant_read_write_data(fn)
            bucket.grant_read_write(fn)
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["ssm:GetParameter"],
                    resources=[
                        f"arn:aws:ssm:{self.region}:{self.account}:parameter/bgmi/*"
                    ],
                )
            )

        # Upload lambdas need S3 + SSM
        for fn in [upload_32, upload_64]:
            bucket.grant_read(fn)
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["ssm:GetParameter"],
                    resources=[
                        f"arn:aws:ssm:{self.region}:{self.account}:parameter/bgmi/*"
                    ],
                )
            )

        # Chain: version_check → download → upload
        upload_32.grant_invoke(download_32)
        upload_64.grant_invoke(download_64)

        # Pass function ARNs via environment
        version_check.add_environment("DOWNLOAD_32_FUNCTION_ARN", download_32.function_arn)
        version_check.add_environment("DOWNLOAD_64_FUNCTION_ARN", download_64.function_arn)
        download_32.add_environment("UPLOAD_FUNCTION_ARN", upload_32.function_arn)
        download_64.add_environment("UPLOAD_FUNCTION_ARN", upload_64.function_arn)

        # --- EventBridge cron (daily at midnight UTC) ---
        rule = events.Rule(
            self,
            "DailyCron",
            rule_name="bgmi-daily-check",
            schedule=events.Schedule.cron(minute="0", hour="0"),
        )
        rule.add_target(targets.LambdaFunction(version_check))

        # --- Outputs ---
        CfnOutput(self, "BucketName", value=bucket.bucket_name)
        CfnOutput(self, "VersionTableName", value=version_table.table_name)
