#!/bin/bash
# 测试运行脚本 (Bash)
# 使用方法: ./run_tests.sh

echo "========================================"
echo "运行第一阶段测试"
echo "========================================"

# 设置PYTHONPATH
export PYTHONPATH="src/backend"
echo "PYTHONPATH设置为: $PYTHONPATH"

# 运行测试
echo ""
echo "运行配置模块测试..."
python -m pytest test/backend/test_config.py -v

echo ""
echo "========================================"
echo "测试完成"
echo "========================================"
