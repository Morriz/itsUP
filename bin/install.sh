#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

    # Docker
    if ! command_exists docker; then
        echo -e "${RED}✗${NC} Docker not found"
        echo "  Install from: https://docs.docker.com/engine/install/"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Docker installed"

    # SOPS
    if ! command_exists sops; then
        echo -e "${YELLOW}  ⬇️  Installing SOPS...${NC}"
        SOPS_VERSION=$(curl -s https://api.github.com/repos/mozilla/sops/releases/latest | grep tag_name | cut -d '"' -f 4 | cut -c 2-)
        wget -qO /tmp/sops.deb "https://github.com/mozilla/sops/releases/download/v${SOPS_VERSION}/sops_${SOPS_VERSION}_amd64.deb"
        sudo dpkg -i /tmp/sops.deb
        rm /tmp/sops.deb
        echo -e "${GREEN}✓${NC} SOPS installed"
    else
        echo -e "${GREEN}✓${NC} SOPS already installed"
    fi

    # age
    if ! command_exists age; then
        echo -e "${YELLOW}  ⬇️  Installing age...${NC}"
        sudo apt-get update
        sudo apt-get install -y age
        echo -e "${GREEN}✓${NC} age installed"
    else
        echo -e "${GREEN}✓${NC} age already installed"
    fi

    # sops-diff (for meaningful diffs)
    if ! command_exists sops-diff; then
        echo -e "${YELLOW}  ⬇️  Installing sops-diff...${NC}"
        SOPS_DIFF_VERSION=$(curl -s https://api.github.com/repos/saltydogtechnology/sops-diff/releases/latest | grep tag_name | cut -d '"' -f 4)
        curl -L "https://github.com/saltydogtechnology/sops-diff/releases/download/${SOPS_DIFF_VERSION}/sops-diff-${SOPS_DIFF_VERSION}-linux-${ARCH_SOPS_DIFF}.tar.gz" | tar xz
        sudo mv sops-diff-linux-${ARCH_SOPS_DIFF} /usr/local/bin/sops-diff
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

# Install Python dependencies
echo "Installing Python dependencies..."
.venv/bin/pip install -q -r requirements-prod.txt
echo -e "${GREEN}✓${NC} Installed Python dependencies"

echo ""
echo -e "${GREEN}✅ Installation complete!${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Source the environment (enables shell completion and PATH):"
echo "     source env.sh"
echo ""
echo "  2. Initialize itsUP (sets up projects and secrets repos):"
echo "     itsup init"
echo ""
echo "  3. Generate SOPS encryption key (auto-updates .sops.yaml):"
echo "     itsup sops-key"
echo ""
echo "  4. Edit secrets:"
echo "     itsup edit-secret itsup"
echo ""
echo "  5. Deploy:"
echo "     itsup apply"
echo ""
