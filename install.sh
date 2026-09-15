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

# gruvbox dark palette (truecolor)
GREEN='\033[38;2;184;187;38m'      # bright green  #b8bb26
YELLOW='\033[38;2;250;189;47m'     # bright yellow #fabd2f
AQUA='\033[38;2;142;192;124m'      # bright aqua   #8ec07c
RED='\033[38;2;251;73;52m'         # bright red    #fb4934
GRAY='\033[38;2;146;131;116m'      # gray          #928374
FG='\033[38;2;235;219;178m'        # fg            #ebdbb2
BG='\033[48;2;40;40;40m'           # bg            #282828
DIM='\033[2m'; RESET='\033[0m'
if [ ! -t 1 ]; then GREEN=''; YELLOW=''; AQUA=''; RED=''; GRAY=''; FG=''; BG=''; DIM=''; RESET=''; fi

say()  { printf '%b' "${GREEN}  >${RESET} $1\n"; }
die()  { printf '%s\n' "  error: $1" >&2; exit 1; }

printf '%b' "$(cat <<EOF
${BG}${YELLOW}  ░▀█▀░█▀▄░█▀█░█▀▄░▀█▀░█▀█░█▀▀░░░░░▀█▀░█░█░▀█▀${RESET}
${BG}${YELLOW}  ░░█░░█▀▄░█▀█░█░█░░█░░█░█░█░█░▄▄▄░░█░░█░█░░█░${RESET}
${BG}${YELLOW}  ░░▀░░▀░▀░▀░▀░▀▀░░▀▀▀░▀░▀░▀▀▀░░░░░░▀░░▀▀▀░▀▀▀${RESET}
${BG}${AQUA}  ╭────────────────────────────────────────────────────────╮${RESET}
${BG}${AQUA}  │${GREEN} trading-tui${GRAY}  ·  live market desk${YELLOW}      BTC-USD${FG}  \$95,431 ${AQUA}│${RESET}
${BG}${FG}  │                                                        │${RESET}
${BG}${AQUA}  │${FG}  ${GREEN}░▒▓█▓▒░▒▓█▓▒░▒▓█▓▒░▒▓${FG}  ${YELLOW}+2.14%${GRAY}   24h vol 12.4k${FG}         ${AQUA}│${RESET}
${BG}${FG}  │                                                        │${RESET}
${BG}${AQUA}  │${GRAY}  SYMBOL     LAST      Δ       ALERT            STATE   ${AQUA}│${RESET}
${BG}${AQUA}  │${YELLOW}  BTC-USD${FG}    95,431.2  ${GREEN}+2.14%${FG}  ${GRAY}crosses 90,000${FG}    ${GREEN}armed${FG}  ${AQUA}│${RESET}
${BG}${AQUA}  │${YELLOW}  ETH-USD${FG}     3,212.4  ${RED}-0.88%${FG}  ${GRAY}crosses  3,500${FG}    ${GREEN}armed${FG}  ${AQUA}│${RESET}
${BG}${AQUA}  │${YELLOW}  SOL-USD${FG}       189.6  ${GREEN}+1.06%${FG}  ${GRAY}rsi < 30${FG}          ${GRAY}idle${FG}   ${AQUA}│${RESET}
${BG}${FG}  │                                                        │${RESET}
${BG}${AQUA}  │${GRAY}  q quit · a add alert · f filter · ws live feed${FG}        ${AQUA}│${RESET}
${BG}${AQUA}  ╰────────────────────────────────────────────────────────╯${RESET}
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
  ${GREEN}  ready. run 'trading-tui' to open the desk.${RESET}

  ${DIM}  quickstart${RESET}
    trading-tui        TUI client (alerts console)
    trading-tui-api    FastAPI market-data server (:8333)

  ${DIM}  market data comes from the API — start it first:${RESET}
    cp $SRC_DIR/.env.example $SRC_DIR/.env
    cd $SRC_DIR && trading-tui-api & trading-tui

  ${DIM}  uninstall: rm -rf $PREFIX_DIR $BIN_DIR/trading-tui $BIN_DIR/trading-tui-api${RESET}
EOF
)"
