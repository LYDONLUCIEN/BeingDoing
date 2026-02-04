# /home/gitclone/BeingDoing/src/backend/debug_server.py
import uvicorn
import os
import sys

# 确保当前目录在 sys.path 中，防止导入错误
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # 注意：debug 模式下通常把 reload 设为 False，否则断点有时候会乱跳
    # "app.main:app" 需要根据你实际的入口文件路径修改
    # 如果你的入口文件是 app/main.py，app变量叫 app，那就是 "app.main:app"
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)