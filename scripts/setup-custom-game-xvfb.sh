#!/usr/bin/env bash
# Rootless Debian Xvfb setup for the managed Linux cloud executor.
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD/work/xvfb"
mkdir -p "$root/apt/lists/partial" "$root/apt/cache/archives/partial"
cat > "$root/apt/sources.list" <<'EOF'
deb https://deb.debian.org/debian trixie main
deb https://deb.debian.org/debian trixie-updates main
deb https://security.debian.org/debian-security trixie-security main
EOF
cat > "$root/apt/apt.conf" <<'EOF'
#clear APT::Update::Post-Invoke;
#clear APT::Update::Post-Invoke-Success;
EOF
apt_options=(-c "$root/apt/apt.conf" -o "Dir::Etc::sourcelist=$root/apt/sources.list" -o Dir::Etc::sourceparts=- -o "Dir::State::lists=$root/apt/lists" -o "Dir::Cache=$root/apt/cache")
apt-get "${apt_options[@]}" update
cd "$root/apt/cache/archives"
apt-get "${apt_options[@]}" download 'xvfb=2:21.1.16-1.3+deb13u4' 'xserver-common=2:21.1.16-1.3+deb13u4' 'libxfont2=1:2.0.6-1+deb13u1'
for package in *.deb; do dpkg-deb -x "$package" "$root"; done
