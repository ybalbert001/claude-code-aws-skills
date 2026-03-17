#!/usr/bin/env python3
"""Copy public ECR images to private ECR using AWS CodeBuild.

SageMaker cannot always pull from public ECR directly, so this script
copies the image to a private ECR repository via a CodeBuild build job.

Usage as module:
    from ecr_image_copier import ensure_private_image
    private_uri = ensure_private_image("public.ecr.aws/xxx/img:tag", "us-west-2")

Usage standalone:
    python ecr_image_copier.py --public-uri public.ecr.aws/xxx/img:tag --region us-west-2
"""

import argparse
import json
import sys
import time

CODEBUILD_PROJECT_NAME = "sglang-ecr-image-copy"
CODEBUILD_ROLE_NAME = "sglang-ecr-copy-codebuild-role"
DEFAULT_REPO_NAME = "sagemaker-sglang"

BUILDSPEC = """version: 0.2
phases:
  pre_build:
    commands:
      - echo "Logging into public ECR..."
      - aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
      - echo "Logging into private ECR..."
      - ACCOUNT_ID=$(echo $TARGET_IMAGE | cut -d. -f1)
      - REGION=$(echo $TARGET_IMAGE | cut -d. -f4)
      - aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
  build:
    commands:
      - echo "Pulling $SOURCE_IMAGE..."
      - docker pull $SOURCE_IMAGE
      - echo "Tagging as $TARGET_IMAGE..."
      - docker tag $SOURCE_IMAGE $TARGET_IMAGE
      - echo "Pushing $TARGET_IMAGE..."
      - docker push $TARGET_IMAGE
"""


def _get_boto3_clients(region):
    import boto3
    kwargs = {"region_name": region} if region else {}
    ecr = boto3.client("ecr", **kwargs)
    codebuild = boto3.client("codebuild", **kwargs)
    iam = boto3.client("iam")  # IAM is global
    sts = boto3.client("sts", **kwargs)
    return ecr, codebuild, iam, sts


def _parse_public_uri(public_uri):
    """Parse public ECR URI into components. Returns (image_without_tag, tag)."""
    if ":" in public_uri.split("/")[-1]:
        base, tag = public_uri.rsplit(":", 1)
    else:
        base, tag = public_uri, "latest"
    return base, tag


def _build_private_uri(account_id, region, repo_name, tag):
    return f"{account_id}.dkr.ecr.{region}.amazonaws.com/{repo_name}:{tag}"


def _check_image_exists(ecr, repo_name, tag):
    """Check if image already exists in private ECR. Returns True if exists."""
    try:
        ecr.describe_images(
            repositoryName=repo_name,
            imageIds=[{"imageTag": tag}]
        )
        return True
    except ecr.exceptions.ImageNotFoundException:
        return False
    except ecr.exceptions.RepositoryNotFoundException:
        return False


def _ensure_ecr_repo(ecr, repo_name):
    """Create ECR repository if it doesn't exist."""
    try:
        ecr.create_repository(repositoryName=repo_name)
        print(f"Created ECR repository: {repo_name}")
    except ecr.exceptions.RepositoryAlreadyExistsException:
        pass


def _verify_codebuild_role(iam):
    """Verify CodeBuild IAM role exists. Returns role ARN or raises error."""
    try:
        resp = iam.get_role(RoleName=CODEBUILD_ROLE_NAME)
        return resp["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        raise RuntimeError(
            f"IAM role '{CODEBUILD_ROLE_NAME}' not found. "
            f"Please create it first by running:\n"
            f"  bash scripts/setup_iam_roles.sh"
        )


def _ensure_codebuild_project(codebuild, role_arn):
    """Create CodeBuild project if it doesn't exist."""
    try:
        resp = codebuild.batch_get_projects(names=[CODEBUILD_PROJECT_NAME])
        if resp["projects"]:
            return
    except Exception:
        pass

    print(f"Creating CodeBuild project: {CODEBUILD_PROJECT_NAME}")
    codebuild.create_project(
        name=CODEBUILD_PROJECT_NAME,
        source={
            "type": "NO_SOURCE",
            "buildspec": BUILDSPEC,
        },
        artifacts={"type": "NO_ARTIFACTS"},
        environment={
            "type": "LINUX_CONTAINER",
            "computeType": "BUILD_GENERAL1_SMALL",
            "image": "aws/codebuild/amazonlinux2-x86_64-standard:5.0",
            "privilegedMode": True,
            "environmentVariables": [
                {"name": "SOURCE_IMAGE", "value": "placeholder", "type": "PLAINTEXT"},
                {"name": "TARGET_IMAGE", "value": "placeholder", "type": "PLAINTEXT"},
                {"name": "AWS_DEFAULT_REGION", "value": "placeholder", "type": "PLAINTEXT"},
            ],
        },
        serviceRole=role_arn,
        timeoutInMinutes=30,
    )


def _run_build(codebuild, source_image, target_image, region, timeout=600):
    """Start CodeBuild build and wait for completion. Timeout in seconds."""
    print(f"Starting CodeBuild: {source_image} -> {target_image}")
    resp = codebuild.start_build(
        projectName=CODEBUILD_PROJECT_NAME,
        environmentVariablesOverride=[
            {"name": "SOURCE_IMAGE", "value": source_image, "type": "PLAINTEXT"},
            {"name": "TARGET_IMAGE", "value": target_image, "type": "PLAINTEXT"},
            {"name": "AWS_DEFAULT_REGION", "value": region, "type": "PLAINTEXT"},
        ],
    )
    build_id = resp["build"]["id"]
    print(f"Build started: {build_id}")

    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            codebuild.stop_build(id=build_id)
            raise TimeoutError(
                f"CodeBuild timed out after {timeout}s. "
                f"Check logs: https://console.aws.amazon.com/codesuite/codebuild/projects/{CODEBUILD_PROJECT_NAME}/build/{build_id}"
            )

        resp = codebuild.batch_get_builds(ids=[build_id])
        build = resp["builds"][0]
        status = build["buildStatus"]

        if status == "SUCCEEDED":
            print("Image copy completed successfully.")
            return
        elif status in ("FAILED", "STOPPED", "FAULT", "TIMED_OUT"):
            phases = build.get("phases", [])
            failed_phase = next((p for p in phases if p.get("phaseStatus") == "FAILED"), None)
            detail = ""
            if failed_phase:
                contexts = failed_phase.get("contexts", [])
                if contexts:
                    detail = f" Phase: {failed_phase['phaseType']}, Message: {contexts[0].get('message', '')}"
            raise RuntimeError(
                f"CodeBuild failed with status: {status}.{detail} "
                f"Check logs: https://console.aws.amazon.com/codesuite/codebuild/projects/{CODEBUILD_PROJECT_NAME}/build/{build_id}"
            )

        print(f"  Build status: {status} ({int(elapsed)}s elapsed)")
        time.sleep(15)


def ensure_private_image(public_uri, region, repo_name=DEFAULT_REPO_NAME):
    """Ensure the public ECR image exists in a private ECR repo.

    Returns the private ECR image URI. If the image already exists in the
    private repo, returns immediately without starting a build.
    """
    ecr, codebuild, iam, sts = _get_boto3_clients(region)

    # Get account ID
    account_id = sts.get_caller_identity()["Account"]
    _, tag = _parse_public_uri(public_uri)
    private_uri = _build_private_uri(account_id, region, repo_name, tag)

    # Fast path: image already exists
    if _check_image_exists(ecr, repo_name, tag):
        print(f"Private image already exists: {private_uri}")
        return private_uri

    print(f"Image not found in private ECR. Copying via CodeBuild...")

    # Verify role exists (must be created manually via setup_iam_roles.sh)
    role_arn = _verify_codebuild_role(iam)

    # Setup infrastructure (idempotent)
    _ensure_ecr_repo(ecr, repo_name)
    _ensure_codebuild_project(codebuild, role_arn)

    # Run the build
    _run_build(codebuild, public_uri, private_uri, region)

    return private_uri


def main():
    parser = argparse.ArgumentParser(description="Copy public ECR image to private ECR via CodeBuild")
    parser.add_argument("--public-uri", required=True, help="Public ECR image URI")
    parser.add_argument("--region", required=True, help="AWS region for private ECR")
    parser.add_argument("--repo-name", default=DEFAULT_REPO_NAME, help=f"Private ECR repo name (default: {DEFAULT_REPO_NAME})")
    args = parser.parse_args()

    private_uri = ensure_private_image(args.public_uri, args.region, args.repo_name)
    print(json.dumps({"private_uri": private_uri}))


if __name__ == "__main__":
    main()
