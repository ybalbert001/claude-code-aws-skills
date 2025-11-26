#!/bin/bash

# Excalidraw Skill Setup Script
# This script installs the required dependencies for PNG export functionality

set -e

echo "================================================"
echo "  Excalidraw Skill - Dependency Setup"
echo "================================================"
echo ""

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Error: Node.js is not installed"
    echo "   Please install Node.js (version 18 or higher)"
    echo "   Visit: https://nodejs.org/"
    exit 1
fi

# Check Node.js version
NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "⚠️  Warning: Node.js version 18 or higher is recommended"
    echo "   Current version: $(node -v)"
fi

echo "✓ Node.js detected: $(node -v)"
echo ""

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ Error: npm is not installed"
    exit 1
fi

echo "✓ npm detected: $(npm -v)"
echo ""

# Navigate to scripts directory where package.json is located
cd "$SCRIPT_DIR"

# Install dependencies
echo "📦 Installing dependencies from scripts/package.json..."
echo ""
npm install

echo ""
echo "🌐 Installing Chromium browser for Playwright..."
echo ""
npx playwright install chromium

echo ""
echo "================================================"
echo "✓ Setup completed successfully!"
echo "================================================"
echo ""
echo "You can now use the PNG export feature:"
echo ""
echo "  # Basic usage:"
echo "  node scripts/render-to-png.js diagram.excalidraw.json"
echo ""
echo "  # With options:"
echo "  node scripts/render-to-png.js diagram.excalidraw.json output.png --scale 3"
echo ""
echo "For more information, see SKILL.md"
echo ""
