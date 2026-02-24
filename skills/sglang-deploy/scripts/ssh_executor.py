#!/usr/bin/env python3
"""
SSH Executor - 通过 SSH 连接远程 EC2 实例执行命令

使用 paramiko 库实现 SSH 连接和远程命令执行。
"""

import io
import os
import time
from pathlib import Path
from typing import Optional

try:
    import paramiko
except ImportError:
    print("Error: paramiko not installed. Run: pip install paramiko")
    raise


class SSHExecutor:
    """通过 SSH 连接远程 EC2 实例执行命令"""

    def __init__(
        self,
        host: str,
        username: str,
        key_file: str,
        port: int = 22,
        timeout: int = 30
    ):
        """
        初始化 SSH 执行器

        Args:
            host: 远程主机地址 (IP 或域名)
            username: SSH 用户名
            key_file: SSH 私钥文件路径
            port: SSH 端口 (默认 22)
            timeout: 连接超时时间 (秒)
        """
        self.host = host
        self.username = username
        self.key_file = os.path.expanduser(key_file)
        self.port = port
        self.timeout = timeout
        self._client: Optional[paramiko.SSHClient] = None

    def _get_client(self) -> paramiko.SSHClient:
        """获取或创建 SSH 客户端连接"""
        if self._client is None or not self._client.get_transport() or not self._client.get_transport().is_active():
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # 加载私钥
            if not os.path.exists(self.key_file):
                raise FileNotFoundError(f"SSH key file not found: {self.key_file}")

            try:
                pkey = paramiko.RSAKey.from_private_key_file(self.key_file)
            except paramiko.ssh_exception.SSHException:
                try:
                    pkey = paramiko.Ed25519Key.from_private_key_file(self.key_file)
                except paramiko.ssh_exception.SSHException:
                    pkey = paramiko.ECDSAKey.from_private_key_file(self.key_file)

            self._client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                pkey=pkey,
                timeout=self.timeout,
                look_for_keys=False,
                allow_agent=False
            )

        return self._client

    def check_connection(self) -> tuple[bool, str]:
        """
        检测 SSH 连接是否可用

        Returns:
            (成功, 消息)
        """
        try:
            client = self._get_client()
            # 执行简单命令验证连接
            stdin, stdout, stderr = client.exec_command("echo 'SSH connection OK'", timeout=10)
            output = stdout.read().decode().strip()
            if "SSH connection OK" in output:
                return True, f"Successfully connected to {self.host}"
            return False, f"Unexpected response: {output}"
        except Exception as e:
            return False, f"SSH connection failed: {str(e)}"

    def execute(
        self,
        command: str,
        timeout: int = 300,
        get_pty: bool = False
    ) -> tuple[bool, str, str]:
        """
        执行远程命令

        Args:
            command: 要执行的命令
            timeout: 命令执行超时时间 (秒)
            get_pty: 是否分配伪终端 (某些命令需要)

        Returns:
            (成功, 标准输出, 标准错误)
        """
        try:
            client = self._get_client()
            stdin, stdout, stderr = client.exec_command(
                command,
                timeout=timeout,
                get_pty=get_pty
            )

            # 读取输出
            stdout_str = stdout.read().decode()
            stderr_str = stderr.read().decode()
            exit_code = stdout.channel.recv_exit_status()

            success = exit_code == 0
            return success, stdout_str, stderr_str

        except Exception as e:
            return False, "", str(e)

    def execute_script(
        self,
        script: str,
        timeout: int = 600,
        env: Optional[dict] = None
    ) -> tuple[bool, str, str]:
        """
        执行多行脚本

        Args:
            script: 要执行的脚本内容
            timeout: 脚本执行超时时间 (秒)
            env: 环境变量字典

        Returns:
            (成功, 标准输出, 标准错误)
        """
        # 构建带环境变量的脚本
        if env:
            env_exports = "\n".join([f"export {k}='{v}'" for k, v in env.items()])
            script = f"{env_exports}\n{script}"

        # 使用 bash -c 执行脚本
        full_command = f"bash -c '{script}'"
        return self.execute(full_command, timeout=timeout, get_pty=True)

    def upload_content(
        self,
        content: str,
        remote_path: str,
        mode: int = 0o644
    ) -> tuple[bool, str]:
        """
        上传字符串内容到远程文件

        Args:
            content: 文件内容
            remote_path: 远程文件路径
            mode: 文件权限

        Returns:
            (成功, 消息)
        """
        try:
            client = self._get_client()
            sftp = client.open_sftp()

            # 创建目录 (如果不存在)
            remote_dir = os.path.dirname(remote_path)
            if remote_dir:
                try:
                    sftp.stat(remote_dir)
                except FileNotFoundError:
                    # 递归创建目录
                    self.execute(f"mkdir -p {remote_dir}")

            # 写入文件
            with sftp.file(remote_path, 'w') as f:
                f.write(content)

            sftp.chmod(remote_path, mode)
            sftp.close()

            return True, f"Uploaded to {remote_path}"

        except Exception as e:
            return False, f"Upload failed: {str(e)}"

    def upload_file(
        self,
        local_path: str,
        remote_path: str
    ) -> tuple[bool, str]:
        """
        上传本地文件到远程

        Args:
            local_path: 本地文件路径
            remote_path: 远程文件路径

        Returns:
            (成功, 消息)
        """
        try:
            local_path = os.path.expanduser(local_path)
            if not os.path.exists(local_path):
                return False, f"Local file not found: {local_path}"

            client = self._get_client()
            sftp = client.open_sftp()

            # 创建目录
            remote_dir = os.path.dirname(remote_path)
            if remote_dir:
                self.execute(f"mkdir -p {remote_dir}")

            sftp.put(local_path, remote_path)
            sftp.close()

            return True, f"Uploaded {local_path} to {remote_path}"

        except Exception as e:
            return False, f"Upload failed: {str(e)}"

    def download_file(
        self,
        remote_path: str,
        local_path: str
    ) -> tuple[bool, str]:
        """
        从远程下载文件到本地

        Args:
            remote_path: 远程文件路径
            local_path: 本地文件路径

        Returns:
            (成功, 消息)
        """
        try:
            local_path = os.path.expanduser(local_path)
            local_dir = os.path.dirname(local_path)
            if local_dir:
                os.makedirs(local_dir, exist_ok=True)

            client = self._get_client()
            sftp = client.open_sftp()
            sftp.get(remote_path, local_path)
            sftp.close()

            return True, f"Downloaded {remote_path} to {local_path}"

        except Exception as e:
            return False, f"Download failed: {str(e)}"

    def close(self):
        """关闭 SSH 连接"""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def test_connection(
    host: str,
    username: str,
    key_file: str,
    port: int = 22
) -> tuple[bool, str]:
    """
    测试 SSH 连接

    Args:
        host: 远程主机地址
        username: SSH 用户名
        key_file: SSH 私钥文件路径
        port: SSH 端口

    Returns:
        (成功, 消息)
    """
    try:
        executor = SSHExecutor(host, username, key_file, port)
        success, message = executor.check_connection()
        executor.close()
        return success, message
    except Exception as e:
        return False, str(e)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test SSH connection")
    parser.add_argument("--host", required=True, help="Remote host address")
    parser.add_argument("--username", default="ec2-user", help="SSH username")
    parser.add_argument("--key-file", required=True, help="SSH private key file")
    parser.add_argument("--port", type=int, default=22, help="SSH port")
    parser.add_argument("--command", help="Command to execute")

    args = parser.parse_args()

    print(f"Testing SSH connection to {args.host}...")
    success, message = test_connection(args.host, args.username, args.key_file, args.port)
    print(f"  {'✓' if success else '✗'} {message}")

    if success and args.command:
        print(f"\nExecuting command: {args.command}")
        with SSHExecutor(args.host, args.username, args.key_file, args.port) as executor:
            success, stdout, stderr = executor.execute(args.command)
            print(f"Exit code: {'0 (success)' if success else 'non-zero (failed)'}")
            if stdout:
                print(f"Output:\n{stdout}")
            if stderr:
                print(f"Errors:\n{stderr}")
