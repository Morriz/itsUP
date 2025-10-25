#!/bin/bash
set -e

# Create Python virtual environment if needed
if [ ! -d .venv ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
    echo "✓ Created .venv"
else
    echo "✓ .venv already exists"
fi

# Install dependencies
echo "Installing Python dependencies..."
.venv/bin/pip install -q -r requirements-prod.txt
echo "✓ Installed Python dependencies"
