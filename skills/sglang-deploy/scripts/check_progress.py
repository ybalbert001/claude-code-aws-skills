#!/usr/bin/env python3
"""
SGLang 部署进度检查脚本

直接检查远程服务器状态，不依赖状态文件。
输出 JSON 格式供 Claude Code 解析。
"""

import argparse
import json
import os
import sys

from ssh_utils import ssh_run


def check_sglang_installed(host: str, user: str, key_file: str, port: int) -> bool:
    """检查 SGLang 是否已安装"""
    cmd = "python3 -c 'import sglang; print(sglang.__version__)' 2>/dev/null"
    success, stdout, _ = ssh_run(host, user, key_file, cmd, port, timeout=10)
    return bool(stdout.strip())


def check_service_running(host: str, user: str, key_file: str, port: int) -> dict:
    """检查 SGLang 服务状态"""
    result = {
        "process_running": False,
        "pid": None,
        "api_healthy": False,
        "http_code": None
    }

    # 检查进程
    success, stdout, _ = ssh_run(host, user, key_file, "pgrep -f 'sglang.launch_server'", port, timeout=10)
    if stdout.strip():
        result["process_running"] = True
        result["pid"] = stdout.strip().split()[0]

    return result


def check_api_health(host: str, user: str, key_file: str, port: int, service_port: int) -> dict:
    """检查 API 健康状态"""
    result = {
        "api_healthy": False,
        "http_code": None,
        "error": None
    }

    cmd = f"curl -s -o /dev/null -w '%{{http_code}}' --connect-timeout 5 http://localhost:{service_port}/v1/models"
    success, stdout, _ = ssh_run(host, user, key_file, cmd, port, timeout=15)

    if stdout.strip():
        result["http_code"] = stdout.strip()
        result["api_healthy"] = result["http_code"] == "200"

    return result


def get_log_tail(host: str, user: str, key_file: str, port: int, log_path: str, lines: int = 10) -> str:
    """获取最新日志

    Args:
        host: 远程主机地址
        user: SSH 用户名
        key_file: SSH 私钥文件路径
        port: SSH 端口
        log_path: 日志文件路径 (如 ~/sglang-qwen3.5-397b.log)
        lines: 获取的行数
    """
    cmd = f"tail -{lines} {log_path} 2>/dev/null"
    _, stdout, _ = ssh_run(host, user, key_file, cmd, port, timeout=10)
    return stdout.strip() if stdout else ""


def check_progress(args) -> dict:
    """检查部署进度"""
    output = {
        "success": True,
        "sglang_installed": False,
        "service": {
            "process_running": False,
            "api_healthy": False,
            "http_code": None
        },
        "log_tail": None,
        "log_path": args.log_path,
        "message": "",
        "next_action": None
    }

    # 1. 检查 SGLang 是否已安装
    output["sglang_installed"] = check_sglang_installed(
        args.host, args.username, args.key_file, args.port
    )

    if not output["sglang_installed"]:
        output["message"] = "SGLang not installed"
        output["next_action"] = "install_sglang"
        return output

    # 2. 检查服务进程
    service_status = check_service_running(
        args.host, args.username, args.key_file, args.port
    )
    output["service"]["process_running"] = service_status["process_running"]

    if not service_status["process_running"]:
        output["message"] = "SGLang installed but service not running"
        output["next_action"] = "start_service"
        return output

    # 3. 检查 API 健康
    api_status = check_api_health(
        args.host, args.username, args.key_file, args.port, args.service_port
    )
    output["service"]["api_healthy"] = api_status["api_healthy"]
    output["service"]["http_code"] = api_status["http_code"]

    if api_status["api_healthy"]:
        output["message"] = "Service is healthy and ready"
        output["next_action"] = "done"
    elif api_status["http_code"] == "000":
        output["message"] = "Service starting, model loading..."
        output["next_action"] = "wait"
        # 获取日志查看加载进度
        output["log_tail"] = get_log_tail(
            args.host, args.username, args.key_file, args.port, args.log_path, 5
        )
    else:
        output["message"] = f"Service running but API returned {api_status['http_code']}"
        output["next_action"] = "wait"

    return output


def main():
    parser = argparse.ArgumentParser(
        description="检查 SGLang 部署进度",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python check_progress.py --host 1.2.3.4 --key_file ~/.ssh/key.pem

输出 (JSON):
  {
    "success": true,
    "sglang_installed": true,
    "service": {
      "process_running": true,
      "api_healthy": true,
      "http_code": "200"
    },
    "message": "Service is healthy and ready",
    "next_action": "done"
  }

next_action 可能的值:
  - install_sglang: 需要安装 SGLang
  - start_service: 需要启动服务
  - wait: 服务启动中，继续等待
  - done: 部署完成
"""
    )

    parser.add_argument("--host", required=True, help="EC2 实例 IP")
    parser.add_argument("--key_file", required=True, help="SSH 私钥文件路径")
    parser.add_argument("--username", default="ubuntu", help="SSH 用户名 (默认: ubuntu)")
    parser.add_argument("--port", type=int, default=22, help="SSH 端口 (默认: 22)")
    parser.add_argument("--service_port", type=int, default=30000, help="SGLang 服务端口 (默认: 30000)")
    parser.add_argument("--log_path", default="~/sglang.log", help="SGLang 日志文件路径 (默认: ~/sglang.log)")
    parser.add_argument("--pretty", action="store_true", help="格式化输出 JSON")

    args = parser.parse_args()
    args.key_file = os.path.expanduser(args.key_file)

    if not os.path.exists(args.key_file):
        print(json.dumps({
            "success": False,
            "message": f"Key file not found: {args.key_file}",
            "next_action": "fix_key_file"
        }))
        return 1

    try:
        result = check_progress(args)
        if args.pretty:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as e:
        print(json.dumps({
            "success": False,
            "message": f"Error: {str(e)}",
            "next_action": "check_connection"
        }))
        return 1


if __name__ == "__main__":
    sys.exit(main())
