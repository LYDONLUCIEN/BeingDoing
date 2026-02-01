# 测试目录说明

## 目录结构

```
test/
├── backend/              # 后端测试
│   ├── core/            # 核心模块测试
│   │   ├── llmapi/      # LLM API测试
│   │   ├── asr/         # ASR API测试
│   │   ├── tts/         # TTS API测试
│   │   ├── agent/       # 智能体框架测试
│   │   ├── knowledge/   # 知识检索测试
│   │   ├── database/    # 数据库测试
│   │   └── cache/       # 缓存测试
│   ├── api/             # API接口测试
│   │   └── v1/          # API v1测试
│   └── services/        # 业务逻辑测试
├── frontend/            # 前端测试
│   ├── components/     # 组件测试
│   ├── pages/          # 页面测试
│   └── services/       # 服务测试
└── integration/         # 集成测试
```

## 运行测试

### 后端测试

```bash
# 从项目根目录运行
pytest test/backend -v

# 运行特定测试文件
pytest test/backend/test_config.py -v

# 运行特定测试函数
pytest test/backend/test_config.py::test_settings -v
```

### 前端测试

```bash
cd src/frontend
npm test
```

## 测试配置

- `pytest.ini`: pytest配置文件，设置pythonpath和测试选项
- 测试文件命名：`test_*.py`
- 测试函数命名：`test_*`
