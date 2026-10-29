#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SYSTEMD_USER_DIR/gideon.service"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 não foi encontrado."
  exit 1
fi

echo "Instalando dependências do Zorin/Ubuntu..."
sudo apt update
sudo apt install -y \
  python3-venv python3-dev build-essential ffmpeg libportaudio2 portaudio19-dev \
  libsndfile1 libayatana-appindicator3-1 wmctrl xdotool pulseaudio-utils xdg-utils \
  libsecret-1-0 gnome-keyring

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -e "$ROOT_DIR"

mkdir -p "$HOME/.local/bin"
ln -sfn "$VENV_DIR/bin/gideon" "$HOME/.local/bin/gideon"
ln -sfn "$VENV_DIR/bin/gideonctl" "$HOME/.local/bin/gideonctl"

echo "Configurando o subsistema Gideon no systemd do usuário..."
mkdir -p "$SYSTEMD_USER_DIR" "$HOME/.local/share/gideon"
# Preserva memórias, automações e configurações criadas antes da migração.
if [[ -d "$ROOT_DIR/dados" ]]; then
  cp -an "$ROOT_DIR/dados/." "$HOME/.local/share/gideon/"
fi
sed \
  -e "s|@ROOT_DIR@|$ROOT_DIR|g" \
  -e "s|@PYTHON@|$VENV_DIR/bin/python|g" \
  "$ROOT_DIR/packaging/systemd/gideon.service.in" > "$SERVICE_FILE"

# Evita duas instâncias quando uma instalação anterior usava o autostart XDG.
rm -f "$HOME/.config/autostart/gideon.desktop"
if command -v dbus-update-activation-environment >/dev/null 2>&1; then
  dbus-update-activation-environment --systemd DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS || true
fi
systemctl --user daemon-reload
systemctl --user enable --now gideon.service

echo
echo "Instalação concluída."
echo "A Gideon já está ativa como subsistema do seu usuário."
echo "Abra com:   $HOME/.local/bin/gideon open"
echo "Estado:     systemctl --user status gideon.service"
echo "Logs:       journalctl --user -u gideon.service -f"
