#!/usr/bin/env sh
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "itsUP Installation"
echo "=================="

# Detect ITSUP_ROOT (project root directory)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ITSUP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export ITSUP_ROOT

# Validate we're in the correct directory
if [ ! -f "$ITSUP_ROOT/bin/install.sh" ] || [ ! -d "$ITSUP_ROOT/samples" ]; then
    echo "${RED}✗ Error: Must be run from itsUP project root${NC}" >&2
    echo "  Expected to find bin/install.sh and samples/ directory" >&2
    exit 1
fi

echo "Project root: $ITSUP_ROOT"

# Check submodules exist
echo ""
echo "Checking submodules..."
if [ ! -d "$ITSUP_ROOT/projects/.git" ]; then
    echo "${RED}✗ Error: projects/ submodule not initialized${NC}" >&2
    echo "  Run: git submodule update --init --recursive" >&2
    exit 1
fi
echo "${GREEN}✓${NC} projects/ submodule initialized"

if [ ! -d "$ITSUP_ROOT/secrets/.git" ]; then
    echo "${RED}✗ Error: secrets/ submodule not initialized${NC}" >&2
    echo "  Run: git submodule update --init --recursive" >&2
    exit 1
fi
echo "${GREEN}✓${NC} secrets/ submodule initialized"

# Initialize configuration files if needed
echo ""
echo "Checking configuration files..."

# Copy .env if it doesn't exist
if [ ! -f "$ITSUP_ROOT/.env" ]; then
    if [ -f "$ITSUP_ROOT/samples/env" ]; then
        cp "$ITSUP_ROOT/samples/env" "$ITSUP_ROOT/.env"
        # Update ITSUP_ROOT in .env with detected path
        sed -i "s|ITSUP_ROOT=.*|ITSUP_ROOT=$ITSUP_ROOT|" "$ITSUP_ROOT/.env"
        echo "${GREEN}✓${NC} Copied samples/env → .env (with ITSUP_ROOT=$ITSUP_ROOT)"
    else
        echo "${YELLOW}⚠${NC} samples/env not found, skipping .env creation"
    fi
else
    echo "${GREEN}✓${NC} .env already exists (not overwriting)"
fi

# Copy traefik.yml if it doesn't exist
if [ ! -f "$ITSUP_ROOT/projects/traefik.yml" ]; then
    if [ -f "$ITSUP_ROOT/samples/traefik.yml" ]; then
        cp "$ITSUP_ROOT/samples/traefik.yml" "$ITSUP_ROOT/projects/traefik.yml"
        echo "${GREEN}✓${NC} Copied samples/traefik.yml → projects/traefik.yml"
    else
        echo "${YELLOW}⚠${NC} samples/traefik.yml not found, skipping"
    fi
else
    echo "${GREEN}✓${NC} projects/traefik.yml already exists (not overwriting)"
fi

# Copy secrets if they don't exist
if [ ! -f "$ITSUP_ROOT/secrets/global.txt" ]; then
    if [ -f "$ITSUP_ROOT/samples/secrets/global.txt" ]; then
        cp "$ITSUP_ROOT/samples/secrets/global.txt" "$ITSUP_ROOT/secrets/global.txt"
        echo "${GREEN}✓${NC} Copied samples/secrets/global.txt → secrets/global.txt"
        echo "${YELLOW}⚠ WARNING: Sample secrets copied - MUST be changed before deployment!${NC}"
    else
        echo "${YELLOW}⚠${NC} samples/secrets/global.txt not found, skipping"
    fi
else
    echo "${GREEN}✓${NC} secrets/global.txt already exists (not overwriting)"
fi

# Create Python virtual environment
echo ""
echo "Setting up Python environment..."
if [ ! -d "$ITSUP_ROOT/.venv" ]; then
    python3 -m venv "$ITSUP_ROOT/.venv"
    echo "${GREEN}✓${NC} Created .venv"
else
    echo "${GREEN}✓${NC} .venv already exists"
fi

# Activate and install dependencies
. "$ITSUP_ROOT/.venv/bin/activate"
pip install -q -r "$ITSUP_ROOT/requirements-prod.txt"
echo "${GREEN}✓${NC} Installed Python dependencies"

echo ""
echo "=================="
echo "${GREEN}✓ Installation complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Edit .env (already set ITSUP_ROOT=$ITSUP_ROOT)"
echo "2. Edit projects/traefik.yml (change domain_suffix to your domain)"
echo "3. Edit secrets/global.txt (fill in all required secrets - CRITICAL!)"
echo "4. Encrypt secrets: cd secrets && sops -e global.txt > global.enc.txt"
echo "5. Commit configs to git (in projects/ and secrets/ submodules)"
echo "6. Deploy: bin/apply.py"
