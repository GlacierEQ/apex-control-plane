#!/bin/bash
# Always Free Ampere A1 (2 OCPU / 12 GB) Buildkite survivor — no exhibits, no PAYG.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl git jq python3 python3-venv python3-pip python3-pytest \
  clang make gcc rsync ufw
# Go via distro if present
apt-get install -y golang-go || true
ufw allow OpenSSH || true
# rustup for engine proofs (noninteractive)
if ! command -v rustc >/dev/null 2>&1; then
  su - ubuntu -c 'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y' || true
fi
install -d -o ubuntu -g ubuntu /home/ubuntu/work
echo "ampere-runner-ready $(date -u +%FT%TZ) $(uname -m)" > /home/ubuntu/work/ampere-ready.txt
chown ubuntu:ubuntu /home/ubuntu/work/ampere-ready.txt
