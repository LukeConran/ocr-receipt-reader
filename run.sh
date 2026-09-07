#!/usr/bin/env bash
# Launch Receipt Scanner: check system deps, create .venv, install, run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

info() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

if ! command -v python3 >/dev/null 2>&1; then
  die "python3 not found. On a Mac: brew install python"
fi

PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
  || die "Python 3.10+ required (found ${PY_VER})"

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
  warn "tkinter is missing. On Homebrew Python: brew install python-tk"
  warn "The UI will not start until tkinter is available."
fi

if ! command -v tesseract >/dev/null 2>&1; then
  warn "tesseract not on PATH. OCR will fail unless Apple Vision is installed."
  warn "Install with:  brew install tesseract"
fi

VENV="${ROOT}/.venv"
if [[ ! -d "${VENV}" ]]; then
  info "Creating virtualenv at .venv"
  python3 -m venv "${VENV}"
fi

# shellcheck disable=SC1091
source "${VENV}/bin/activate"

info "Installing Python packages"
python -m pip install --upgrade pip -q
python -m pip install -e "${ROOT}" -q

mkdir -p "${ROOT}/data/captures"

info "Starting ${APP_NAME:-Receipt Scanner}"
exec python -m receipt_ocr "$@"
