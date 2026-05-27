#!/usr/bin/env bash
# Build script for Render deployment

set -o errexit

echo "🚀 Starting Injaaz App build..."

# Upgrade pip first
echo "📦 Upgrading pip..."
python -m pip install --upgrade pip

# Install Python dependencies
echo "📦 Installing dependencies from requirements-prods.txt..."
pip install -r requirements-prods.txt

# Create necessary directories
echo "📁 Creating directory structure..."
mkdir -p generated/uploads
mkdir -p generated/submissions
mkdir -p generated/jobs
mkdir -p generated/drafts
mkdir -p instance

echo "✅ Build completed successfully!"
