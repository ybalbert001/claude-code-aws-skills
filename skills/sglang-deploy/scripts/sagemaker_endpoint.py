#!/usr/bin/env python3
"""SGLang SageMaker Endpoint deployment tool.

Manages the full lifecycle: endpoint creation, waiting, testing, and cleanup.
Model is downloaded directly from HuggingFace at container startup.

Reference: https://github.com/ybalbert001/sglang-aws-kit/tree/main/sagemaker_endpoint_deploy
"""

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime

DEFAULT_CONTAINER = "public.ecr.aws/w4r2d0t2/sagemaker_endpoint/sglang:v0.5.9"

# Instance type -> GPU count mapping for TP inference
INSTANCE_GPU_MAP = {
    "ml.g5.xlarge": 1, "ml.g5.2xlarge": 1, "ml.g5.4xlarge": 1,
    "ml.g5.12xlarge": 4, "ml.g5.24xlarge": 4, "ml.g5.48xlarge": 8,
    "ml.g6.xlarge": 1, "ml.g6.2xlarge": 1, "ml.g6.4xlarge": 1,
    "ml.g6.12xlarge": 4, "ml.g6.24xlarge": 4, "ml.g6.48xlarge": 8,
    "ml.g6e.xlarge": 1, "ml.g6e.2xlarge": 1, "ml.g6e.4xlarge": 1,
    "ml.g6e.12xlarge": 4, "ml.g6e.24xlarge": 4, "ml.g6e.48xlarge": 8,
    "ml.p4d.24xlarge": 8, "ml.p4de.24xlarge": 8,
    "ml.p5.48xlarge": 8, "ml.p5e.48xlarge": 8,
}


def get_boto3_clients(region=None):
    import boto3
    kwargs = {"region_name": region} if region else {}
    sm = boto3.client("sagemaker", **kwargs)
    s3 = boto3.client("s3", **kwargs)
    runtime = boto3.client("runtime.sagemaker", **kwargs)
    sts = boto3.client("sts", **kwargs)
    return sm, s3, runtime, sts


def get_default_bucket(region=None):
    """Get SageMaker default bucket."""
    import boto3
    import sagemaker
    sess = sagemaker.Session(boto_session=boto3.Session(region_name=region) if region else None)
    return sess.default_bucket()


def get_execution_role():
    """Get SageMaker execution role."""
    import sagemaker
    return sagemaker.get_execution_role()


def model_name_sanitize(model_id):
    """Convert model ID to a safe name for AWS resources."""
    return model_id.replace("/", "-").replace(".", "-")


def action_deploy(args):
    """Create SageMaker Model, EndpointConfig, and Endpoint."""
    sm, s3, _, sts = get_boto3_clients(args.region)

    model_name = model_name_sanitize(args.model_id)
    container_uri = DEFAULT_CONTAINER

    # Determine TP
    tp = args.tp or INSTANCE_GPU_MAP.get(args.instance_type, 1)

    # Generate unique resource names
    timestamp = datetime.now().strftime("%m%d-%H%M")
    base_name = args.endpoint_name or f"sglang-{model_name[:40]}-{timestamp}"
    endpoint_model_name = base_name
    endpoint_config_name = base_name
    endpoint_name = base_name

    # Generate start.sh — download model from HuggingFace at container startup
    sglang_args = args.sglang_args if args.sglang_args else f"--tp {tp} --trust-remote-code --mem-fraction-static 0.85"
    token_line = f"    token='{args.hf_token}',\n" if args.hf_token else ""
    start_sh_content = f"""#!/bin/bash
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='{args.model_id}',
    local_dir='/opt/ml/modelfile/',
    max_workers=16,
    ignore_patterns=['*.msgpack', '*.h5', '*.ot', '*.gguf'],
    allow_patterns=['*.safetensors', '*.json', '*.txt', '*.model', '*.tiktoken'],
{token_line})
"

python3 -m sglang.launch_server \\
    --host 0.0.0.0 \\
    --port 8080 \\
    --model-path /opt/ml/modelfile/ \\
    {sglang_args}
"""

    # Package start.sh as tar.gz and upload to S3
    with tempfile.TemporaryDirectory() as tmpdir:
        code_dir = os.path.join(tmpdir, endpoint_model_name)
        os.makedirs(code_dir)
        start_sh_path = os.path.join(code_dir, "start.sh")
        with open(start_sh_path, "w") as f:
            f.write(start_sh_content)
        os.chmod(start_sh_path, 0o755)

        tar_path = os.path.join(tmpdir, f"{endpoint_model_name}.tar.gz")
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(code_dir, arcname=endpoint_model_name)

        s3_code_path = f"s3://{args.s3_bucket}/endpoint_code/sglang_byoc/{endpoint_model_name}.tar.gz"
        subprocess.run(["aws", "s3", "cp", tar_path, s3_code_path], check=True)

    # Create Model
    print(f"Creating model: {endpoint_model_name}")
    sm.create_model(
        ModelName=endpoint_model_name,
        PrimaryContainer={
            "Image": container_uri,
            "ModelDataUrl": s3_code_path,
        },
        ExecutionRoleArn=args.role_arn,
    )

    # Create Endpoint Config
    print(f"Creating endpoint config: {endpoint_config_name}")
    production_variant = {
        "VariantName": "AllTraffic",
        "ModelName": endpoint_model_name,
        "InitialInstanceCount": 1,
        "InstanceType": args.instance_type,
        "InitialVariantWeight": 1.0,
        "ContainerStartupHealthCheckTimeoutInSeconds": 1000,
        "InferenceAmiVersion": "al2-ami-sagemaker-inference-gpu-3-1",
    }
    if args.capacity_reservation_arn:
        production_variant["CapacityReservationConfig"] = {
            "MlReservationArn": args.capacity_reservation_arn,
            "CapacityReservationPreference": "capacity-reservations-only",
        }
    sm.create_endpoint_config(
        EndpointConfigName=endpoint_config_name,
        ProductionVariants=[production_variant],
    )

    # Create Endpoint
    print(f"Creating endpoint: {endpoint_name}")
    sm.create_endpoint(
        EndpointName=endpoint_name,
        EndpointConfigName=endpoint_config_name,
    )

    result = {
        "status": "creating",
        "endpoint_name": endpoint_name,
        "endpoint_config_name": endpoint_config_name,
        "model_name": endpoint_model_name,
        "instance_type": args.instance_type,
        "model_id": args.model_id,
        "tp": tp,
        "container": container_uri,
    }
    if args.capacity_reservation_arn:
        result["capacity_reservation_arn"] = args.capacity_reservation_arn
    print(json.dumps(result, indent=2))


def action_wait(args):
    """Wait for endpoint to become InService."""
    sm, _, _, _ = get_boto3_clients(args.region)
    endpoint_name = args.endpoint_name

    print(f"Waiting for endpoint {endpoint_name}...")
    while True:
        resp = sm.describe_endpoint(EndpointName=endpoint_name)
        status = resp["EndpointStatus"]
        now = datetime.now().strftime("%Y%m%d-%H:%M:%S")
        print(f"{now} status: {status}")

        if status == "InService":
            print(json.dumps({"status": "InService", "endpoint_name": endpoint_name}))
            return
        elif status == "Failed":
            reason = resp.get("FailureReason", "unknown")
            print(json.dumps({"status": "Failed", "reason": reason}), file=sys.stderr)
            sys.exit(1)

        time.sleep(60)


def action_test(args):
    """Test endpoint with a simple chat completion request."""
    _, _, runtime, _ = get_boto3_clients(args.region)
    endpoint_name = args.endpoint_name

    payload = {
        "messages": [{"role": "user", "content": "Hello! Tell me a joke."}],
        "max_tokens": 256,
        "stream": False,
    }

    print(f"Testing endpoint {endpoint_name}...")
    response = runtime.invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Body=json.dumps(payload),
    )

    result = json.loads(response["Body"].read())
    print(json.dumps(result, indent=2, ensure_ascii=False))


def action_delete(args):
    """Delete endpoint, endpoint config, and model."""
    sm, _, _, _ = get_boto3_clients(args.region)
    endpoint_name = args.endpoint_name

    # Get config and model names from endpoint
    try:
        ep = sm.describe_endpoint(EndpointName=endpoint_name)
        config_name = ep["EndpointConfigName"]
    except Exception:
        config_name = endpoint_name

    try:
        cfg = sm.describe_endpoint_config(EndpointConfigName=config_name)
        model_name = cfg["ProductionVariants"][0]["ModelName"]
    except Exception:
        model_name = endpoint_name

    # Delete in order
    for name, fn in [
        ("Endpoint", lambda: sm.delete_endpoint(EndpointName=endpoint_name)),
        ("EndpointConfig", lambda: sm.delete_endpoint_config(EndpointConfigName=config_name)),
        ("Model", lambda: sm.delete_model(ModelName=model_name)),
    ]:
        try:
            fn()
            print(f"Deleted {name}: {endpoint_name}")
        except Exception as e:
            print(f"Skip {name} deletion: {e}")

    print(json.dumps({"status": "deleted", "endpoint_name": endpoint_name}))


def main():
    parser = argparse.ArgumentParser(description="SGLang SageMaker Endpoint deployment tool")
    parser.add_argument("--action", required=True,
                        choices=["deploy", "wait", "test", "delete"],
                        help="Action to perform")
    parser.add_argument("--model-id", help="HuggingFace model ID")
    parser.add_argument("--instance-type", default="ml.g6.2xlarge",
                        help="SageMaker instance type (default: ml.g6.2xlarge)")
    parser.add_argument("--role-arn", help="SageMaker execution role ARN")
    parser.add_argument("--s3-bucket", help="S3 bucket for start.sh artifact (default: SageMaker default bucket)")
    parser.add_argument("--sglang-version", default="v0.5.9",
                        help="SGLang version tag (default: v0.5.9)")
    parser.add_argument("--endpoint-name", help="Endpoint name (auto-generated if omitted)")
    parser.add_argument("--tp", type=int, help="Tensor parallelism (auto from instance type)")
    parser.add_argument("--hf-token", help="HuggingFace token for gated models")
    parser.add_argument("--capacity-reservation-arn",
                        help="Flexible Training Plan (FTP) capacity reservation ARN")
    parser.add_argument("--sglang-args", default="",
                        help="SGLang launch args (replaces defaults; e.g. '--tp 4 --chat-template chatml --mem-fraction-static 0.8')")
    parser.add_argument("--region", help="AWS region")

    args = parser.parse_args()

    # Auto-detect defaults for S3 bucket and IAM role
    if not args.s3_bucket and args.action == "deploy":
        args.s3_bucket = get_default_bucket(args.region)
        print(f"Using default S3 bucket: {args.s3_bucket}")

    if not args.role_arn and args.action == "deploy":
        try:
            args.role_arn = get_execution_role()
            print(f"Using auto-detected IAM role: {args.role_arn}")
        except Exception:
            parser.error("--role-arn is required (auto-detection failed, not running on SageMaker)")

    actions = {
        "deploy": action_deploy,
        "wait": action_wait,
        "test": action_test,
        "delete": action_delete,
    }

    # Validate required args
    if args.action == "deploy" and not args.model_id:
        parser.error("--model-id is required for this action")
    if args.action in ("wait", "test", "delete") and not args.endpoint_name:
        parser.error("--endpoint-name is required for this action")

    actions[args.action](args)


if __name__ == "__main__":
    main()
