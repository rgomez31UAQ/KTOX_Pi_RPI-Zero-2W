#!/usr/bin/env bash
# Install PyBoy 2.x Game Boy emulator for KTOx (Raspberry Pi / ARM)
# Usage: sudo bash scripts/install_pyboy.sh
#
# PyBoy 2.x (latest: 2.7.0) provides pre-built ARM wheels:
#   armv7l  — available on piwheels.org (auto-configured in Pi OS /etc/pip.conf)
#   aarch64 — available directly on PyPI
# No Cython compilation needed when wheels are available.
#
# pip method order:
#   1. Plain pip install  (works on Raspberry Pi OS — piwheels auto-configured)
#   2. Explicit piwheels  (for custom/Ubuntu Pi images without /etc/pip.conf)
#   3. PyPI binary-only   (aarch64 and other arches with PyPI wheels)
#   4. No-build-isolation (uses system cython3 — avoids downloading Cython)

set -e

info() { printf "\e[1;32m[INFO]\e[0m %s\n" "$*"; }
warn() { printf "\e[1;33m[WARN]\e[0m %s\n" "$*"; }
err()  { printf "\e[1;31m[ERR ]\e[0m %s\n" "$*"; exit 1; }

ARCH=$(uname -m)
info "Architecture: $ARCH"
info "Python: $(python3 --version 2>&1)"

# ---------------------------------------------------------------------------
# 1. Free disk space — Cython source build needs ~200 MB in /tmp
# ---------------------------------------------------------------------------
info "Freeing disk space..."
pip3 cache purge 2>/dev/null || true
apt-get clean    2>/dev/null || true
rm -rf /tmp/pip-* /tmp/cc*.s 2>/dev/null || true

AVAIL=$(df /tmp --output=avail -BM 2>/dev/null | tail -1 | tr -d 'M ' || echo 0)
if [ -n "$AVAIL" ] && [ "$AVAIL" -lt 150 ]; then
    warn "Low /tmp space (${AVAIL}MB) — redirecting build dir to /var/tmp"
    export TMPDIR=/var/tmp
    mkdir -p "$TMPDIR"
fi

# ---------------------------------------------------------------------------
# 2. System libraries
#    libsdl2-2.0-0    — SDL2 runtime (pyboy links it even in null-window mode)
#    libatlas-base-dev — BLAS for numpy on ARM (needed for pip-built numpy)
#    python3-numpy    — try apt numpy first (pre-built, no compilation)
# ---------------------------------------------------------------------------
info "Installing system dependencies..."
apt-get install -y --no-install-recommends \
    libsdl2-2.0-0 libatlas-base-dev python3-numpy \
  || warn "Some apt packages unavailable — pip will provide them"

# ---------------------------------------------------------------------------
# 3. pip install — try methods in order, stop at first success
# ---------------------------------------------------------------------------
INSTALLED=0
PREFER="--prefer-binary"
BREAK="--break-system-packages"
PIWHLS="--extra-index-url https://www.piwheels.org/simple"

# Method 1: plain pip — Pi OS /etc/pip.conf already points to piwheels
info "Method 1: pip3 install pyboy (Pi OS piwheels auto-config)..."
if pip3 install $PREFER $BREAK "pyboy>=2.0" 2>/dev/null; then
    info "Installed (method 1)"
    INSTALLED=1

# Method 2: explicit piwheels URL — for Ubuntu/custom Pi images
elif pip3 install $PREFER $PIWHLS $BREAK "pyboy>=2.0" 2>/dev/null; then
    info "Installed (method 2: explicit piwheels)"
    INSTALLED=1

# Method 3: PyPI binary-only — aarch64 wheels are on PyPI for 2.7.0+
elif pip3 install --only-binary=:all: $BREAK "pyboy>=2.0" 2>/dev/null; then
    info "Installed (method 3: PyPI binary-only)"
    INSTALLED=1

# Method 4: no-build-isolation with system cython (avoids downloading Cython)
else
    info "Binary wheel not found. Trying source build with system cython..."
    apt-get install -y --no-install-recommends \
        libsdl2-dev python3-dev cython3 \
      || warn "Dev packages unavailable"

    if pip3 install $BREAK --no-build-isolation "pyboy>=2.0" 2>/dev/null; then
        info "Installed (method 4: system cython)"
        INSTALLED=1
    elif pip3 install --no-build-isolation "pyboy>=2.0" 2>/dev/null; then
        info "Installed (method 4b: system cython, no break-flag)"
        INSTALLED=1
    fi
fi

if [ "$INSTALLED" -eq 0 ]; then
    err "All install methods failed.
Check disk space (df -h) then try manually:
  pip3 install --prefer-binary --extra-index-url https://www.piwheels.org/simple pyboy"
fi

# ---------------------------------------------------------------------------
# 4. Ensure numpy is importable (pyboy.screen.image needs it)
# ---------------------------------------------------------------------------
if ! python3 -c "import numpy" 2>/dev/null; then
    warn "numpy not found — attempting pip install..."
    pip3 install $PREFER $PIWHLS $BREAK numpy 2>/dev/null \
      || pip3 install $PREFER numpy 2>/dev/null \
      || warn "numpy install failed — screen features may not work"
fi

# ---------------------------------------------------------------------------
# 5. ROMs directory
# ---------------------------------------------------------------------------
mkdir -p /root/KTOx/roms

# ---------------------------------------------------------------------------
# 6. Verify — import and print version
# ---------------------------------------------------------------------------
if python3 - <<'EOF'
from pyboy import PyBoy
import importlib.metadata
v = importlib.metadata.version("pyboy")
print(f"[OK] PyBoy {v} installed and importable")
EOF
then
    info "Verification passed."
else
    err "PyBoy import check failed after install.
Run: python3 -c \"from pyboy import PyBoy; print('ok')\""
fi

info "Done! Place .gb / .gbc ROMs in /root/KTOx/roms/"
