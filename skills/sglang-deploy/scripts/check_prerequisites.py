#!/usr/bin/env python3
"""
SGLang AWS Deployment - Prerequisites Checker

检查 EC2 实例是否满足 SGLang 部署的前提条件。
"""

import json
import os
import sys

from ssh_utils import ssh_test
from instance_checker import InstanceChecker, print_check_report
from hf_api import fetch_trending_models


def check_ssh_key_file(key_file: str) -> tuple[bool, str]:
    """检查 SSH 密钥文件"""
    key_file = os.path.expanduser(key_file)

    if not os.path.exists(key_file):
        return False, f"密钥文件不存在: {key_file}"

    mode = os.stat(key_file).st_mode & 0o777
    if mode > 0o600:
        return False, f"密钥文件权限过宽: {oct(mode)}，建议设置为 600"

    return True, f"密钥文件有效: {key_file}"


def main():
    import argparse

    parser = argparse.ArgumentParser(description="检查 EC2 实例是否满足 SGLang 部署条件")
    parser.add_argument("--host", type=str, help="EC2 实例 IP 或域名")
    parser.add_argument("--username", type=str, default="ec2-user", help="SSH 用户名")
    parser.add_argument("--key-file", type=str, help="SSH 私钥文件路径")
    parser.add_argument("--port", type=int, default=22, help="SSH 端口")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--list-models", action="store_true", help="列出可用模型")

    args = parser.parse_args()

    if args.list_models:
        print("\n正在从 HuggingFace 获取 trending 32B+ 模型...")
        models = fetch_trending_models(limit=15, min_params_billions=32)
        if models:
            print(f"\n可用模型 ({len(models)} 个):")
            print("-" * 60)
            for i, model in enumerate(models, 1):
                print(f"\n  {i}. {model['name']}")
                print(f"     HuggingFace: {model['hf_model_id']}")
                print(f"     参数量: {model.get('params_billions', 'N/A')}B")
                print(f"     推荐配置: {model['recommended_instance']} (TP={model['recommended_tp']})")
        else:
            print("无法获取模型列表")
        print()
        return 0

    if not args.host:
        print("错误: 必须提供 --host 参数")
        return 1

    if not args.key_file:
        print("错误: 必须提供 --key-file 参数")
        return 1

    print("=" * 60)
    print("SGLang 部署前提条件检查")
    print("=" * 60)

    print("\n检查 SSH 密钥文件...")
    key_ok, key_msg = check_ssh_key_file(args.key_file)
    print(f"  {'✓' if key_ok else '✗'} {key_msg}")

    if not key_ok:
        return 1

    print(f"\n测试 SSH 连接: {args.username}@{args.host}:{args.port}")
    conn_ok, conn_msg = ssh_test(args.host, args.username, args.key_file, args.port)
    print(f"  {'✓' if conn_ok else '✗'} {conn_msg}")

    if not conn_ok:
        print("\n无法连接到实例。请检查:")
        print("  - 实例是否正在运行")
        print("  - 安全组是否允许 SSH")
        print("  - 密钥文件是否正确")
        return 1

    print("\n运行实例检测...")
    try:
        checker = InstanceChecker(args.host, args.username, args.key_file, args.port)
        report = checker.run_all_checks()

        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print_check_report(report)

        return 0 if report["summary"]["ready_for_deployment"] else 1

    except Exception as e:
        print(f"\n✗ 检测失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
