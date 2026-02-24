#!/usr/bin/env python3
"""
SGLang AWS Deployment Script

通过 SSH 在预先存在的 EC2 实例上部署 SGLang LLM 推理服务器。
纯 CLI 模式，所有参数通过命令行提供。
"""

import argparse
import os
import sys
import time

from ssh_utils import ssh_run, ssh_script, ssh_upload_content
from instance_checker import InstanceChecker, print_check_report
from hf_api import fetch_trending_models, fetch_model_params, parse_params_from_name, estimate_model_requirements


def load_models_config():
    """从 HuggingFace API 获取 trending 模型列表 (32B+)"""
    print("正在从 HuggingFace 获取 trending 32B+ 模型...")
    models = fetch_trending_models(limit=15, min_params_billions=32)
    if models:
        print(f"已获取 {len(models)} 个模型")
    else:
        print("警告: 无法从 HuggingFace 获取模型列表")
    return {"models": models}


def get_model_config(model_id: str):
    """获取指定模型的配置"""
    if "/" not in model_id:
        print(f"错误: 模型 ID 格式应为 'org/model'，如 'Qwen/Qwen2.5-72B-Instruct'")
        return None

    print(f"正在获取模型信息: {model_id}")
    params_total = fetch_model_params(model_id)
    params_billions = None

    if params_total:
        params_billions = params_total / 1e9
    else:
        params_billions = parse_params_from_name(model_id)

    if params_billions is None:
        params_billions = 32.0
        print(f"  无法获取参数量，使用默认值 {params_billions}B")

    requirements = estimate_model_requirements(params_billions, model_id)

    return {
        "id": model_id.split("/")[-1].lower(),
        "name": model_id.split("/")[-1],
        "hf_model_id": model_id,
        "min_gpu_memory_gb": requirements["min_gpu_memory_gb"],
        "recommended_instance": requirements["recommended_instance"],
        "recommended_tp": requirements["recommended_tp"],
        "params_billions": round(params_billions, 1),
    }


def check_instance(ssh_info: dict) -> dict | None:
    """检测实例可用性"""
    print("\n" + "=" * 60)
    print("检测实例配置...")
    print("=" * 60)

    try:
        checker = InstanceChecker(ssh_info["host"], ssh_info["user"], ssh_info["key"], ssh_info["port"])
        report = checker.run_all_checks()
        print_check_report(report)

        if not report["summary"]["ready_for_deployment"]:
            print("\n⚠ 实例存在问题，继续部署...")

        return report

    except Exception as e:
        print(f"\n✗ 连接失败: {e}")
        return None


def configure_deployment(args, model_config: dict, gpu_info: dict) -> dict:
    """配置部署参数"""
    print("\n" + "=" * 60)
    print("配置部署参数")
    print("=" * 60)

    config = {}
    gpu_count = gpu_info.get("count", 1)
    recommended_tp = model_config.get("recommended_tp", 1)
    default_tp = min(recommended_tp, gpu_count)

    # 服务端口
    config["port"] = args.service_port if args.service_port else 30000
    print(f"  端口: {config['port']}")

    # Tensor Parallelism
    config["tp"] = args.tp if args.tp else default_tp
    print(f"  TP: {config['tp']} (GPU数: {gpu_count}, 推荐: {recommended_tp})")

    # 监控组件
    config["enable_monitoring"] = args.enable_monitoring if args.enable_monitoring is not None else False
    print(f"  监控: {'是' if config['enable_monitoring'] else '否'}")

    # HuggingFace Token
    if args.hf_token:
        config["hf_token"] = args.hf_token
        print("  HF Token: 已设置")

    return config


def generate_prereq_script() -> str:
    """生成前置环境准备脚本"""
    return """#!/bin/bash
set -ex
echo "=== 准备前置环境 ==="

if ! command -v pip3 &> /dev/null; then
    echo "Installing python3-pip..."
    sudo apt-get update && sudo apt-get install -y python3-pip
fi

if ! command -v uv &> /dev/null && [ ! -f ~/.local/bin/uv ]; then
    echo "Installing uv..."
    pip3 install --break-system-packages uv || pip3 install --user uv
fi

if ! command -v nvcc &> /dev/null && [ ! -f /usr/local/cuda/bin/nvcc ]; then
    echo "Installing CUDA Toolkit..."
    sudo apt-get update
    sudo apt-get install -y cuda-toolkit-12-8 || sudo apt-get install -y cuda-toolkit-12-6 || sudo apt-get install -y cuda-toolkit
fi

export PATH="$HOME/.local/bin:/usr/local/cuda/bin:$PATH"
echo "=== 前置环境准备完成 ==="
"""


def generate_install_script(deploy_config: dict) -> str:
    """生成 SGLang 安装脚本"""
    hf_token = deploy_config.get("hf_token", "")
    return f"""#!/bin/bash
set -ex
echo "=== 开始安装 SGLang ==="
{f'export HF_TOKEN="{hf_token}"' if hf_token else ''}
export PATH="$HOME/.local/bin:$PATH"

if command -v uv &> /dev/null; then
    sudo $(which uv) pip install "sglang[all]" --system --break-system-packages
elif [ -f ~/.local/bin/uv ]; then
    sudo ~/.local/bin/uv pip install "sglang[all]" --system --break-system-packages
else
    sudo pip3 install --break-system-packages "sglang[all]"
fi

echo "=== SGLang 安装完成 ==="
"""


def generate_startup_script(model_config: dict, deploy_config: dict) -> str:
    """生成启动脚本"""
    hf_model_id = model_config["hf_model_id"]
    port = deploy_config.get("port", 30000)
    tp = deploy_config.get("tp", 1)
    hf_token = deploy_config.get("hf_token", "")

    return f"""#!/bin/bash
{f'export HF_TOKEN="{hf_token}"' if hf_token else ''}
LOG_FILE="/tmp/sglang.log"
pkill -f "sglang.launch_server" 2>/dev/null || true
sleep 2
echo "Starting SGLang server..."
nohup python3 -m sglang.launch_server \\
    --model-path {hf_model_id} \\
    --host 0.0.0.0 \\
    --port {port} \\
    --tp {tp} \\
    --enable-metrics \\
    > $LOG_FILE 2>&1 &
echo "SGLang server started with PID: $!"
echo "Log file: $LOG_FILE"
"""


def generate_monitoring_script() -> str:
    """生成监控组件安装脚本"""
    return """#!/bin/bash
set -ex
echo "=== 安装监控组件 ==="

if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh
    systemctl start docker && systemctl enable docker
fi

if ! command -v docker-compose &> /dev/null; then
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi

mkdir -p /opt/monitoring
cat > /opt/monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'sglang'
    static_configs:
      - targets: ['localhost:30000']
EOF

cat > /opt/monitoring/docker-compose.yml << 'EOF'
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    ports: ["9090:9090"]
    volumes: ["./prometheus.yml:/etc/prometheus/prometheus.yml"]
    network_mode: host
  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
    environment: ["GF_SECURITY_ADMIN_PASSWORD=admin"]
    network_mode: host
EOF

cd /opt/monitoring && docker-compose up -d
echo "=== 监控组件安装完成 ==="
"""


def execute_deployment(ssh_info: dict, model_config: dict, deploy_config: dict) -> bool:
    """执行部署"""
    print("\n" + "=" * 60)
    print("执行部署")
    print("=" * 60)

    host, user, key, port = ssh_info["host"], ssh_info["user"], ssh_info["key"], ssh_info["port"]

    try:
        # 1. 准备前置环境
        print("\n[1/5] 准备前置环境...")
        success, stdout, stderr = ssh_script(host, user, key, generate_prereq_script(), port, timeout=300)
        if not success:
            print(f"⚠ 前置环境警告: {stderr}")
        print("✓ 前置环境准备完成")

        # 2. 安装 SGLang
        print("\n[2/5] 安装 SGLang...")
        success, stdout, stderr = ssh_script(host, user, key, generate_install_script(deploy_config), port, timeout=900)
        if not success:
            print(f"✗ SGLang 安装失败: {stderr}")
            return False
        print("✓ SGLang 安装完成")

        # 3. 上传启动脚本
        print("\n[3/5] 配置启动脚本...")
        success, msg = ssh_upload_content(host, user, key, generate_startup_script(model_config, deploy_config), "/opt/start_sglang.sh", port, mode=0o755)
        if not success:
            print(f"✗ 启动脚本配置失败: {msg}")
            return False
        print("✓ 启动脚本配置完成")

        # 4. 安装监控 (可选)
        if deploy_config.get("enable_monitoring"):
            print("\n[4/5] 安装监控组件...")
            success, _, stderr = ssh_script(host, user, key, generate_monitoring_script(), port, timeout=300)
            if not success:
                print(f"⚠ 监控安装失败: {stderr}")
            else:
                print("✓ 监控组件安装完成")
        else:
            print("\n[4/5] 跳过监控组件安装")

        # 5. 启动服务
        print("\n[5/5] 启动 SGLang 服务...")
        ssh_run(host, user, key, "sudo /opt/start_sglang.sh", port)

        print("等待服务启动...")
        time.sleep(10)

        success, stdout, _ = ssh_run(host, user, key, "pgrep -f 'sglang.launch_server' && echo 'SGLang is running'", port)
        if "SGLang is running" in stdout:
            print("✓ SGLang 服务启动成功")
        else:
            print("⚠ SGLang 进程未检测到，请检查日志: tail -f /tmp/sglang.log")

        return True

    except Exception as e:
        print(f"\n✗ 部署失败: {e}")
        return False


def print_deployment_summary(ssh_info: dict, model_config: dict, deploy_config: dict):
    """打印部署摘要"""
    host = ssh_info["host"]
    port = deploy_config.get("port", 30000)

    print("\n" + "=" * 60)
    print("部署完成!")
    print("=" * 60)
    print(f"\nSGLang API: http://{host}:{port}")
    print(f"模型: {model_config['hf_model_id']}")
    print(f"Tensor Parallelism: {deploy_config.get('tp', 1)}")

    if deploy_config.get("enable_monitoring"):
        print(f"\nGrafana: http://{host}:3000 (admin/admin)")
        print(f"Prometheus: http://{host}:9090")

    print(f"\n测试命令:")
    print(f'''curl http://{host}:{port}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{{"model": "default", "messages": [{{"role": "user", "content": "Hello!"}}]}}'
''')


def deploy(args) -> int:
    """执行部署流程"""
    print("=" * 60)
    print("SGLang AWS Deployment - SSH 远程部署")
    print("=" * 60)

    # 1. 验证计算资源类型
    print("\n[1/5] 验证计算资源类型")
    if args.resource_type == "hyperpod":
        print("✗ Hyperpod 集群支持即将推出，请使用 EC2 实例")
        return 1
    print(f"  资源类型: {args.resource_type}")

    # 2. 构建 SSH 连接信息
    print("\n[2/5] SSH 连接配置")
    key_file = os.path.expanduser(args.key_file)
    if not os.path.exists(key_file):
        print(f"✗ 密钥文件不存在: {key_file}")
        return 1

    ssh_info = {
        "host": args.host,
        "user": args.username,
        "key": key_file,
        "port": args.port
    }
    print(f"  主机: {ssh_info['host']}")
    print(f"  用户: {ssh_info['user']}")
    print(f"  端口: {ssh_info['port']}")

    # 3. 检测实例可用性
    print("\n[3/5] 检测实例可用性")
    report = check_instance(ssh_info)
    if not report:
        print("✗ 无法连接到实例")
        return 1

    gpu_info = report.get("gpu", {})
    gpu_count = gpu_info.get("count", 0)

    if gpu_count == 0:
        print("\n✗ 未检测到 GPU，无法部署 SGLang")
        return 1

    # 4. 获取模型配置
    print("\n[4/5] 获取模型配置")
    model_config = get_model_config(args.model)
    if not model_config:
        print(f"✗ 无法获取模型 '{args.model}' 的配置")
        return 1

    print(f"  模型: {model_config['name']}")
    print(f"  HuggingFace ID: {model_config['hf_model_id']}")
    print(f"  参数量: {model_config.get('params_billions', 'N/A')}B")
    print(f"  推荐 TP: {model_config['recommended_tp']}")

    # 5. 配置部署参数并执行
    print("\n[5/5] 配置部署参数")
    deploy_config = configure_deployment(args, model_config, gpu_info)

    # 打印部署摘要
    print("\n" + "=" * 60)
    print("部署配置摘要")
    print("=" * 60)
    print(f"  主机: {ssh_info['host']}")
    print(f"  模型: {model_config['hf_model_id']}")
    print(f"  端口: {deploy_config['port']}")
    print(f"  TP: {deploy_config['tp']}")
    print(f"  监控: {'是' if deploy_config.get('enable_monitoring') else '否'}")
    print("=" * 60)

    # 执行部署
    success = execute_deployment(ssh_info, model_config, deploy_config)

    if success:
        print_deployment_summary(ssh_info, model_config, deploy_config)
        return 0
    else:
        print("\n✗ 部署失败，请检查日志")
        return 1


def list_models() -> int:
    """列出可用模型"""
    print("\n" + "=" * 60)
    print("Trending 32B+ SGLang Models (from HuggingFace)")
    print("=" * 60)
    config = load_models_config()
    models = config.get("models", [])
    if not models:
        print("\n无法获取模型列表")
        return 1
    for i, model in enumerate(models, 1):
        print(f"\n  {i}. {model['name']}")
        print(f"     HuggingFace: {model['hf_model_id']}")
        print(f"     参数量: {model.get('params_billions', 'N/A')}B")
        print(f"     推荐配置: {model['recommended_instance']} (TP={model['recommended_tp']})")
    print()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="通过 SSH 在 EC2 实例上部署 SGLang",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 部署模型
  python deploy.py --host 1.2.3.4 --key_file ~/.ssh/key.pem --model Qwen/Qwen2.5-72B-Instruct

  # 指定 TP 和端口
  python deploy.py --host 1.2.3.4 --key_file ~/.ssh/key.pem --model Qwen/Qwen2.5-72B-Instruct --tp 8 --service_port 8080

  # 启用监控
  python deploy.py --host 1.2.3.4 --key_file ~/.ssh/key.pem --model Qwen/Qwen2.5-72B-Instruct --enable_monitoring

  # 列出可用模型
  python deploy.py --trending_models
"""
    )

    # 必需参数
    parser.add_argument("--host", type=str, required=False, help="EC2 实例 IP 或域名 (必需)")
    parser.add_argument("--key_file", type=str, required=False, help="SSH 私钥文件路径 (必需)")
    parser.add_argument("--model", type=str, required=False, help="HuggingFace 模型 ID，如 Qwen/Qwen2.5-72B-Instruct (必需)")

    # 可选参数
    parser.add_argument("--username", type=str, default="ubuntu", help="SSH 用户名 (默认: ubuntu)")
    parser.add_argument("--port", type=int, default=22, help="SSH 端口 (默认: 22)")
    parser.add_argument("--resource_type", choices=["ec2", "hyperpod"], default="ec2",
                        help="计算资源类型 (默认: ec2)")
    parser.add_argument("--service_port", type=int, help="SGLang 服务端口 (默认: 30000)")
    parser.add_argument("--tp", type=int, help="Tensor Parallelism (默认: 自动根据 GPU 数量)")
    parser.add_argument("--hf_token", type=str, help="HuggingFace Token (部分模型需要)")

    # 监控选项
    monitoring_group = parser.add_mutually_exclusive_group()
    monitoring_group.add_argument("--enable_monitoring", action="store_true", dest="enable_monitoring",
                                  help="安装监控组件 (Prometheus + Grafana)")
    monitoring_group.add_argument("--no_monitoring", action="store_false", dest="enable_monitoring",
                                  help="不安装监控组件 (默认)")
    parser.set_defaults(enable_monitoring=None)

    # 辅助命令
    parser.add_argument("--trending_models", action="store_true", help="列出可用的 trending 模型")

    args = parser.parse_args()

    # 列出模型
    if args.trending_models:
        return list_models()

    # 检查必需参数
    missing = []
    if not args.host:
        missing.append("--host")
    if not args.key_file:
        missing.append("--key-file")
    if not args.model:
        missing.append("--model")

    if missing:
        print(f"错误: 缺少必需参数: {', '.join(missing)}")
        print("\n使用 --help 查看帮助")
        return 1

    return deploy(args)


if __name__ == "__main__":
    sys.exit(main())
