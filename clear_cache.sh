#!/bin/bash

# 清理缓存
echo "🧹 清理 Python 缓存..."
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null