# 后端测试说明

## 测试文件列表

### Phase 0 测试

1. **test_config.py** - 配置模块测试
   - 测试应用配置读取
   - 测试架构配置
   - 测试引导策略配置
   - 测试语音配置

2. **test_main.py** - 主应用测试
   - 测试根路径
   - 测试健康检查接口

3. **test_utils.py** - 工具函数测试
   - 测试UUID生成
   - 测试时间戳获取
   - 测试响应格式化

4. **test_middleware.py** - 中间件测试
   - 测试语音功能中间件
   - 测试错误处理中间件

5. **test_api_config.py** - API配置接口测试
   - 测试架构配置查询接口

## 运行测试

```bash
# 运行所有测试
pytest test/backend -v

# 运行特定测试文件
pytest test/backend/test_config.py -v

# 运行特定测试函数
pytest test/backend/test_config.py::test_settings -v

# 查看覆盖率
pytest test/backend --cov=src/backend/app --cov-report=html
```

## 测试覆盖率目标

- Phase 0: > 80%
- 核心模块: > 80%
- 业务逻辑: > 70%
