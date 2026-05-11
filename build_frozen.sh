#!/bin/bash
set -euo pipefail

# Build a frozen executable for the current Linux target.
# IMPORTANT: Build on the same architecture/OS family as the gateway target.

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${APP_DIR}/.venv-build"
PYTHON_BIN="python3"
ARCH="$(uname -m 2>/dev/null || echo unknown)"

echo "[build] app dir: ${APP_DIR}"
echo "[build] detected arch: ${ARCH}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[build] ERROR: python3 is required"
  exit 1
fi

if ! "${PYTHON_BIN}" -m pip --version >/dev/null 2>&1; then
  echo "[build] ERROR: python3 pip is required (python3-pip)."
  exit 1
fi

# PyInstaller's build backend calls `ldd` during metadata generation.
# Some minimal gateway images only provide musl-ldd, not ldd.
if ! command -v ldd >/dev/null 2>&1; then
  SHIM_BIN_DIR="${APP_DIR}/.shim-bin"
  mkdir -p "${SHIM_BIN_DIR}"
  if command -v musl-ldd >/dev/null 2>&1; then
    cat > "${SHIM_BIN_DIR}/ldd" <<'EOF'
#!/bin/sh
exec musl-ldd "$@"
EOF
    chmod +x "${SHIM_BIN_DIR}/ldd"
    export PATH="${SHIM_BIN_DIR}:${PATH}"
    echo "[build] ldd not found; using musl-ldd shim"
  else
    # Last-resort shim for minimal images with neither ldd nor musl-ldd.
    # This is enough for PyInstaller's platform checks and often sufficient
    # for Python-only apps on embedded targets.
    cat > "${SHIM_BIN_DIR}/ldd" <<'EOF'
#!/bin/sh
if [ $# -eq 0 ]; then
  # PyInstaller checks stderr for "musl" to detect libc flavor.
  echo "musl libc (ldd shim)" 1>&2
  exit 0
fi
# Fallback response for dependency probes on static/minimal binaries.
echo "$1:"
echo "not a dynamic executable"
exit 0
EOF
    chmod +x "${SHIM_BIN_DIR}/ldd"
    export PATH="${SHIM_BIN_DIR}:${PATH}"
    echo "[build] ldd/musl-ldd not found; using fallback ldd shim"
    echo "[build] NOTE: If build later fails on binary dependency analysis, build on a fuller Linux host."
  fi
fi

USE_VENV=0
if "${PYTHON_BIN}" -m venv --help >/dev/null 2>&1; then
  USE_VENV=1
fi

if [ "${USE_VENV}" -eq 1 ]; then
  echo "[build] venv available; using isolated build env"
  if [ ! -d "${VENV_DIR}" ]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi

  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
  PYTHON_RUN="python"
  PIP_RUN="python -m pip"
else
  echo "[build] venv module not available; falling back to --user install"
  PYTHON_RUN="${PYTHON_BIN}"
  PIP_RUN="${PYTHON_BIN} -m pip"
  export PATH="${HOME}/.local/bin:${PATH}"
fi

${PIP_RUN} install --upgrade pip
${PIP_RUN} install -r "${APP_DIR}/requirements.txt"

# Do not allow source builds (they require gcc/clang to compile bootloader).
# On ARMv7, try a few versions that are more likely to have usable wheels.
install_pyinstaller_wheel() {
  local ver="$1"
  echo "[build] trying prebuilt pyinstaller==${ver}"
  if [ "${USE_VENV}" -eq 1 ]; then
    ${PIP_RUN} install --only-binary=:all: --no-build-isolation "pyinstaller==${ver}" && return 0
  else
    ${PIP_RUN} install --user --only-binary=:all: --no-build-isolation "pyinstaller==${ver}" && return 0
  fi
  return 1
}

if [ -n "${PYINSTALLER_VERSION:-}" ]; then
  if ! install_pyinstaller_wheel "${PYINSTALLER_VERSION}"; then
    echo "[build] ERROR: no prebuilt wheel available for pyinstaller==${PYINSTALLER_VERSION} on this platform."
    exit 1
  fi
else
  case "${ARCH}" in
    armv7l|armv6l|armhf)
      PYI_CANDIDATES="5.13.2 5.11.0 5.8.0"
      ;;
    *)
      PYI_CANDIDATES="6.11.1 6.8.0 5.13.2"
      ;;
  esac
  FOUND=0
  for ver in ${PYI_CANDIDATES}; do
    if install_pyinstaller_wheel "${ver}"; then
      PYINSTALLER_VERSION="${ver}"
      FOUND=1
      break
    fi
  done
  if [ "${FOUND}" -ne 1 ]; then
    echo "[build] ERROR: could not find a prebuilt PyInstaller wheel for ${ARCH}."
    echo "[build] This device lacks a C compiler, so source build is not possible."
    echo "[build] Use one of these options:"
    echo "[build]   1) Build on another Linux ARMv7 host that has a compatible wheel/toolchain."
    echo "[build]   2) Install a compiler toolchain (gcc, libc-dev, make) and allow source build."
    exit 1
  fi
fi
echo "[build] using pyinstaller==${PYINSTALLER_VERSION}"

cd "${APP_DIR}"
${PYTHON_RUN} -m PyInstaller --clean --noconfirm "RadioBridgeTools.spec"

OUT_BIN="${APP_DIR}/dist/RadioBridgeTools/RadioBridgeTools"
if [ ! -f "${OUT_BIN}" ]; then
  echo "[build] ERROR: expected output not found: ${OUT_BIN}"
  exit 1
fi

# Copy binary to repo root so Start/Install will auto-detect it.
cp -f "${OUT_BIN}" "${APP_DIR}/RadioBridgeTools"
chmod +x "${APP_DIR}/RadioBridgeTools"

echo "[build] done"
echo "[build] binary: ${APP_DIR}/RadioBridgeTools"
echo "[build] include this file when packaging the app tar.gz"
