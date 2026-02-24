#!/usr/bin/env python3
"""
Instance Checker - 通过 SSH 检测 EC2 实例的可用性和配置

检测项目:
- GPU 配置 (nvidia-smi)
- 磁盘空间
- Python 环境
- 网络连通性
"""

import json
import re

from ssh_utils import ssh_run, ssh_test


class InstanceChecker:
    """通过 SSH 检测 EC2 实例的可用性和配置"""

    def __init__(self, host: str, user: str, key_file: str, port: int = 22):
        self.host = host
        self.user = user
        self.key_file = key_file
        self.port = port

    def _run(self, cmd: str, timeout: int = 300) -> tuple[bool, str, str]:
        """执行远程命令"""
        return ssh_run(self.host, self.user, self.key_file, cmd, self.port, timeout)

    def check_connection(self) -> tuple[bool, str]:
        """检测 SSH 连接"""
        return ssh_test(self.host, self.user, self.key_file, self.port)

    def check_gpu_availability(self) -> dict:
        """检测 GPU 配置"""
        result = {
            "available": False,
            "count": 0,
            "gpus": [],
            "driver_version": "",
            "cuda_version": "",
            "error": ""
        }

        success, stdout, stderr = self._run("which nvidia-smi")
        if not success:
            result["error"] = "nvidia-smi not found. Is NVIDIA driver installed?"
            return result

        cmd = "nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader,nounits"
        success, stdout, stderr = self._run(cmd)

        if not success:
            result["error"] = f"nvidia-smi failed: {stderr}"
            return result

        gpus = []
        for line in stdout.strip().split("\n"):
            if line.strip():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    gpus.append({
                        "index": int(parts[0]),
                        "name": parts[1],
                        "memory_total_mb": int(parts[2]),
                        "memory_free_mb": int(parts[3])
                    })

        result["available"] = len(gpus) > 0
        result["count"] = len(gpus)
        result["gpus"] = gpus

        success, stdout, _ = self._run("nvidia-smi --query-gpu=driver_version --format=csv,noheader")
        if success and stdout.strip():
            result["driver_version"] = stdout.strip().split("\n")[0]

        success, stdout, _ = self._run("nvidia-smi | grep 'CUDA Version' | awk '{print $9}'")
        if success and stdout.strip():
            result["cuda_version"] = stdout.strip()

        success, stdout, _ = self._run("nvcc --version 2>/dev/null | grep release || /usr/local/cuda/bin/nvcc --version 2>/dev/null | grep release")
        if success and stdout.strip():
            result["cuda_toolkit_installed"] = True
            match = re.search(r'release (\d+\.\d+)', stdout)
            if match:
                result["cuda_toolkit_version"] = match.group(1)
        else:
            result["cuda_toolkit_installed"] = False
            result["cuda_toolkit_version"] = ""

        return result

    def check_disk_space(self, path: str = "/") -> dict:
        """检测磁盘空间"""
        result = {
            "path": path,
            "total_gb": 0,
            "used_gb": 0,
            "available_gb": 0,
            "use_percent": 0,
            "sufficient": False
        }

        success, stdout, _ = self._run(f"df -BG {path} | tail -1")
        if not success:
            return result

        parts = stdout.split()
        if len(parts) >= 5:
            try:
                result["total_gb"] = float(parts[1].rstrip('G'))
                result["used_gb"] = float(parts[2].rstrip('G'))
                result["available_gb"] = float(parts[3].rstrip('G'))
                result["use_percent"] = float(parts[4].rstrip('%'))
                result["sufficient"] = result["available_gb"] >= 100
            except (ValueError, IndexError):
                pass

        return result

    def check_python_env(self) -> dict:
        """检测 Python 环境"""
        result = {
            "python_available": False,
            "python_version": "",
            "python_path": "",
            "pip_available": False,
            "pip_version": "",
            "uv_available": False,
            "uv_version": "",
            "conda_available": False
        }

        for python_cmd in ["python3", "python"]:
            success, stdout, _ = self._run(f"which {python_cmd}")
            if success and stdout.strip():
                result["python_path"] = stdout.strip()
                success, stdout, _ = self._run(f"{python_cmd} --version")
                if success:
                    result["python_available"] = True
                    result["python_version"] = stdout.strip().replace("Python ", "")
                break

        for pip_cmd in ["pip3", "pip"]:
            success, stdout, _ = self._run(f"{pip_cmd} --version")
            if success and stdout.strip():
                result["pip_available"] = True
                match = re.search(r'pip (\d+\.\d+(\.\d+)?)', stdout)
                if match:
                    result["pip_version"] = match.group(1)
                break

        success, stdout, _ = self._run("uv --version")
        if success and stdout.strip():
            result["uv_available"] = True
            result["uv_version"] = stdout.strip().replace("uv ", "")

        success, stdout, _ = self._run("which conda")
        result["conda_available"] = success and bool(stdout.strip())

        return result

    def check_network(self, test_url: str = "https://huggingface.co") -> dict:
        """检测网络连通性"""
        result = {
            "internet_available": False,
            "huggingface_accessible": False,
            "test_url": test_url,
            "latency_ms": 0
        }

        success, stdout, _ = self._run("curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 https://www.google.com")
        if success and stdout.strip() == "200":
            result["internet_available"] = True

        success, stdout, _ = self._run(f"curl -s -o /dev/null -w '%{{http_code}} %{{time_total}}' --connect-timeout 10 {test_url}")
        if success:
            parts = stdout.strip().split()
            if len(parts) >= 1 and parts[0] in ["200", "301", "302"]:
                result["huggingface_accessible"] = True
                if len(parts) >= 2:
                    try:
                        result["latency_ms"] = float(parts[1]) * 1000
                    except ValueError:
                        pass

        return result

    def check_sglang_installed(self) -> dict:
        """检测 SGLang 是否已安装"""
        result = {"installed": False, "version": "", "path": ""}

        success, stdout, _ = self._run("python3 -c 'import sglang; print(sglang.__version__)'")
        if success and stdout.strip():
            result["installed"] = True
            result["version"] = stdout.strip()

        success, stdout, _ = self._run("python3 -c 'import sglang; print(sglang.__file__)'")
        if success and stdout.strip():
            result["path"] = stdout.strip()

        return result

    def check_sglang_service(self) -> dict:
        """检测 SGLang 服务状态"""
        result = {"service_exists": False, "service_running": False, "port": 0, "pid": 0}

        success, stdout, _ = self._run("test -f /opt/start_sglang.sh && echo 'exists'")
        if success and "exists" in stdout:
            result["service_exists"] = True

        success, stdout, _ = self._run("pgrep -f 'sglang.launch_server'")
        if success and stdout.strip():
            result["service_running"] = True
            try:
                result["pid"] = int(stdout.strip().split("\n")[0])
            except ValueError:
                pass

        success, stdout, _ = self._run("ss -tlnp | grep -E ':30000|:8000' | head -1")
        if success and stdout.strip():
            match = re.search(r':(\d+)\s', stdout)
            if match:
                result["port"] = int(match.group(1))

        return result

    def run_all_checks(self) -> dict:
        """运行所有检测"""
        connection_ok, connection_msg = self.check_connection()
        gpu_info = self.check_gpu_availability()
        disk_info = self.check_disk_space()
        python_info = self.check_python_env()
        network_info = self.check_network()
        sglang_info = self.check_sglang_installed()
        service_info = self.check_sglang_service()

        issues = []
        if not connection_ok:
            issues.append(f"SSH connection failed: {connection_msg}")
        if not gpu_info["available"]:
            issues.append(f"No GPU available: {gpu_info.get('error', 'Unknown')}")
        if not disk_info["sufficient"]:
            issues.append(f"Insufficient disk space: {disk_info['available_gb']:.1f}GB available (need 100GB+)")
        if not python_info["python_available"]:
            issues.append("Python not available")
        if not python_info["pip_available"]:
            issues.append("pip not available")
        if not network_info["huggingface_accessible"]:
            issues.append("Cannot access HuggingFace (model download may fail)")

        ready = len(issues) == 0 or (
            connection_ok and
            gpu_info["available"] and
            python_info["python_available"] and
            python_info["pip_available"]
        )

        return {
            "connection": {"ok": connection_ok, "message": connection_msg},
            "gpu": gpu_info,
            "disk": disk_info,
            "python": python_info,
            "network": network_info,
            "sglang": sglang_info,
            "service": service_info,
            "summary": {"ready_for_deployment": ready, "issues": issues}
        }


def print_check_report(report: dict):
    """打印检测报告"""
    print("\n" + "=" * 60)
    print("Instance Check Report")
    print("=" * 60)

    conn = report["connection"]
    print(f"\n{'✓' if conn['ok'] else '✗'} SSH Connection: {conn['message']}")

    gpu = report["gpu"]
    if gpu["available"]:
        print(f"\n✓ GPU: {gpu['count']} GPU(s) found")
        for g in gpu["gpus"]:
            print(f"    - GPU {g['index']}: {g['name']} ({g['memory_total_mb']}MB, {g['memory_free_mb']}MB free)")
        print(f"    Driver: {gpu['driver_version']}, CUDA: {gpu['cuda_version']}")
        toolkit_status = f"✓ {gpu.get('cuda_toolkit_version', 'unknown')}" if gpu.get('cuda_toolkit_installed') else "✗ Not installed"
        print(f"    CUDA Toolkit (nvcc): {toolkit_status}")
    else:
        print(f"\n✗ GPU: {gpu.get('error', 'Not available')}")

    disk = report["disk"]
    print(f"\n{'✓' if disk['sufficient'] else '⚠'} Disk: {disk['available_gb']:.1f}GB available / {disk['total_gb']:.1f}GB total ({disk['use_percent']:.0f}% used)")

    py = report["python"]
    print(f"\n{'✓' if py['python_available'] else '✗'} Python: {py['python_version'] or 'Not found'}")
    print(f"    pip: {'✓ ' + py['pip_version'] if py['pip_available'] else '✗ Not found'}")
    print(f"    uv: {'✓ ' + py['uv_version'] if py['uv_available'] else '- Not installed'}")

    net = report["network"]
    print(f"\n{'✓' if net['internet_available'] else '✗'} Internet: {'Available' if net['internet_available'] else 'Not available'}")
    print(f"    HuggingFace: {'✓ Accessible' if net['huggingface_accessible'] else '✗ Not accessible'}" +
          (f" ({net['latency_ms']:.0f}ms)" if net['latency_ms'] else ""))

    sg = report["sglang"]
    print(f"\n{'✓' if sg['installed'] else '-'} SGLang: {sg['version'] if sg['installed'] else 'Not installed'}")

    svc = report["service"]
    if svc["service_running"]:
        print(f"✓ Service: Running (port {svc['port']}, pid {svc['pid']})")
    elif svc["service_exists"]:
        print("- Service: Configured but not running")
    else:
        print("- Service: Not configured")

    summary = report["summary"]
    print("\n" + "=" * 60)
    if summary["ready_for_deployment"]:
        print("✓ Instance is ready for SGLang deployment")
    else:
        print("✗ Issues found:")
        for issue in summary["issues"]:
            print(f"  - {issue}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check EC2 instance for SGLang deployment")
    parser.add_argument("--host", required=True, help="Remote host address")
    parser.add_argument("--username", default="ec2-user", help="SSH username")
    parser.add_argument("--key-file", required=True, help="SSH private key file")
    parser.add_argument("--port", type=int, default=22, help="SSH port")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    checker = InstanceChecker(args.host, args.username, args.key_file, args.port)
    report = checker.run_all_checks()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_check_report(report)
