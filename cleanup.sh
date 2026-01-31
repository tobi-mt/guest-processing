#!/usr/bin/env bash
# cleanup.sh - Clean up temporary files

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🧹 Cleaning up project files..."

# Remove Python cache files
echo "  - Removing __pycache__ directories..."
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "*.pyo" -delete 2>/dev/null || true

# Remove old database file (keep the updated one)
if [ -f "guest_database.db" ]; then
    echo "  - Removing old database file..."
    rm "guest_database.db"
fi

# Remove Hatch environments (if you want to recreate them)
if [ "$1" == "--full" ]; then
    echo "  - Removing Hatch environments..."
    hatch env remove default 2>/dev/null || true
    hatch env remove lint 2>/dev/null || true
    rm -rf .hatch/ 2>/dev/null || true
fi

# Remove other temporary files
echo "  - Removing temporary files..."
find . -name ".DS_Store" -delete 2>/dev/null || true
find . -name "*.tmp" -delete 2>/dev/null || true
find . -name "*.log" -delete 2>/dev/null || true

echo "✅ Cleanup complete!"
echo ""
if [ "$1" == "--full" ]; then
    echo "Note: Hatch environments removed. Run 'hatch env create' to recreate them."
else
    echo "Note: __pycache__ directories will be recreated when you run Python code."
    echo "This is normal behavior and improves performance."
    echo ""
    echo "Run './cleanup.sh --full' to also remove Hatch environments."
fi
