#!/bin/bash
# Setup IAM roles required for SGLang SageMaker Endpoint deployment.
#
# Creates 2 roles:
#   1. sglang-sagemaker-execution-role  - SageMaker execution role (AmazonSageMakerFullAccess)
#   2. sglang-ecr-copy-codebuild-role   - CodeBuild role for copying public ECR images to private ECR
#
# Usage:
#   bash setup_iam_roles.sh
#
# Prerequisites:
#   - AWS CLI configured with IAM permissions to create roles and policies

set -euo pipefail

SAGEMAKER_ROLE_NAME="sglang-sagemaker-execution-role"
CODEBUILD_ROLE_NAME="sglang-ecr-copy-codebuild-role"

echo "============================================"
echo "  SGLang SageMaker Endpoint - IAM Role Setup"
echo "============================================"
echo ""

# --- 1. SageMaker Execution Role ---

echo "[1/2] Creating SageMaker execution role: ${SAGEMAKER_ROLE_NAME}"

# Check if role already exists
if aws iam get-role --role-name "${SAGEMAKER_ROLE_NAME}" >/dev/null 2>&1; then
    SAGEMAKER_ROLE_ARN=$(aws iam get-role --role-name "${SAGEMAKER_ROLE_NAME}" --query 'Role.Arn' --output text)
    echo "  Role already exists: ${SAGEMAKER_ROLE_ARN}"
else
    # Create role with SageMaker trust policy
    SAGEMAKER_ROLE_ARN=$(aws iam create-role \
        --role-name "${SAGEMAKER_ROLE_NAME}" \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "sagemaker.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }' \
        --description "SageMaker execution role for SGLang endpoint deployment" \
        --query 'Role.Arn' --output text)

    # Attach AmazonSageMakerFullAccess managed policy
    aws iam attach-role-policy \
        --role-name "${SAGEMAKER_ROLE_NAME}" \
        --policy-arn "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"

    echo "  Created: ${SAGEMAKER_ROLE_ARN}"
    echo "  Attached: AmazonSageMakerFullAccess"
fi

echo ""

# --- 2. CodeBuild Service Role ---

echo "[2/2] Creating CodeBuild service role: ${CODEBUILD_ROLE_NAME}"

if aws iam get-role --role-name "${CODEBUILD_ROLE_NAME}" >/dev/null 2>&1; then
    CODEBUILD_ROLE_ARN=$(aws iam get-role --role-name "${CODEBUILD_ROLE_NAME}" --query 'Role.Arn' --output text)
    echo "  Role already exists: ${CODEBUILD_ROLE_ARN}"
else
    # Create role with CodeBuild trust policy
    CODEBUILD_ROLE_ARN=$(aws iam create-role \
        --role-name "${CODEBUILD_ROLE_NAME}" \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "codebuild.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }' \
        --description "CodeBuild role for copying public ECR images to private ECR" \
        --query 'Role.Arn' --output text)

    # Attach inline policy for ECR operations (least privilege)
    aws iam put-role-policy \
        --role-name "${CODEBUILD_ROLE_NAME}" \
        --policy-name "ecr-copy-policy" \
        --policy-document '{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "ECRAuth",
                    "Effect": "Allow",
                    "Action": "ecr:GetAuthorizationToken",
                    "Resource": "*"
                },
                {
                    "Sid": "ECRPrivateRepoReadWrite",
                    "Effect": "Allow",
                    "Action": [
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:GetDownloadUrlForLayer",
                        "ecr:BatchGetImage",
                        "ecr:PutImage",
                        "ecr:InitiateLayerUpload",
                        "ecr:UploadLayerPart",
                        "ecr:CompleteLayerUpload"
                    ],
                    "Resource": "arn:aws:ecr:*:*:repository/sagemaker-sglang"
                },
                {
                    "Sid": "ECRPublicRead",
                    "Effect": "Allow",
                    "Action": [
                        "ecr-public:GetAuthorizationToken",
                        "ecr-public:BatchCheckLayerAvailability",
                        "ecr-public:GetRepositoryPolicy",
                        "ecr-public:DescribeRepositories",
                        "ecr-public:DescribeImages",
                        "ecr-public:GetDownloadUrlForLayer",
                        "ecr-public:BatchGetImage"
                    ],
                    "Resource": "*"
                },
                {
                    "Sid": "STSToken",
                    "Effect": "Allow",
                    "Action": "sts:GetServiceBearerToken",
                    "Resource": "*"
                },
                {
                    "Sid": "CloudWatchLogs",
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ],
                    "Resource": "arn:aws:logs:*:*:log-group:/aws/codebuild/sglang-ecr-image-copy:*"
                }
            ]
        }'

    echo "  Created: ${CODEBUILD_ROLE_ARN}"
    echo "  Attached inline policy: ecr-copy-policy"
fi

echo ""
echo "============================================"
echo "  Setup Complete"
echo "============================================"
echo ""
echo "SageMaker Execution Role:"
echo "  Name: ${SAGEMAKER_ROLE_NAME}"
echo "  ARN:  ${SAGEMAKER_ROLE_ARN}"
echo ""
echo "CodeBuild Service Role:"
echo "  Name: ${CODEBUILD_ROLE_NAME}"
echo "  ARN:  ${CODEBUILD_ROLE_ARN}"
echo ""
echo "Usage:"
echo "  python scripts/sagemaker_endpoint.py --action deploy \\"
echo "      --model-id <MODEL_ID> \\"
echo "      --instance-type <INSTANCE_TYPE> \\"
echo "      --region <REGION> \\"
echo "      --role-arn ${SAGEMAKER_ROLE_ARN}"
