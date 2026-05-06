#!/usr/bin/env python3
"""Create a Spot EC2 instance via argparse arguments (designed for LLM invocation)."""

import argparse
import sys

import boto3


VALID_INSTANCE_TYPES = [
    "p5en.48xlarge",
    "p6-b300.48xlarge",
    "p6-b200.48xlarge",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create a Spot EC2 instance on AWS.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--region",
        default="us-west-2",
        help="AWS region (default: us-west-2 / PDX)",
    )
    parser.add_argument(
        "--instance-type",
        required=True,
        choices=VALID_INSTANCE_TYPES,
        help="EC2 instance type. Valid choices:\n  " + "\n  ".join(VALID_INSTANCE_TYPES),
    )
    parser.add_argument(
        "--ami",
        default="ami-0563479679ac2e7a6",
        help="AMI ID (default: ami-0563479679ac2e7a6)",
    )
    parser.add_argument(
        "--key-pair",
        default="yuanbo",
        help="Key pair name (default: yuanbo)",
    )
    parser.add_argument(
        "--storage-gb",
        type=int,
        default=2000,
        help="Root volume size in GB (default: 2000)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Instance Name tag (default: spot-{instance-type})",
    )
    return parser.parse_args()


def create_spot_instance(args):
    ec2 = boto3.client("ec2", region_name=args.region)
    name = args.name or f"spot-{args.instance_type}"

    print(f"Creating Spot instance:")
    print(f"  Region:        {args.region}")
    print(f"  Instance type: {args.instance_type}")
    print(f"  AMI:           {args.ami}")
    print(f"  Key Pair:      {args.key_pair}")
    print(f"  Storage:       {args.storage_gb} GB gp3")
    print(f"  Name:          {name}")
    print(f"  Purchasing:    Spot (one-time)")
    print(f"  Capacity Res:  None")

    try:
        response = ec2.run_instances(
            ImageId=args.ami,
            InstanceType=args.instance_type,
            KeyName=args.key_pair,
            MinCount=1,
            MaxCount=1,
            InstanceMarketOptions={
                "MarketType": "spot",
                "SpotOptions": {
                    "SpotInstanceType": "one-time",
                },
            },
            CapacityReservationSpecification={
                "CapacityReservationPreference": "none",
            },
            BlockDeviceMappings=[
                {
                    "DeviceName": "/dev/xvda",
                    "Ebs": {
                        "VolumeSize": args.storage_gb,
                        "VolumeType": "gp3",
                        "DeleteOnTermination": True,
                    },
                }
            ],
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": name},
                    ],
                }
            ],
        )
    except Exception as e:
        print(f"ERROR: Failed to create instance: {e}", file=sys.stderr)
        sys.exit(1)

    instance_id = response["Instances"][0]["InstanceId"]
    print(f"\nInstance launched: {instance_id}")
    print("Waiting for running state...")

    try:
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id])
    except Exception as e:
        print(f"ERROR: Instance {instance_id} failed to reach running state: {e}", file=sys.stderr)
        sys.exit(1)

    desc = ec2.describe_instances(InstanceIds=[instance_id])
    instance = desc["Reservations"][0]["Instances"][0]
    public_ip = instance.get("PublicIpAddress", "N/A")
    private_ip = instance.get("PrivateIpAddress", "N/A")

    print(f"\nSUCCESS: Instance is running")
    print(f"  Instance ID: {instance_id}")
    print(f"  Public IP:   {public_ip}")
    print(f"  Private IP:  {private_ip}")
    if public_ip != "N/A":
        print(f"  SSH:         ssh -i ~/.ssh/{args.key_pair}.pem ubuntu@{public_ip}")


def main():
    args = parse_args()
    create_spot_instance(args)


if __name__ == "__main__":
    main()
