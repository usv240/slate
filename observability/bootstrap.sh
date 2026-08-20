#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl docker.io docker-compose-v2
systemctl enable --now docker
mkdir -p /opt/slate-observability
chmod 0750 /opt/slate-observability
