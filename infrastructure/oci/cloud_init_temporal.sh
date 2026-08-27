#!/usr/bin/env bash
# ==============================================================================
# APEX SOVEREIGN CLOUD HORIZON: TEMPORAL 24/7 CLOUD SERVER PROVISIONER
# Target: Oracle Cloud Infrastructure (OCI) Ampere A1 (4 OCPU, 24GB RAM)
# OS: Ubuntu 22.04 / Oracle Linux 8
# Role: Host 24/7 Durable Temporal Workflow Engine & Webhook Endpoints
# ==============================================================================

set -euo pipefail

echo "=========================================================="
echo "⚡ PROVISIONING 24/7 TEMPORAL SOVEREIGN SERVER ON OCI"
echo "=========================================================="

# 1. Update and install prerequisites
export DEBIAN_FRONTEND=noninteractive
apt-get update -y && apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg lsb-release git jq ufw

# 2. Install Docker & Docker Compose
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable docker
systemctl start docker

# 3. Create Temporal Stack Directory
mkdir -p /opt/apex/temporal
cd /opt/apex/temporal

# 4. Write Docker Compose Stack (Temporal + Postgres + Web UI + Caddy)
cat << 'EOF' > docker-compose.yml
version: '3.8'

services:
  postgresql:
    image: postgres:15-alpine
    container_name: apex-temporal-postgresql
    environment:
      POSTGRES_USER: temporal
      POSTGRES_PASSWORD: temporal_master_password_apex
      POSTGRES_DB: temporal
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - temporal-network
    restart: unless-stopped

  temporal:
    image: temporalio/auto-setup:1.24.2
    container_name: apex-temporal-server
    depends_on:
      - postgresql
    environment:
      - DB=postgresql
      - DB_PORT=5432
      - POSTGRES_USER=temporal
      - POSTGRES_PWD=temporal_master_password_apex
      - POSTGRES_SEEDS=postgresql
      - DYNAMIC_CONFIG_FILE_PATH=config/dynamicconfig/development-sql.yaml
    ports:
      - "7233:7233" # Temporal gRPC frontend
    networks:
      - temporal-network
    restart: unless-stopped

  temporal-ui:
    image: temporalio/ui:2.26.2
    container_name: apex-temporal-ui
    depends_on:
      - temporal
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - TEMPORAL_CORS_ORIGINS=http://localhost:3000
    ports:
      - "8080:8080" # Web UI
    networks:
      - temporal-network
    restart: unless-stopped

volumes:
  postgres_data:

networks:
  temporal-network:
    driver: bridge
EOF

# 5. Launch Stack
docker compose up -d

# 6. Configure Firewall (UFW)
ufw allow 22/tcp   # SSH
ufw allow 7233/tcp # Temporal gRPC
ufw allow 8080/tcp # Temporal Web UI
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw --force enable

echo "=========================================================="
echo "🟢 APEX 24/7 TEMPORAL SERVER LAUNCHED SUCCESSFULLY"
echo "  gRPC Endpoint : localhost:7233"
echo "  Web Console   : http://localhost:8080"
echo "=========================================================="
