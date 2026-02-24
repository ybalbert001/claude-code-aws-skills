#!/usr/bin/env python3
"""
SGLang Cleanup Script

通过 SSH 清理 EC2 实例上的 SGLang 部署。
"""

import sys
from ssh_utils import ssh_run, ssh_test


def stop_sglang_service(host: str, user: str, key: str, port: int) -> bool:
    """停止 SGLang 服务"""
    print("\n[1/4] 停止 SGLang 服务...")

    ssh_run(host, user, key, "systemctl stop sglang 2>/dev/null || true", port)
    ssh_run(host, user, key, "systemctl disable sglang 2>/dev/null || true", port)
    ssh_run(host, user, key, "rm -f /etc/systemd/system/sglang.service", port)
    ssh_run(host, user, key, "systemctl daemon-reload", port)

    success, stdout, _ = ssh_run(host, user, key, "pgrep -f 'sglang.launch_server'", port)
    if success and stdout.strip():
        print("  发现残留进程，强制终止...")
        ssh_run(host, user, key, "pkill -9 -f 'sglang.launch_server'", port)

    print("✓ SGLang 服务已停止")
    return True


def uninstall_sglang(host: str, user: str, key: str, port: int) -> bool:
    """卸载 SGLang"""
    print("\n[2/4] 卸载 SGLang...")

    success, _, _ = ssh_run(host, user, key, "python3 -c 'import sglang' 2>/dev/null", port)
    if not success:
        print("  SGLang 未安装，跳过")
        return True

    ssh_run(host, user, key, "pip uninstall -y sglang 2>/dev/null || true", port)
    print("✓ SGLang 已卸载")
    return True


def stop_monitoring(host: str, user: str, key: str, port: int) -> bool:
    """停止监控组件"""
    print("\n[3/4] 停止监控组件...")

    success, stdout, _ = ssh_run(host, user, key, "test -f /opt/monitoring/docker-compose.yml && echo 'exists'", port)
    if not success or "exists" not in stdout:
        print("  监控组件未安装，跳过")
        return True

    ssh_run(host, user, key, "cd /opt/monitoring && docker-compose down 2>/dev/null || true", port)
    print("✓ 监控组件已停止")
    return True


def cleanup_files(host: str, user: str, key: str, port: int) -> bool:
    """清理配置文件"""
    print("\n[4/4] 清理配置文件...")
    ssh_run(host, user, key, "rm -rf /opt/monitoring", port)
    print("✓ 配置文件已清理")
    return True


def interactive_cleanup(args):
    """交互式/非交互式清理流程

    当提供 --force 参数时，将以非交互式模式运行。
    """
    print("=" * 60)
    print("SGLang 清理工具")
    print("=" * 60)

    non_interactive = args.force

    # 检查必需参数
    if not args.host:
        if non_interactive:
            print("错误: 非交互式模式需要 --host 参数")
            return 1
        args.host = input("\n请输入 EC2 实例 IP 或域名: ").strip()
        if not args.host:
            print("错误: 必须提供主机地址")
            return 1

    if not args.key_file:
        if non_interactive:
            print("错误: 非交互式模式需要 --key-file 参数")
            return 1
        args.key_file = input("SSH 私钥文件路径: ").strip()
        if not args.key_file:
            print("错误: 必须提供 SSH 私钥文件")
            return 1

    user = args.username or "ec2-user"
    port = args.port or 22

    print(f"\n目标实例: {args.host}")
    print(f"用户名: {user}")

    if non_interactive:
        print("\n--force 模式，自动确认清理...")
    else:
        confirm = input("\n确认清理? 这将停止 SGLang 服务并删除配置 [y/N]: ").strip().lower()
        if confirm != 'y':
            print("清理取消。")
            return 1

    try:
        success, msg = ssh_test(args.host, user, args.key_file, port)
        if not success:
            print(f"\n✗ SSH 连接失败: {msg}")
            return 1

        print(f"\n✓ 已连接到 {args.host}")

        stop_sglang_service(args.host, user, args.key_file, port)

        if args.uninstall:
            uninstall_sglang(args.host, user, args.key_file, port)

        stop_monitoring(args.host, user, args.key_file, port)
        cleanup_files(args.host, user, args.key_file, port)

        print("\n" + "=" * 60)
        print("✓ 清理完成!")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n✗ 清理失败: {e}")
        return 1


def main():
    import argparse

    parser = argparse.ArgumentParser(description="清理 EC2 实例上的 SGLang 部署")
    parser.add_argument("--host", type=str, help="EC2 实例 IP 或域名")
    parser.add_argument("--username", type=str, default="ec2-user", help="SSH 用户名")
    parser.add_argument("--key-file", type=str, help="SSH 私钥文件路径")
    parser.add_argument("--port", type=int, default=22, help="SSH 端口")
    parser.add_argument("--force", "-f", action="store_true", help="不询问确认直接清理")
    parser.add_argument("--uninstall", action="store_true", help="同时卸载 sglang 包")

    args = parser.parse_args()
    return interactive_cleanup(args)


if __name__ == "__main__":
    sys.exit(main())
