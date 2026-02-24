#!/usr/bin/env python3
"""
SGLang AWS Deployment Script

通过 SSH 在预先存在的 EC2 实例上部署 SGLang LLM 推理服务器。
"""

import os
import sys
import time
from typing import Optional

from ssh_utils import ssh_run, ssh_script, ssh_upload_content, ssh_test
from instance_checker import InstanceChecker, print_check_report
from hf_api import fetch_trending_models, fetch_model_params, parse_params_from_name, estimate_model_requirements


def load_models_config():
    """从 HuggingFace API 获取 trending 模型列表 (32B+)"""
    print("正在从 HuggingFace 获取 trending 32B+ 模型...")
    models = fetch_trending_models(limit=15, min_params_billions=32)
    if models:
        print(f"已获取 {len(models)} 个模型")
    else:
        print("警告: 无法从 HuggingFace 获取模型列表，请检查网络连接")
    return {"models": models}


def get_model_config(model_id: str, models_list: list = None):
    """获取指定模型的配置"""
    if models_list:
        for model in models_list:
            if model["id"] == model_id or model.get("hf_model_id") == model_id:
                return model

    if "/" in model_id:
        print(f"正在获取模型信息: {model_id}")
        params_total = fetch_model_params(model_id)
        params_billions = None

        if params_total:
            params_billions = params_total / 1e9
        else:
            params_billions = parse_params_from_name(model_id)

        if params_billions is None:
            params_billions = 32.0

        requirements = estimate_model_requirements(params_billions, model_id)

        return {
            "id": model_id.split("/")[-1].lower(),
            "name": model_id.split("/")[-1],
            "hf_model_id": model_id,
            "min_gpu_memory_gb": requirements["min_gpu_memory_gb"],
            "recommended_instance": requirements["recommended_instance"],
            "recommended_tp": requirements["recommended_tp"],
            "params_billions": round(params_billions, 1),
            "source": "custom"
        }

    return None


def select_from_list(items: list, prompt: str, name_key: str = "name", id_key: str = "id"):
    """交互式列表选择"""
    if not items:
        return None

    print(f"\n{prompt}")
    for i, item in enumerate(items, 1):
        name = item.get(name_key, "N/A")
        item_id = item.get(id_key, "N/A")
        extra = item.get("extra", "")
        print(f"  {i}. {item_id} - {name} {extra}")

    while True:
        try:
            choice = input("\n请输入序号 (或 'q' 退出): ").strip()
            if choice.lower() == 'q':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return items[idx]
            print("无效选择，请重试。")
        except ValueError:
            print("请输入数字。")


def get_ssh_connection_info(args) -> Optional[dict]:
    """获取 SSH 连接信息"""
    print("\n" + "=" * 60)
    print("SSH 连接配置")
    print("=" * 60)

    if args.host:
        host = args.host
    else:
        host = input("\n请输入 EC2 实例 IP 或域名: ").strip()
        if not host:
            print("错误: 必须提供主机地址")
            return None

    if args.username:
        username = args.username
    else:
        username = input(f"SSH 用户名 [默认: ec2-user]: ").strip() or "ec2-user"

    if args.key_file:
        key_file = args.key_file
    else:
        key_file = input("SSH 私钥文件路径: ").strip()
        if not key_file:
            print("错误: 必须提供 SSH 私钥文件")
            return None

    key_file = os.path.expanduser(key_file)
    if not os.path.exists(key_file):
        print(f"错误: 密钥文件不存在: {key_file}")
        return None

    if args.port:
        port = args.port
    else:
        port_str = input("SSH 端口 [默认: 22]: ").strip()
        port = int(port_str) if port_str else 22

    return {"host": host, "user": username, "key": key_file, "port": port}


def check_instance(ssh_info: dict) -> Optional[dict]:
    """检测实例可用性"""
    print("\n" + "=" * 60)
    print("检测实例配置...")
    print("=" * 60)

    try:
        checker = InstanceChecker(ssh_info["host"], ssh_info["user"], ssh_info["key"], ssh_info["port"])
        report = checker.run_all_checks()
        print_check_report(report)

        if not report["summary"]["ready_for_deployment"]:
            print("\n⚠ 实例存在问题，是否继续？")
            if input("继续部署? [y/N]: ").strip().lower() != 'y':
                return None

        return report

    except Exception as e:
        print(f"\n✗ 连接失败: {e}")
        return None


def select_model_source() -> Optional[str]:
    """让用户选择模型来源"""
    sources = [
        {"id": "trending", "name": "Trending Models (32B+ from HuggingFace)", "extra": ""},
        {"id": "custom", "name": "Custom Model ID (输入任意 HF 模型)", "extra": ""},
    ]
    selected = select_from_list(sources, "请选择模型来源:", "name", "id")
    return selected["id"] if selected else None


def select_model(args, gpu_count: int) -> Optional[dict]:
    """选择部署模型"""
    print("\n" + "=" * 60)
    print("选择部署模型")
    print("=" * 60)

    if args.model:
        model_config = get_model_config(args.model)
        if not model_config:
            print(f"错误: 无法获取模型 '{args.model}' 的配置")
            return None
        return model_config

    source = select_model_source()
    if not source:
        return None

    if source == "custom":
        print("\n请输入 HuggingFace 模型 ID (例如: 'Qwen/Qwen2.5-72B-Instruct'):")
        custom_id = input("Model ID: ").strip()
        if not custom_id:
            print("错误: 必须提供模型 ID")
            return None

        model_config = get_model_config(custom_id)
        if model_config:
            print(f"\n模型配置已生成:")
            print(f"  参数量: {model_config.get('params_billions', 'N/A')}B")
            print(f"  预估显存: {model_config['min_gpu_memory_gb']}GB")
            print(f"  推荐 TP: {model_config['recommended_tp']}")
            confirm = input("\n使用此配置? [Y/n]: ").strip().lower()
            if confirm == 'n':
                return None
        return model_config

    config = load_models_config()
    models = config.get("models", [])

    if not models:
        print("\n无法获取模型列表，请使用 Custom Model ID")
        return None

    suitable_models = []
    for m in models:
        rec_tp = m.get("recommended_tp", 1)
        suitable = "✓" if rec_tp <= gpu_count else "⚠"
        extra_parts = []
        if m.get("params_billions"):
            extra_parts.append(f"{m['params_billions']}B")
        extra_parts.append(f"TP={rec_tp}")
        if m.get("likes"):
            extra_parts.append(f"likes:{m['likes']}")

        suitable_models.append({
            "id": m["id"],
            "name": m["name"],
            "hf_model_id": m.get("hf_model_id", m["name"]),
            "extra": f"({suitable} {', '.join(extra_parts)})"
        })

    print(f"\n可用模型 (共 {len(suitable_models)} 个):")
    selected = select_from_list(suitable_models, "请选择要部署的模型:", "name", "id")
    if not selected:
        return None

    hf_id = selected.get("hf_model_id", "")
    return get_model_config(hf_id if "/" in hf_id else selected["id"], models)


def configure_deployment(args, model_config: dict, gpu_info: dict) -> dict:
    """配置部署参数"""
    print("\n" + "=" * 60)
    print("配置部署参数")
    print("=" * 60)

    config = {}

    if args.service_port:
        config["port"] = args.service_port
    else:
        port_str = input(f"服务端口 [默认: 30000]: ").strip()
        config["port"] = int(port_str) if port_str else 30000

    gpu_count = gpu_info.get("count", 1)
    recommended_tp = model_config.get("recommended_tp", 1)

    if args.tp:
        config["tp"] = args.tp
    else:
        print(f"\n检测到 {gpu_count} 个 GPU，模型推荐 TP={recommended_tp}")
        tp_str = input(f"Tensor Parallelism [默认: {min(recommended_tp, gpu_count)}]: ").strip()
        config["tp"] = int(tp_str) if tp_str else min(recommended_tp, gpu_count)

    if args.enable_monitoring is not None:
        config["enable_monitoring"] = args.enable_monitoring
    else:
        monitor = input("\n是否安装监控组件? [y/N]: ").strip().lower()
        config["enable_monitoring"] = monitor == 'y'

    if args.hf_token:
        config["hf_token"] = args.hf_token
    else:
        needs_token = "llama" in model_config["hf_model_id"].lower()
        if needs_token:
            print("\n该模型可能需要 HuggingFace Token")
        token = input("HuggingFace Token (可选): ").strip()
        if token:
            config["hf_token"] = token

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


def generate_install_script(model_config: dict, deploy_config: dict) -> str:
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
        success, stdout, stderr = ssh_script(host, user, key, generate_install_script(model_config, deploy_config), port, timeout=900)
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


def interactive_deploy(args):
    """交互式部署流程"""
    print("=" * 60)
    print("SGLang AWS Deployment - SSH 远程部署模式")
    print("=" * 60)

    # 1. 选择计算资源类型
    print("\n[1/6] 选择计算资源类型")
    resource_types = [
        {"id": "ec2", "name": "EC2 实例", "extra": "(当前支持)"},
        {"id": "hyperpod", "name": "Hyperpod 集群", "extra": "(即将支持)"}
    ]
    selected = select_from_list(resource_types, "请选择计算资源类型:", "name", "id")
    if not selected:
        print("部署取消。")
        return 1

    if selected["id"] == "hyperpod":
        print("\n⚠ Hyperpod 集群支持即将推出，请先使用 EC2 实例。")
        return 1

    # 2. 获取 SSH 连接信息
    print("\n[2/6] 获取 SSH 连接信息")
    ssh_info = get_ssh_connection_info(args)
    if not ssh_info:
        print("部署取消。")
        return 1

    # 3. 检测实例可用性
    print("\n[3/6] 检测实例可用性")
    report = check_instance(ssh_info)
    if not report:
        print("部署取消。")
        return 1

    gpu_info = report.get("gpu", {})
    gpu_count = gpu_info.get("count", 0)

    if gpu_count == 0:
        print("\n✗ 未检测到 GPU，无法部署 SGLang")
        return 1

    # 4. 选择部署模型
    print("\n[4/6] 选择部署模型")
    model_config = select_model(args, gpu_count)
    if not model_config:
        print("部署取消。")
        return 1

    print(f"\n已选择模型: {model_config['name']}")
    print(f"  HuggingFace ID: {model_config['hf_model_id']}")

    # 5. 配置部署参数
    print("\n[5/6] 配置部署参数")
    deploy_config = configure_deployment(args, model_config, gpu_info)

    # 6. 确认并执行部署
    print("\n" + "=" * 60)
    print("部署配置摘要")
    print("=" * 60)
    print(f"  主机: {ssh_info['host']}")
    print(f"  模型: {model_config['hf_model_id']}")
    print(f"  端口: {deploy_config['port']}")
    print(f"  TP: {deploy_config['tp']}")
    print("=" * 60)

    confirm = input("\n确认开始部署? [y/N]: ").strip().lower()
    if confirm != 'y':
        print("部署取消。")
        return 1

    success = execute_deployment(ssh_info, model_config, deploy_config)

    if success:
        print_deployment_summary(ssh_info, model_config, deploy_config)
        return 0
    else:
        print("\n✗ 部署失败，请检查日志")
        return 1


def main():
    import argparse

    parser = argparse.ArgumentParser(description="通过 SSH 在 EC2 实例上部署 SGLang")

    parser.add_argument("--host", type=str, help="EC2 实例 IP 或域名")
    parser.add_argument("--username", type=str, help="SSH 用户名")
    parser.add_argument("--key-file", type=str, help="SSH 私钥文件路径")
    parser.add_argument("--port", type=int, default=22, help="SSH 端口")

    parser.add_argument("--model", type=str, help="模型 ID")
    parser.add_argument("--service-port", type=int, help="SGLang 服务端口")
    parser.add_argument("--tp", type=int, help="Tensor Parallelism")
    parser.add_argument("--hf-token", type=str, help="HuggingFace Token")
    parser.add_argument("--enable-monitoring", action="store_true", help="安装监控组件")
    parser.add_argument("--no-monitoring", action="store_false", dest="enable_monitoring")

    parser.add_argument("--list-models", action="store_true", help="列出可用模型")

    args = parser.parse_args()

    if args.list_models:
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

    return interactive_deploy(args)


if __name__ == "__main__":
    sys.exit(main())
