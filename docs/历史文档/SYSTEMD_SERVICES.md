# systemd 部署说明（前后端分离）

本文提供 BeingDoing 在同一台服务器上的稳定运行方式，避免多个项目之间环境变量互相污染。

## 文件位置

- 服务文件（仓库内模板）：
  - `deploy/systemd/beingdoing-backend.service`
  - `deploy/systemd/beingdoing-frontend.service`
- 环境变量模板（仓库内）：
  - `deploy/systemd/beingdoing.env.example`
- 实际生效环境文件（系统级）：
  - `/etc/beingdoing.env`
- systemd 正式服务路径（系统级）：
  - `/etc/systemd/system/beingdoing-backend.service`
  - `/etc/systemd/system/beingdoing-frontend.service`

## `beingdoing.env` 与 `.service` 的关系

- 两个 `.service` 都声明了：`EnvironmentFile=/etc/beingdoing.env`
- 含义：systemd 启动进程时，会先把 `/etc/beingdoing.env` 中的键值注入进程环境。
- 后端读取顺序是：
  1. 进程环境（systemd 注入）
  2. 项目根 `.env`
  3. `settings.py` 默认值
- 因此使用 systemd 后，`/etc/beingdoing.env` 会成为“最高优先级配置来源”，可避免 tmux/shell 的旧变量串进来。

## 安装步骤（一次性）

1. 复制环境文件模板：

```bash
sudo cp /home/gitclone/BeingDoing/deploy/systemd/beingdoing.env.example /etc/beingdoing.env
sudo chmod 600 /etc/beingdoing.env
```

2. 编辑 `/etc/beingdoing.env`，至少填写：
- `SECRET_KEY`
- `DEEPSEEK_API_KEY`
- （可选）`SUPER_ADMIN_EMAILS`

3. 安装服务文件：

```bash
sudo cp /home/gitclone/BeingDoing/deploy/systemd/beingdoing-backend.service /etc/systemd/system/
sudo cp /home/gitclone/BeingDoing/deploy/systemd/beingdoing-frontend.service /etc/systemd/system/
```

4. 重新加载并启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable beingdoing-backend
sudo systemctl enable beingdoing-frontend
sudo systemctl restart beingdoing-backend
sudo systemctl restart beingdoing-frontend
```

## 常用命令

```bash
sudo systemctl status beingdoing-backend
sudo systemctl status beingdoing-frontend
sudo journalctl -u beingdoing-backend -f
sudo journalctl -u beingdoing-frontend -f
```

## 一键自动化脚本（推荐）

仓库已提供脚本：

- `deploy/systemd/deploy_systemd.sh`

### 常见用法

1) 使用项目根 `.env` 作为实际部署环境，并自动重启：

```bash
sudo /home/gitclone/BeingDoing/deploy/systemd/deploy_systemd.sh --from-project-env
```

2) 使用模板环境（示例值），并自动重启：

```bash
sudo /home/gitclone/BeingDoing/deploy/systemd/deploy_systemd.sh --from-template
```

3) 只同步文件，不重启（用于先检查）：

```bash
sudo /home/gitclone/BeingDoing/deploy/systemd/deploy_systemd.sh --from-project-env --no-restart
```

## 配置变更生效

- 修改 `/etc/beingdoing.env` 后需要重启服务：

```bash
sudo systemctl restart beingdoing-backend
sudo systemctl restart beingdoing-frontend
```

