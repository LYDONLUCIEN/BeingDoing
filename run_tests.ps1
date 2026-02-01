# 测试运行脚本 (PowerShell)
# 使用方法: .\run_tests.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "运行第一阶段测试" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 设置PYTHONPATH
$env:PYTHONPATH = "src/backend"
Write-Host "PYTHONPATH设置为: $env:PYTHONPATH" -ForegroundColor Green

# 运行测试
Write-Host "`n运行配置模块测试..." -ForegroundColor Yellow
python -m pytest test/backend/test_config.py -v

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "测试完成" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
