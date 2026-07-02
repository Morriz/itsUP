#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ── Guard: canonical checkout only ───────────────────────────────────────────
# This binds global state to REPO_ROOT — the `~/.local/bin/itsup` symlink and
# the editable install. Run from a linked git worktree (`.git` is a file, not a
# directory) it would repoint the global `itsup` at that worktree's transient
# venv. Refuse anywhere but the canonical checkout.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "${REPO_ROOT}/.git" ]; then
    echo -e "${RED}✗ Refusing: run 'make install' from the canonical itsUP checkout, not a linked worktree.${NC}" >&2
    echo -e "  here: ${REPO_ROOT} (this is a git worktree)" >&2
    echo -e "  It binds the global ~/.local/bin/itsup symlink; from a worktree that points at a transient venv." >&2
    exit 1
fi

echo -e "${BLUE}🔍 Detecting platform...${NC}"

# Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     PLATFORM=Linux;;
    Darwin*)    PLATFORM=Mac;;
    *)          PLATFORM="UNKNOWN:${OS}"
esac

# Detect architecture
ARCH="$(uname -m)"
case "${ARCH}" in
    x86_64)     ARCH_SOPS_DIFF="amd64";;
    aarch64)    ARCH_SOPS_DIFF="arm64";;
    arm64)      ARCH_SOPS_DIFF="arm64";;
    *)          ARCH_SOPS_DIFF="${ARCH}";;
esac

echo -e "${GREEN}✓${NC} Detected: ${PLATFORM} (${ARCH})"
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# True inside a Docker container. Containers often run as root with no `sudo`
# command, so privileged commands inside them must omit sudo.
is_container() {
    [ -f /.dockerenv ] || [ -n "${CONTAINER:-}" ]
}

# Install dependencies based on platform
if [ "$PLATFORM" = "Mac" ]; then
    echo -e "${BLUE}📦 Installing macOS dependencies...${NC}"

    # Check Homebrew
    if ! command_exists brew; then
        echo -e "${RED}✗${NC} Homebrew not found"
        echo "  Install from: https://brew.sh"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Homebrew installed"

    # Docker
    if ! command_exists docker; then
        echo -e "${YELLOW}  ⬇️  Installing Docker...${NC}"
        brew install --cask docker
        echo -e "${GREEN}✓${NC} Docker installed"
    else
        echo -e "${GREEN}✓${NC} Docker already installed"
    fi

    # SOPS
    if ! command_exists sops; then
        echo -e "${YELLOW}  ⬇️  Installing SOPS...${NC}"
        brew install sops
        echo -e "${GREEN}✓${NC} SOPS installed"
    else
        echo -e "${GREEN}✓${NC} SOPS already installed"
    fi

    # age (for SOPS encryption)
    if ! command_exists age; then
        echo -e "${YELLOW}  ⬇️  Installing age (for SOPS encryption)...${NC}"
        brew install age
        echo -e "${GREEN}✓${NC} age installed"
    else
        echo -e "${GREEN}✓${NC} age already installed"
    fi

    # sops-diff (for meaningful diffs)
    if ! command_exists sops-diff; then
        echo -e "${YELLOW}  ⬇️  Installing sops-diff...${NC}"
        SOPS_DIFF_VERSION=$(curl -s https://api.github.com/repos/saltydogtechnology/sops-diff/releases/latest | grep tag_name | cut -d '"' -f 4)
        curl -L "https://github.com/saltydogtechnology/sops-diff/releases/download/${SOPS_DIFF_VERSION}/sops-diff-${SOPS_DIFF_VERSION}-darwin-${ARCH_SOPS_DIFF}.tar.gz" | tar xz
        sudo mv sops-diff-darwin-${ARCH_SOPS_DIFF} /usr/local/bin/sops-diff
        echo -e "${GREEN}✓${NC} sops-diff installed"
    else
        echo -e "${GREEN}✓${NC} sops-diff already installed"
    fi

elif [ "$PLATFORM" = "Linux" ]; then
    echo -e "${BLUE}📦 Installing Linux dependencies...${NC}"

    # Docker (skip check if running in container - e.g., during tests)
    if is_container; then
        echo -e "${YELLOW}⚠${NC} Running in container - skipping Docker check"
    elif ! command_exists docker; then
        echo -e "${RED}✗${NC} Docker not found"
        echo "  Install from: https://docs.docker.com/engine/install/"
        exit 1
    else
        echo -e "${GREEN}✓${NC} Docker installed"
    fi

    # SOPS
    if ! command_exists sops; then
        echo -e "${YELLOW}  ⬇️  Installing SOPS...${NC}"
        SOPS_VERSION=$(curl -s https://api.github.com/repos/getsops/sops/releases/latest | grep tag_name | cut -d '"' -f 4 | cut -c 2-)

        # Determine architecture for sops binary
        case "${ARCH}" in
            x86_64)     SOPS_ARCH="amd64";;
            aarch64)    SOPS_ARCH="arm64";;
            arm64)      SOPS_ARCH="arm64";;
            *)          SOPS_ARCH="amd64";;
        esac

        if is_container; then SUDO=""; else SUDO="sudo"; fi

        # Download binary directly (more reliable than .deb for arm64)
        SOPS_URL="https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.linux.${SOPS_ARCH}"
        echo "  Downloading from: $SOPS_URL"
        if wget -O /tmp/sops "$SOPS_URL"; then
            $SUDO mv /tmp/sops /usr/local/bin/sops
            $SUDO chmod +x /usr/local/bin/sops
            echo -e "${GREEN}✓${NC} SOPS installed"
        else
            echo -e "${RED}✗${NC} Failed to download SOPS"
            echo "  URL: $SOPS_URL"
            exit 1
        fi
    else
        echo -e "${GREEN}✓${NC} SOPS already installed"
    fi

    # age
    if ! command_exists age; then
        echo -e "${YELLOW}  ⬇️  Installing age...${NC}"

        if is_container; then SUDO=""; else SUDO="sudo"; fi

        $SUDO apt-get update
        $SUDO apt-get install -y age
        echo -e "${GREEN}✓${NC} age installed"
    else
        echo -e "${GREEN}✓${NC} age already installed"
    fi

    # sops-diff (for meaningful diffs)
    if ! command_exists sops-diff; then
        echo -e "${YELLOW}  ⬇️  Installing sops-diff...${NC}"

        if is_container; then SUDO=""; else SUDO="sudo"; fi

        SOPS_DIFF_VERSION=$(curl -s https://api.github.com/repos/saltydogtechnology/sops-diff/releases/latest | grep tag_name | cut -d '"' -f 4)
        curl -L "https://github.com/saltydogtechnology/sops-diff/releases/download/${SOPS_DIFF_VERSION}/sops-diff-${SOPS_DIFF_VERSION}-linux-${ARCH_SOPS_DIFF}.tar.gz" | tar xz
        $SUDO mv sops-diff-linux-${ARCH_SOPS_DIFF} /usr/local/bin/sops-diff
        echo -e "${GREEN}✓${NC} sops-diff installed"
    else
        echo -e "${GREEN}✓${NC} sops-diff already installed"
    fi

else
    echo -e "${RED}✗${NC} Unsupported platform: ${PLATFORM}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ System dependencies installed${NC}"
echo ""

# Python environment setup
echo -e "${BLUE}🐍 Setting up Python environment...${NC}"

# Create Python virtual environment if needed
if [ ! -d .venv ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
    echo -e "${GREEN}✓${NC} Created .venv"
else
    echo -e "${GREEN}✓${NC} .venv already exists"
fi

# Editable install: resolves prod deps (pyproject dynamic dependencies) + the
# `test` extra, and mints the repo-local `.venv/bin/itsup` console-script with
# the venv interpreter baked into its shebang — runnable from any cwd, no sourcing.
echo "Installing itsUP (editable) with test extras..."
.venv/bin/pip install -q -e ".[test]"
echo -e "${GREEN}✓${NC} Installed itsUP editable + test deps (minted .venv/bin/itsup)"

# Expose a global `itsup` on the user's PATH: ~/.local/bin/itsup -> the repo's
# console-script. The target is cwd-independent (venv shebang + root() resolution),
# so the bare `itsup` works from any directory. Runtime callers (systemd/launchd)
# use the absolute path and do not rely on this symlink.
LOCAL_BIN="${HOME}/.local/bin"
mkdir -p "${LOCAL_BIN}"
ln -sf "${REPO_ROOT}/.venv/bin/itsup" "${LOCAL_BIN}/itsup"
echo -e "${GREEN}✓${NC} Linked global itsup: ${LOCAL_BIN}/itsup -> ${REPO_ROOT}/.venv/bin/itsup"
if [[ ":$PATH:" != *":${LOCAL_BIN}:"* ]]; then
    echo -e "${YELLOW}⚠${NC} ${LOCAL_BIN} is not on your PATH — add it to use the bare 'itsup':"
    echo "     export PATH=\"${LOCAL_BIN}:\$PATH\"   # add to your shell profile"
fi

echo ""
echo -e "${GREEN}✅ Dependencies installed!${NC}"
echo ""
echo "itsup is global: run 'itsup <cmd>' from any directory (via ~/.local/bin/itsup)."
echo "'source env.sh' is optional — venv activation + shell completion for development."
echo ""
echo "Next steps:"
echo ""
echo "  1. Initialize itsUP (sets up projects and secrets repos):"
echo "     itsup init"
echo ""
echo "  2. Generate SOPS encryption key (auto-updates .sops.yaml):"
echo "     itsup sops-key"
echo ""
echo "  3. Edit secrets:"
echo "     itsup edit-secret itsup"
echo ""
echo "  4. Enable git hooks (auto requirements install on pull):"
echo "     git config core.hooksPath bin/hooks"
echo ""
echo "On the container host only — make it a live deployment:"
echo ""
echo "  make install-runtime       # install boot/nightly/healthcheck integration + start the stack"
echo "  itsup apply                # deploy/redeploy the stack (host-only; never on a dev box)"
echo "  make uninstall-runtime     # decommission: stop everything, remove integration"
echo ""

# Auto-enable git hooks (post-merge requirements install) if inside a git repo
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git config core.hooksPath bin/hooks
    echo -e "${GREEN}✓${NC} Git hooks enabled (core.hooksPath=bin/hooks)"
else
    echo -e "${YELLOW}⚠${NC} Not a git repo; skipping hooks setup"
fi
echo ""
