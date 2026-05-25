#!/bin/bash
# Quick Start Script for Gatekeeper with GitNexus

echo "================================"
echo "Gatekeeper + GitNexus Quick Start"
echo "================================"
echo ""

# Check if GitNexus is installed
echo "1. Checking GitNexus installation..."
if command -v gitnexus &> /dev/null; then
    echo "   ✅ GitNexus is installed"
    gitnexus --version
else
    echo "   ❌ GitNexus not found"
    echo "   Installing GitNexus..."
    npm install -g gitnexus
fi

echo ""
echo "2. Starting repository setup..."
echo "   You'll be prompted to add repositories"
echo ""

# Run the repository setup
python setup_repos.py

echo ""
echo "3. To enable GitNexus analysis, run:"
echo "   python setup_repos.py index"
echo ""
echo "4. Then start Gatekeeper:"
echo "   python main.py"
echo ""
echo "================================"
echo "Quick Start Complete!"
echo "================================"
