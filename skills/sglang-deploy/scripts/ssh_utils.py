#!/usr/bin/env python3
"""
SSH 工具函数 - 使用系统 ssh/scp 命令
"""

import os
import subprocess
from typing import Optional


def _ssh_opts(key_file: str, port: int, timeout: int) -> list:
    """构建 SSH 通用选项"""
    return [
        "-i", key_file,
        "-p", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", f"ConnectTimeout={timeout}",
        "-o", "LogLevel=ERROR"
    ]


def ssh_run(
    host: str,
    user: str,
    key_file: str,
    cmd: str,
    port: int = 22,
    timeout: int = 300
) -> tuple[bool, str, str]:
    """
    执行远程 SSH 命令

    Returns: (success, stdout, stderr)
    """
    key_file = os.path.expanduser(key_file)
    args = ["ssh"] + _ssh_opts(key_file, port, 30) + [f"{user}@{host}", cmd]

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)


def ssh_script(
    host: str,
    user: str,
    key_file: str,
    script: str,
    port: int = 22,
    timeout: int = 600,
    env: Optional[dict] = None
) -> tuple[bool, str, str]:
    """
    执行远程脚本（通过 stdin 传递）

    Returns: (success, stdout, stderr)
    """
    if env:
        env_exports = "\n".join([f"export {k}='{v}'" for k, v in env.items()])
        script = f"{env_exports}\n{script}"

    key_file = os.path.expanduser(key_file)
    args = ["ssh", "-t"] + _ssh_opts(key_file, port, 30) + [f"{user}@{host}", "bash -s"]

    try:
        result = subprocess.run(args, input=script, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Script timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)


def ssh_upload_content(
    host: str,
    user: str,
    key_file: str,
    content: str,
    remote_path: str,
    port: int = 22,
    mode: int = 0o644
) -> tuple[bool, str]:
    """
    上传字符串内容到远程文件

    Returns: (success, message)
    """
    key_file = os.path.expanduser(key_file)

    # 创建远程目录 (使用 sudo 以支持系统路径)
    remote_dir = os.path.dirname(remote_path)
    if remote_dir:
        ssh_run(host, user, key_file, f"sudo mkdir -p {remote_dir}", port)

    # 通过 ssh + sudo tee 写入 (支持写入需要 root 权限的路径)
    args = ["ssh"] + _ssh_opts(key_file, port, 30) + [f"{user}@{host}", f"sudo tee {remote_path} > /dev/null"]

    try:
        result = subprocess.run(args, input=content, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return False, f"Upload failed: {result.stderr}"

        # 设置权限
        ssh_run(host, user, key_file, f"sudo chmod {oct(mode)[2:]} {remote_path}", port)
        return True, f"Uploaded to {remote_path}"
    except Exception as e:
        return False, f"Upload failed: {e}"


def scp_upload(
    host: str,
    user: str,
    key_file: str,
    local_path: str,
    remote_path: str,
    port: int = 22
) -> tuple[bool, str]:
    """
    使用 scp 上传文件

    Returns: (success, message)
    """
    key_file = os.path.expanduser(key_file)
    local_path = os.path.expanduser(local_path)

    if not os.path.exists(local_path):
        return False, f"Local file not found: {local_path}"

    # 创建远程目录
    remote_dir = os.path.dirname(remote_path)
    if remote_dir:
        ssh_run(host, user, key_file, f"mkdir -p {remote_dir}", port)

    args = ["scp"] + _ssh_opts(key_file, port, 30) + [local_path, f"{user}@{host}:{remote_path}"]
    # scp 用 -P 不是 -p
    args[args.index("-p")] = "-P"

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return True, f"Uploaded {local_path} to {remote_path}"
        return False, f"Upload failed: {result.stderr}"
    except Exception as e:
        return False, f"Upload failed: {e}"


def scp_download(
    host: str,
    user: str,
    key_file: str,
    remote_path: str,
    local_path: str,
    port: int = 22
) -> tuple[bool, str]:
    """
    使用 scp 下载文件

    Returns: (success, message)
    """
    key_file = os.path.expanduser(key_file)
    local_path = os.path.expanduser(local_path)

    local_dir = os.path.dirname(local_path)
    if local_dir:
        os.makedirs(local_dir, exist_ok=True)

    args = ["scp"] + _ssh_opts(key_file, port, 30) + [f"{user}@{host}:{remote_path}", local_path]
    args[args.index("-p")] = "-P"

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return True, f"Downloaded {remote_path} to {local_path}"
        return False, f"Download failed: {result.stderr}"
    except Exception as e:
        return False, f"Download failed: {e}"


def ssh_test(host: str, user: str, key_file: str, port: int = 22) -> tuple[bool, str]:
    """测试 SSH 连接"""
    success, stdout, stderr = ssh_run(host, user, key_file, "echo 'OK'", port, timeout=10)
    if success and "OK" in stdout:
        return True, f"Connected to {host}"
    return False, f"Connection failed: {stderr}"
