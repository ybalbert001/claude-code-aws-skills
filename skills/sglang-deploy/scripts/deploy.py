#!/usr/bin/env python3
"""
SGLang AWS Deployment Script

通过 SSH 在预先存在的 EC2 实例上部署 SGLang LLM 推理服务器。

工作流程:
1. 选择计算资源类型 (EC2 / Hyperpod)
2. 获取 SSH 连接信息
3. 检测实例可用性
4. 选择部署模型
5. 配置参数
6. 执行部署
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from ssh_executor import SSHExecutor
from instance_checker import InstanceChecker, print_check_report


def load_models_config():
    """加载模型配置"""
    script_dir = Path(__file__).parent
    models_file = script_dir.parent / "references" / "models.json"

    if models_file.exists():
        with open(models_file) as f:
            return json.load(f)
    return {"models": []}


def get_model_config(model_id: str):
    """获取指定模型的配置"""
    config = load_models_config()
    for model in config.get("models", []):
        if model["id"] == model_id:
            return model
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

    # 主机地址
    if args.host:
        host = args.host
    else:
        host = input("\n请输入 EC2 实例 IP 或域名: ").strip()
        if not host:
            print("错误: 必须提供主机地址")
            return None

    # 用户名
    if args.username:
        username = args.username
    else:
        username = input(f"SSH 用户名 [默认: ec2-user]: ").strip() or "ec2-user"

    # 密钥文件
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

    # 端口
    if args.port:
        port = args.port
    else:
        port_str = input("SSH 端口 [默认: 22]: ").strip()
        port = int(port_str) if port_str else 22

    return {
        "host": host,
        "username": username,
        "key_file": key_file,
        "port": port
    }


def check_instance(ssh_info: dict) -> Optional[dict]:
    """检测实例可用性"""
    print("\n" + "=" * 60)
    print("检测实例配置...")
    print("=" * 60)

    try:
        with SSHExecutor(**ssh_info) as executor:
            checker = InstanceChecker(executor)
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


def select_model(args, gpu_count: int) -> Optional[dict]:
    """选择部署模型"""
    print("\n" + "=" * 60)
    print("选择部署模型")
    print("=" * 60)

    config = load_models_config()
    models = config.get("models", [])

    if args.model:
        model_config = get_model_config(args.model)
        if not model_config:
            print(f"错误: 模型 '{args.model}' 未找到")
            print("可用模型:")
            for m in models:
                print(f"  - {m['id']}")
            return None
        return model_config

    # 根据 GPU 数量过滤和排序模型
    suitable_models = []
    for m in models:
        rec_tp = m.get("recommended_tp", 1)
        suitable = "✓" if rec_tp <= gpu_count else "⚠"
        suitable_models.append({
            "id": m["id"],
            "name": m["name"],
            "extra": f"({suitable} 推荐: {m['recommended_instance']}, TP={rec_tp})"
        })

    selected = select_from_list(suitable_models, "请选择要部署的模型:", "name", "id")
    if not selected:
        return None

    return get_model_config(selected["id"])


def configure_deployment(args, model_config: dict, gpu_info: dict) -> dict:
    """配置部署参数"""
    print("\n" + "=" * 60)
    print("配置部署参数")
    print("=" * 60)

    config = {}

    # 端口
    if args.port:
        config["port"] = args.port
    else:
        port_str = input(f"服务端口 [默认: 30000]: ").strip()
        config["port"] = int(port_str) if port_str else 30000

    # Tensor Parallelism
    gpu_count = gpu_info.get("count", 1)
    recommended_tp = model_config.get("recommended_tp", 1)

    if args.tp:
        config["tp"] = args.tp
    else:
        print(f"\n检测到 {gpu_count} 个 GPU，模型推荐 TP={recommended_tp}")
        tp_str = input(f"Tensor Parallelism [默认: {min(recommended_tp, gpu_count)}]: ").strip()
        config["tp"] = int(tp_str) if tp_str else min(recommended_tp, gpu_count)

    # 监控
    if args.enable_monitoring is not None:
        config["enable_monitoring"] = args.enable_monitoring
    else:
        monitor = input("\n是否安装监控组件 (Prometheus + Grafana)? [y/N]: ").strip().lower()
        config["enable_monitoring"] = monitor == 'y'

    # HuggingFace Token
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


def generate_install_script(model_config: dict, deploy_config: dict) -> str:
    """生成 SGLang 安装脚本"""
    hf_model_id = model_config["hf_model_id"]
    port = deploy_config.get("port", 30000)
    tp = deploy_config.get("tp", 1)
    hf_token = deploy_config.get("hf_token", "")

    script = f"""#!/bin/bash
set -ex

echo "=== 开始安装 SGLang ==="

# 设置 HuggingFace Token
{f'export HF_TOKEN="{hf_token}"' if hf_token else 'echo "No HuggingFace token provided"'}

# 升级 pip
pip install --upgrade pip

# 安装 uv (更快的包管理器)
pip install uv

# 安装 sglang
uv pip install "sglang[all]" || pip install "sglang[all]"

echo "=== SGLang 安装完成 ==="
"""
    return script


def generate_service_script(model_config: dict, deploy_config: dict) -> str:
    """生成 systemd 服务配置"""
    hf_model_id = model_config["hf_model_id"]
    port = deploy_config.get("port", 30000)
    tp = deploy_config.get("tp", 1)
    hf_token = deploy_config.get("hf_token", "")

    service_content = f"""[Unit]
Description=SGLang LLM Inference Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt
ExecStart=/usr/bin/python3 -m sglang.launch_server \\
    --model-path {hf_model_id} \\
    --host 0.0.0.0 \\
    --port {port} \\
    --tp {tp} \\
    --enable-metrics
Restart=on-failure
RestartSec=10
{f'Environment="HF_TOKEN={hf_token}"' if hf_token else ''}

[Install]
WantedBy=multi-user.target
"""
    return service_content


def generate_monitoring_script() -> str:
    """生成监控组件安装脚本"""
    return """#!/bin/bash
set -ex

echo "=== 安装监控组件 ==="

# 安装 Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    systemctl start docker
    systemctl enable docker
fi

# 安装 docker-compose
if ! command -v docker-compose &> /dev/null; then
    echo "Installing docker-compose..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi

# 创建监控目录
mkdir -p /opt/monitoring

# 创建 Prometheus 配置
cat > /opt/monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'sglang'
    static_configs:
      - targets: ['localhost:30000']
EOF

# 创建 docker-compose 配置
cat > /opt/monitoring/docker-compose.yml << 'EOF'
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    restart: unless-stopped
    network_mode: host

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
    restart: unless-stopped
    network_mode: host

volumes:
  prometheus_data:
  grafana_data:
EOF

# 启动监控栈
cd /opt/monitoring
docker-compose up -d

echo "=== 监控组件安装完成 ==="
echo "Grafana: http://localhost:3000 (admin/admin)"
echo "Prometheus: http://localhost:9090"
"""


def execute_deployment(ssh_info: dict, model_config: dict, deploy_config: dict) -> bool:
    """执行部署"""
    print("\n" + "=" * 60)
    print("执行部署")
    print("=" * 60)

    try:
        with SSHExecutor(**ssh_info) as executor:
            # 1. 安装 SGLang
            print("\n[1/4] 安装 SGLang...")
            install_script = generate_install_script(model_config, deploy_config)
            success, stdout, stderr = executor.execute_script(install_script, timeout=600)
            if not success:
                print(f"✗ SGLang 安装失败: {stderr}")
                return False
            print("✓ SGLang 安装完成")

            # 2. 配置 systemd 服务
            print("\n[2/4] 配置 systemd 服务...")
            service_content = generate_service_script(model_config, deploy_config)
            success, msg = executor.upload_content(service_content, "/etc/systemd/system/sglang.service")
            if not success:
                print(f"✗ 服务配置失败: {msg}")
                return False
            print("✓ 服务配置完成")

            # 3. 安装监控 (可选)
            if deploy_config.get("enable_monitoring"):
                print("\n[3/4] 安装监控组件...")
                monitoring_script = generate_monitoring_script()
                success, stdout, stderr = executor.execute_script(monitoring_script, timeout=300)
                if not success:
                    print(f"⚠ 监控安装失败 (非致命): {stderr}")
                else:
                    print("✓ 监控组件安装完成")
            else:
                print("\n[3/4] 跳过监控组件安装")

            # 4. 启动服务
            print("\n[4/4] 启动 SGLang 服务...")
            success, stdout, stderr = executor.execute("systemctl daemon-reload && systemctl enable sglang && systemctl start sglang")
            if not success:
                print(f"✗ 服务启动失败: {stderr}")
                return False

            # 等待服务启动
            print("等待服务启动...")
            time.sleep(10)

            # 检查服务状态
            success, stdout, stderr = executor.execute("systemctl is-active sglang")
            if stdout.strip() == "active":
                print("✓ SGLang 服务启动成功")
            else:
                print(f"⚠ 服务状态: {stdout.strip()}")
                print("  请检查日志: journalctl -u sglang -f")

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
    print("=" * 60)


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
    print(f"  推荐配置: {model_config['recommended_instance']}, TP={model_config['recommended_tp']}")

    # 5. 配置部署参数
    print("\n[5/6] 配置部署参数")
    deploy_config = configure_deployment(args, model_config, gpu_info)

    # 6. 确认并执行部署
    print("\n" + "=" * 60)
    print("部署配置摘要")
    print("=" * 60)
    print(f"  主机: {ssh_info['host']}")
    print(f"  用户: {ssh_info['username']}")
    print(f"  模型: {model_config['hf_model_id']}")
    print(f"  端口: {deploy_config['port']}")
    print(f"  TP: {deploy_config['tp']}")
    print(f"  监控: {'是' if deploy_config.get('enable_monitoring') else '否'}")
    print("=" * 60)

    confirm = input("\n确认开始部署? [y/N]: ").strip().lower()
    if confirm != 'y':
        print("部署取消。")
        return 1

    # 执行部署
    success = execute_deployment(ssh_info, model_config, deploy_config)

    if success:
        print_deployment_summary(ssh_info, model_config, deploy_config)
        return 0
    else:
        print("\n✗ 部署失败，请检查日志")
        return 1


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="通过 SSH 在 EC2 实例上部署 SGLang LLM 推理服务器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 交互式部署
  python deploy.py

  # 指定连接信息
  python deploy.py --host 10.0.1.100 --username ec2-user --key-file ~/.ssh/my-key.pem

  # 完整参数部署
  python deploy.py --host 10.0.1.100 --username ec2-user --key-file ~/.ssh/my-key.pem \\
    --model qwen2.5-7b --port 30000 --tp 1

  # 列出可用模型
  python deploy.py --list-models
        """
    )

    # SSH 连接参数
    parser.add_argument("--host", type=str, help="EC2 实例 IP 或域名")
    parser.add_argument("--username", type=str, help="SSH 用户名 (默认: ec2-user)")
    parser.add_argument("--key-file", type=str, help="SSH 私钥文件路径")
    parser.add_argument("--port", type=int, help="SSH 端口 (默认: 22)", dest="ssh_port")

    # 部署参数
    parser.add_argument("--model", type=str, help="模型 ID (见 --list-models)")
    parser.add_argument("--service-port", type=int, dest="port", help="SGLang 服务端口 (默认: 30000)")
    parser.add_argument("--tp", type=int, help="Tensor Parallelism (GPU 数量)")
    parser.add_argument("--hf-token", type=str, help="HuggingFace Token")
    parser.add_argument("--enable-monitoring", action="store_true", help="安装监控组件")
    parser.add_argument("--no-monitoring", action="store_false", dest="enable_monitoring", help="不安装监控组件")

    # 其他
    parser.add_argument("--list-models", action="store_true", help="列出可用模型")

    args = parser.parse_args()

    # 处理 SSH 端口参数
    if hasattr(args, 'ssh_port') and args.ssh_port:
        args.port_ssh = args.ssh_port
    else:
        args.port_ssh = 22

    # 重新映射端口参数
    original_port = args.port
    args.port = args.port_ssh  # SSH 端口
    if original_port:
        args.service_port = original_port

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

    return interactive_deploy(args)


if __name__ == "__main__":
    sys.exit(main())
