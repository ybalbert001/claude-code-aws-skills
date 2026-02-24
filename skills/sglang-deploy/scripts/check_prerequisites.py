#!/usr/bin/env python3
"""
SGLang AWS Deployment - Prerequisites Checker

检查 EC2 实例是否满足 SGLang 部署的前提条件:
1. SSH 连接
2. GPU 配置
3. 磁盘空间
4. Python 环境
5. 网络连通性
"""

import json
import os
import sys
from pathlib import Path

from ssh_executor import SSHExecutor, test_connection
from instance_checker import InstanceChecker, print_check_report


def load_models_config():
    """加载模型配置"""
    script_dir = Path(__file__).parent
    models_file = script_dir.parent / "references" / "models.json"

    if models_file.exists():
        with open(models_file) as f:
            return json.load(f)
    return {"models": []}


def check_ssh_key_file(key_file: str) -> tuple[bool, str]:
    """检查 SSH 密钥文件"""
    key_file = os.path.expanduser(key_file)

    if not os.path.exists(key_file):
        return False, f"密钥文件不存在: {key_file}"

    # 检查文件权限
    mode = os.stat(key_file).st_mode & 0o777
    if mode > 0o600:
        return False, f"密钥文件权限过宽: {oct(mode)}，建议设置为 600"

    return True, f"密钥文件有效: {key_file}"


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="检查 EC2 实例是否满足 SGLang 部署条件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 检查实例
  python check_prerequisites.py --host 10.0.1.100 --key-file ~/.ssh/my-key.pem

  # 指定用户名
  python check_prerequisites.py --host 10.0.1.100 --username ubuntu --key-file ~/.ssh/my-key.pem

  # 输出 JSON 格式
  python check_prerequisites.py --host 10.0.1.100 --key-file ~/.ssh/my-key.pem --json

  # 列出可用模型
  python check_prerequisites.py --list-models
        """
    )

    parser.add_argument("--host", type=str, help="EC2 实例 IP 或域名")
    parser.add_argument("--username", type=str, default="ec2-user", help="SSH 用户名 (默认: ec2-user)")
    parser.add_argument("--key-file", type=str, help="SSH 私钥文件路径")
    parser.add_argument("--port", type=int, default=22, help="SSH 端口 (默认: 22)")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--list-models", action="store_true", help="列出可用模型")

    args = parser.parse_args()

    # 列出模型
    if args.list_models:
        config = load_models_config()
        print("\n可用模型:")
        print("-" * 60)
        for model in config.get("models", []):
            print(f"\n  {model['id']}")
            print(f"    名称: {model['name']}")
            print(f"    HuggingFace: {model['hf_model_id']}")
            print(f"    最小显存: {model['min_gpu_memory_gb']}GB")
            print(f"    推荐配置: {model['recommended_instance']} (TP={model['recommended_tp']})")
        print()
        return 0

    # 检查必需参数
    if not args.host:
        print("错误: 必须提供 --host 参数")
        print("使用 --help 查看帮助")
        return 1

    if not args.key_file:
        print("错误: 必须提供 --key-file 参数")
        print("使用 --help 查看帮助")
        return 1

    print("=" * 60)
    print("SGLang 部署前提条件检查")
    print("=" * 60)

    # 检查密钥文件
    print("\n检查 SSH 密钥文件...")
    key_ok, key_msg = check_ssh_key_file(args.key_file)
    print(f"  {'✓' if key_ok else '✗'} {key_msg}")

    if not key_ok:
        return 1

    # 测试 SSH 连接
    print(f"\n测试 SSH 连接: {args.username}@{args.host}:{args.port}")
    conn_ok, conn_msg = test_connection(args.host, args.username, args.key_file, args.port)
    print(f"  {'✓' if conn_ok else '✗'} {conn_msg}")

    if not conn_ok:
        print("\n无法连接到实例。请检查:")
        print("  - 实例是否正在运行")
        print("  - 安全组是否允许 SSH (端口 22)")
        print("  - 密钥文件是否正确")
        print("  - 用户名是否正确 (Amazon Linux: ec2-user, Ubuntu: ubuntu)")
        return 1

    # 运行完整检测
    print("\n运行实例检测...")
    try:
        with SSHExecutor(args.host, args.username, args.key_file, args.port) as executor:
            checker = InstanceChecker(executor)
            report = checker.run_all_checks()

            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print_check_report(report)

            # 返回状态
            if report["summary"]["ready_for_deployment"]:
                return 0
            else:
                return 1

    except Exception as e:
        print(f"\n✗ 检测失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
