#!/usr/bin/env bash
set -Eeuo pipefail

# Installs Docker Engine + Docker Compose plugin + NVIDIA Container Toolkit.
# Does NOT reinstall the NVIDIA host driver.

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo: sudo bash $0"
  exit 1
fi

REAL_USER="${SUDO_USER:-${USER:-root}}"

if [[ ! -r /etc/os-release ]]; then
  echo "ERROR: /etc/os-release not found."
  exit 1
fi
. /etc/os-release

if [[ "${ID:-}" != "ubuntu" && "${ID_LIKE:-}" != *"debian"* ]]; then
  echo "WARNING: Intended for Ubuntu/Debian-derived systems. Detected: ${PRETTY_NAME:-unknown}"
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi is not installed. Install a working NVIDIA driver first."
  exit 1
fi
if ! nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: NVIDIA driver is not working. If it was just updated, reboot first."
  exit 1
fi

nvidia-smi -L

apt-get update
apt-get install -y ca-certificates curl gnupg

conflicts=(docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc)
installed_conflicts=()
for pkg in "${conflicts[@]}"; do
  if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed"; then
    installed_conflicts+=("$pkg")
  fi
done
if ((${#installed_conflicts[@]})); then
  apt-get remove -y "${installed_conflicts[@]}"
fi

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

UBUNTU_CODENAME="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
if [[ -z "$UBUNTU_CODENAME" ]]; then
  echo "ERROR: Could not determine Ubuntu codename."
  exit 1
fi

cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

if [[ "$REAL_USER" != "root" ]]; then
  usermod -aG docker "$REAL_USER"
fi

curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  > /etc/apt/sources.list.d/nvidia-container-toolkit.list

apt-get update
apt-get install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

docker --version
docker compose version
docker run --rm hello-world >/dev/null
docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu24.04 nvidia-smi

echo
echo "Host preparation completed successfully."
if [[ "$REAL_USER" != "root" ]]; then
  echo "Log out/in once or run: newgrp docker"
fi
