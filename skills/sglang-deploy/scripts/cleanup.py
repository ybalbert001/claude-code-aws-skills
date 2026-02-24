#!/usr/bin/env python3
"""
SGLang Cleanup Script

通过 SSH 清理 EC2 实例上的 SGLang 部署。

功能:
- 停止 SGLang 服务
- 卸载 SGLang
- 停止监控组件
- 清理配置文件
"""

import sys
from ssh_executor import SSHExecutor


def stop_sglang_service(executor: SSHExecutor) -> bool:
    """停止 SGLang 服务"""
    print("\n[1/4] 停止 SGLang 服务...")

    # 停止服务
    success, stdout, stderr = executor.execute("systemctl stop sglang 2>/dev/null || true")

    # 禁用服务
    success, stdout, stderr = executor.execute("systemctl disable sglang 2>/dev/null || true")

    # 删除服务文件
    success, stdout, stderr = executor.execute("rm -f /etc/systemd/system/sglang.service")
    executor.execute("systemctl daemon-reload")

    # 检查是否还有 sglang 进程
    success, stdout, stderr = executor.execute("pgrep -f 'sglang.launch_server'")
    if success and stdout.strip():
        print("  发现残留进程，强制终止...")
        executor.execute("pkill -9 -f 'sglang.launch_server'")

    print("✓ SGLang 服务已停止")
    return True


def uninstall_sglang(executor: SSHExecutor) -> bool:
    """卸载 SGLang"""
    print("\n[2/4] 卸载 SGLang...")

    # 检查是否安装
    success, stdout, stderr = executor.execute("python3 -c 'import sglang' 2>/dev/null")
    if not success:
        print("  SGLang 未安装，跳过")
        return True

    # 卸载
    success, stdout, stderr = executor.execute("pip uninstall -y sglang 2>/dev/null || true")
    print("✓ SGLang 已卸载")
    return True


def stop_monitoring(executor: SSHExecutor) -> bool:
    """停止监控组件"""
    print("\n[3/4] 停止监控组件...")

    # 检查 docker-compose 是否存在
    success, stdout, stderr = executor.execute("test -f /opt/monitoring/docker-compose.yml && echo 'exists'")
    if not success or "exists" not in stdout:
        print("  监控组件未安装，跳过")
        return True

    # 停止容器
    success, stdout, stderr = executor.execute("cd /opt/monitoring && docker-compose down 2>/dev/null || true")
    print("✓ 监控组件已停止")
    return True


def cleanup_files(executor: SSHExecutor) -> bool:
    """清理配置文件"""
    print("\n[4/4] 清理配置文件...")

    # 清理监控目录
    executor.execute("rm -rf /opt/monitoring")

    # 清理模型缓存 (可选，默认不清理)
    # executor.execute("rm -rf ~/.cache/huggingface")

    print("✓ 配置文件已清理")
    return True


def interactive_cleanup(args):
    """交互式清理流程"""
    print("=" * 60)
    print("SGLang 清理工具")
    print("=" * 60)

    # 获取连接信息
    if not args.host:
        args.host = input("\n请输入 EC2 实例 IP 或域名: ").strip()
        if not args.host:
            print("错误: 必须提供主机地址")
            return 1

    if not args.key_file:
        args.key_file = input("SSH 私钥文件路径: ").strip()
        if not args.key_file:
            print("错误: 必须提供 SSH 私钥文件")
            return 1

    username = args.username or "ec2-user"
    port = args.port or 22

    print(f"\n目标实例: {args.host}")
    print(f"用户名: {username}")

    # 确认
    if not args.force:
        confirm = input("\n确认清理? 这将停止 SGLang 服务并删除配置 [y/N]: ").strip().lower()
        if confirm != 'y':
            print("清理取消。")
            return 1

    # 执行清理
    try:
        with SSHExecutor(args.host, username, args.key_file, port) as executor:
            # 检查连接
            success, msg = executor.check_connection()
            if not success:
                print(f"\n✗ SSH 连接失败: {msg}")
                return 1

            print(f"\n✓ 已连接到 {args.host}")

            # 执行清理步骤
            stop_sglang_service(executor)

            if args.uninstall:
                uninstall_sglang(executor)

            stop_monitoring(executor)
            cleanup_files(executor)

            print("\n" + "=" * 60)
            print("✓ 清理完成!")
            print("=" * 60)
            return 0

    except Exception as e:
        print(f"\n✗ 清理失败: {e}")
        return 1


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="清理 EC2 实例上的 SGLang 部署",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 交互式清理
  python cleanup.py

  # 指定连接信息
  python cleanup.py --host 10.0.1.100 --username ec2-user --key-file ~/.ssh/my-key.pem

  # 强制清理 (不询问确认)
  python cleanup.py --host 10.0.1.100 --key-file ~/.ssh/my-key.pem --force

  # 同时卸载 sglang 包
  python cleanup.py --host 10.0.1.100 --key-file ~/.ssh/my-key.pem --uninstall
        """
    )

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
