#!/bin/sh
# trading-tui installer
# example:
#   curl -fsSL https://raw.githubusercontent.com/corderkrow/trading-tui/main/install.sh | sh
#
# Installs the TUI client + FastAPI backend into ~/.local/share/trading-tui
# and links the `trading-tui` / `trading-tui-api` commands into ~/.local/bin.
# Override destinations:  PREFIX_DIR=... BIN_DIR=... sh install.sh

set -eu

REPO="https://github.com/corderkrow/trading-tui.git"
PREFIX_DIR="${PREFIX_DIR:-$HOME/.local/share/trading-tui}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
SRC_DIR="$PREFIX_DIR/src"
VENV_DIR="$PREFIX_DIR/venv"

# coderkrow brand palette — dark variant (truecolor)
# tokens per .ai/rules/brand/RULES.md §2, matching tui_client/themes.py
TEAL_LIGHT='\033[38;2;59;184;186m'  # #3bb8ba — accents, highlights, success
TEAL_MID='\033[38;2;46;127;128m'    # #2e7f80 — interactive chrome, borders
CYAN='\033[38;2;0;209;212m'         # #00d1d4 — signal only: active/on, focus
DANGER='\033[38;2;200;60;60m'       # #c83c3c — errors, down deltas
MUTED='\033[38;2;136;135;128m'      # #888780 — secondary text, captions
FG='\033[38;2;232;230;223m'         # #e8e6df — ink, primary text
BG='\033[48;2;17;17;16m'            # #111110 — bg, near-black (never #000)
DIM='\033[2m'; RESET='\033[0m'
if [ ! -t 1 ]; then
  TEAL_LIGHT=''; TEAL_MID=''; CYAN=''; DANGER=''; MUTED=''; FG=''; BG=''; DIM=''; RESET=''
fi

say()  { printf '%b' "${TEAL_MID}  >${RESET} $1\n"; }
die()  { printf '%b\n' "  ${DANGER}error:${RESET} $1" >&2; exit 1; }

printf '%b' "$(cat <<EOF
${BG}${TEAL_LIGHT}  ░▀█▀░█▀▄░█▀█░█▀▄░▀█▀░█▀█░█▀▀░░░░░▀█▀░█░█░▀█▀${RESET}
${BG}${TEAL_LIGHT}  ░░█░░█▀▄░█▀█░█░█░░█░░█░█░█░█░▄▄▄░░█░░█░█░░█░${RESET}
${BG}${TEAL_LIGHT}  ░░▀░░▀░▀░▀░▀░▀▀░░▀▀▀░▀░▀░▀▀▀░░░░░░▀░░▀▀▀░▀▀▀${RESET}
${BG}${TEAL_MID}  ╭────────────────────────────────────────────────────────╮${RESET}
${BG}${TEAL_MID}  │${TEAL_LIGHT} trading-tui${MUTED}  ·  live market desk${MUTED}      BTC-USD${FG}  \$95,431 ${TEAL_MID}│${RESET}
${BG}${TEAL_MID}  │                                                        │${RESET}
${BG}${TEAL_MID}  │${FG}  ${TEAL_LIGHT}░▒▓█▓▒░▒▓█▓▒░▒▓█▓▒░▒▓${TEAL_LIGHT}  +2.14%${MUTED}   24h vol 12.4k${FG}         ${TEAL_MID}│${RESET}
${BG}${TEAL_MID}  │                                                        │${RESET}
${BG}${TEAL_MID}  │${MUTED}  SYMBOL     LAST      Δ       ALERT            STATE   ${TEAL_MID}│${RESET}
${BG}${TEAL_MID}  │${TEAL_LIGHT}  BTC-USD${FG}    95,431.2  ${TEAL_LIGHT}+2.14%${FG}  ${MUTED}crosses 90,000${FG}    ${CYAN}armed${FG}  ${TEAL_MID}│${RESET}
${BG}${TEAL_MID}  │${TEAL_LIGHT}  ETH-USD${FG}     3,212.4  ${DANGER}-0.88%${FG}  ${MUTED}crosses  3,500${FG}    ${CYAN}armed${FG}  ${TEAL_MID}│${RESET}
${BG}${TEAL_MID}  │${TEAL_LIGHT}  SOL-USD${FG}       189.6  ${TEAL_LIGHT}+1.06%${FG}  ${MUTED}rsi < 30${FG}          ${MUTED}idle${FG}   ${TEAL_MID}│${RESET}
${BG}${TEAL_MID}  │                                                        │${RESET}
${BG}${TEAL_MID}  │${MUTED}  ${CYAN}q${MUTED} quit · ${CYAN}a${MUTED} add alert · ${CYAN}f${MUTED} filter · ${CYAN}ws${MUTED} live feed${FG}        ${TEAL_MID}│${RESET}
${BG}${TEAL_MID}  ╰────────────────────────────────────────────────────────╯${RESET}
EOF
)"
printf '\n\n'

# ---------------------------------------------------------------- detect
OS="$(uname -s 2>/dev/null || echo unknown)"
ARCH="$(uname -m 2>/dev/null || echo unknown)"
case "$OS" in
  Linux)  OS="linux"  ;;
  Darwin) OS="macos"  ;;
  *)      die "unsupported os: $OS" ;;
esac
case "$ARCH" in
  x86_64|amd64)      ARCH="x86_64" ;;
  aarch64|arm64)     ARCH="arm64"  ;;
  *)                 die "unsupported arch: $ARCH" ;;
esac

PY=""
command -v python3 >/dev/null 2>&1 && PY="python3"
[ -z "$PY" ] && command -v python >/dev/null 2>&1 && PY="python"
[ -z "$PY" ] && die "python 3.12+ not found (install python or uv first)."
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  die "python >= 3.12 required (found $("$PY" --version 2>&1))."
fi
command -v git >/dev/null 2>&1 || die "git not found."

say "detected $OS/$ARCH · $("$PY" --version 2>&1 | cut -d' ' -f2)"

# ------------------------------------------------------------------ fetch
if [ -d "$SRC_DIR/.git" ]; then
  say "updating existing install in $PREFIX_DIR"
  git -C "$SRC_DIR" pull --ff-only --quiet || die "could not update $SRC_DIR"
else
  say "fetching trading-tui source..."
  mkdir -p "$PREFIX_DIR"
  git clone --quiet "$REPO" "$SRC_DIR" || die "git clone failed: $REPO"
fi
VERSION="$(git -C "$SRC_DIR" describe --tags --always 2>/dev/null || echo dev)"
say "checking out $VERSION"

# --------------------------------------------------------------- install
if [ ! -x "$VENV_DIR/bin/python" ]; then
  say "creating virtualenv..."
  "$PY" -m venv "$VENV_DIR" \
    || die "venv failed. on debian/ubuntu install 'python3-venv', or use 'uv venv'."
fi
say "installing python dependencies..."
"$VENV_DIR/bin/python" -m pip install --quiet --disable-pip-version-check --editable "$SRC_DIR"

# --------------------------------------------------------------- link
mkdir -p "$BIN_DIR"
for entry in trading-tui trading-tui-api; do
  ln -sfn "$VENV_DIR/bin/$entry" "$BIN_DIR/$entry"
done
say "installed trading-tui $VERSION to $BIN_DIR/trading-tui"

# ----------------------------------------------------------------- ready
if ! printf '%s' "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
  say "add $BIN_DIR to your PATH:  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

printf '\n'
printf '%b' "$(cat <<EOF
  ${TEAL_LIGHT}  ready.${RESET} run '${TEAL_LIGHT}trading-tui${RESET}' to open the desk.

  ${MUTED}  quickstart${RESET}
    ${TEAL_LIGHT}trading-tui${RESET}        TUI client (alerts console)
    ${TEAL_LIGHT}trading-tui-api${RESET}    FastAPI market-data server (:8333)

  ${MUTED}  market data comes from the API — start it first:${RESET}
    ${FG}cp $SRC_DIR/.env.example $SRC_DIR/.env${RESET}
    ${FG}cd $SRC_DIR && trading-tui-api & trading-tui${RESET}

  ${MUTED}  uninstall: rm -rf $PREFIX_DIR $BIN_DIR/trading-tui $BIN_DIR/trading-tui-api${RESET}
EOF
)"
