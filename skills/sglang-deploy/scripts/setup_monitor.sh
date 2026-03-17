#!/bin/bash

set -ex

# 安装 Docker
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo systemctl enable docker
    sudo systemctl start docker
    sudo usermod -aG docker $USER
fi

# 安装 docker-compose (v2 plugin 优先)
if ! docker compose version &> /dev/null; then
    sudo mkdir -p /usr/local/lib/docker/cli-plugins
    sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
fi

# 从 GitHub 拉取官方监控配置
MONITORING_DIR="$HOME/sglang-monitoring"
if [ -d "$MONITORING_DIR" ]; then
    cd "$MONITORING_DIR" && git pull
else
    git clone --depth 1 --filter=blob:none --sparse \
        https://github.com/sgl-project/sglang.git "$MONITORING_DIR"
    cd "$MONITORING_DIR"
    git sparse-checkout set examples/monitoring
fi

# 进入监控目录
cd "$MONITORING_DIR/examples/monitoring"

# 启动监控服务
docker compose up -d

echo "Monitoring started!"
echo "Grafana: http://localhost:3000 (anonymous access enabled)"
echo "Prometheus: http://localhost:9090"