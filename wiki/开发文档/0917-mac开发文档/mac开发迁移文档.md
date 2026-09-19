
• 可以。下面这份可直接转给服务器人员确认。核心原则是：Mac 只修改和验证前端源码；Linux 从 Git 拉取源码后，在 Linux 上重新安装依赖、构建、重启前端。

  # 一、请服务器人员先确认的事项

  请确认以下内容后再按此流程上线：

  1. 线上项目目录，例如 /opt/BeingDoing，以及生产分支名（下文以 <生产分支> 表示）。
  2. 线上服务确实由项目根目录的 ./start.sh 管理，而不是 systemd、Docker 或其他面板单独管理。
  3. 当前生产服务是以 prod 环境启动：

     cd /项目目录
     cat .start_env

     应输出：

     prod

  4. Linux 的 Node 主版本建议为 18，与项目 Dockerfile 一致：

     node --version
     npm --version

  5. 生产环境的 .env、.env.prod、NEXT_SERVER_ACTIONS_ENCRYPTION_KEY 都已存在且不会被 Git 覆盖。它们不应提交到仓库。
  6. tmux 服务会话存在：

     tmux has-session -t beingdoing

  特别说明：项目现有 ./start.sh restart frontend 会在生产模式下删除旧 .next、重新 npm run build 并重启前端。因此，纯 UI 发布不需要重启后端。

  # 二、Mac 上一次性准备

  Mac 不需要安装 Python、Conda、数据库、LLM Key 或运行完整后端。只需：

  - Git
  - Node.js 18
  - npm
  - Chrome / Edge

  检查版本：

  git --version
  node --version
  npm --version

  Node 应为 v18.x。若已安装 nvm：

  nvm install 18
  nvm use 18

  首次拉取并安装前端：

  git clone <仓库地址>
  cd BeingDoing/src/frontend
  npm ci
  npm run dev

  浏览器访问：

  http://localhost:3000

  注意：不要在 Mac 执行 ./start.sh，它包含 Linux 的 tmux、Conda、后端启动逻辑，不适合本地纯 UI 开发。

  # 三、Mac 日常 UI 开发操作

  每次开发：

  cd /Users/soulhappy/gitclone/BeingDoing
  git switch <开发分支>
  cd src/frontend
  npm run dev

  修改范围通常是：

  src/frontend/app/         页面
  src/frontend/components/  组件
  src/frontend/styles/      视觉样式与主题
  src/frontend/public/      图片、字体等静态资源

  完成后至少执行：

  cd /Users/soulhappy/gitclone/BeingDoing/src/frontend
  npm run lint
  npm run build

  并用 Chrome 检查：

  - 桌面宽度
  - 手机宽度
  - 明亮 / 深色主题
  - 首页、探索聊天页、购买弹窗等被修改的页面
  - 浏览器控制台无报错

  若只是改视觉，不连本地后端也可以工作；接口请求失败不影响 CSS、布局、动画等 UI 验收。

  若必须联调真实接口，应由服务器人员提供独立测试环境，在 Mac 创建未纳入 Git 的 src/frontend/.env.local：

  NEXT_PUBLIC_API_URL=https://测试环境域名

  不要让 Mac 本地开发页面直接操作生产支付、用户、订单或激活码数据。

  # 四、Mac 提交代码

  cd /Users/soulhappy/gitclone/BeingDoing
  git status
  git add src/frontend
  git commit -m "feat(ui): 描述本次界面调整"
  git push -u origin <开发分支>

  建议通过 PR / 合并请求进入 <生产分支>；不要直接在服务器手改前端文件。

  不应提交这些内容：

  src/frontend/node_modules/
  src/frontend/.next/
  src/frontend/.env.local
  .env
  .env.prod

  项目当前 .gitignore 已忽略它们。

  # 五、Linux 纯 UI 发布操作

  服务器人员在确认生产分支已合并后执行：

  cd /项目目录
  git status --short
  git pull --ff-only origin <生产分支>
  cd src/frontend
  npm ci
  cd ../..
  ./start.sh restart frontend

  说明：

  - git status --short 必须为空；若服务器有未提交修改，先停止发布并处理，不能硬拉代码。
  - npm ci 每次执行最稳，尤其当 package-lock.json 有变化时必须执行。
  - ./start.sh restart frontend 会重新构建和重启前端，不会重启 FastAPI 后端。
  - 不要使用 ./start.sh prod 做纯 UI 小发布：若 tmux 服务已存在，它不会替你完成预期的全量重启；若改用 stop 再 prod，又会影响后端服务。

  发布后检查：

  tmux list-windows -t beingdoing
  tmux capture-pane -pt beingdoing:frontend -S -80

  然后由浏览器访问正式域名，强制刷新页面并验证本次改动。

  # 六、我的实施计划

  Mac
    建立 Node 18 前端开发环境
    → Codex 修改 src/frontend 源码
    → 本地热更新验收
    → lint + build
    → Git 提交并合并生产分支

  Linux
    检查工作区、分支、Node、tmux、prod 环境
    → git pull --ff-only
    → npm ci
    → ./start.sh restart frontend
    → 查看前端日志与线上页面

  这套方案不改变后端、数据库、密钥和生产配置；实际变更只有 Git 中的前端源码。最重要的前置检查是：服务器是否确实用 start.sh + tmux 管理前端，以及 .start_env 是否
  为 prod。

  # 七、New UI 设计规范与本地预览

  当前 UI 设计、页面边界、组件范式、响应式规则和验收清单统一维护在：

  `wiki/开发文档/0919-newui-UI设计范式与实现标准.md`

  本地没有后端数据时，可在开发环境使用 `?ui_preview=1` 检查页面，例如：

  ```text
  /explore/chat/values?ui_preview=1&preview_state=conversation
  /explore/chat/values?ui_preview=1&preview_state=conclusion
  /explore/chat/rumination?ui_preview=1&preview_state=conversation
  /dashboard?ui_preview=1
  /dashboard/settings?ui_preview=1
  ```

  UI 预览只允许在 `NODE_ENV=development` 下生效，不得用于绕过生产鉴权，也不得触发支付、删除或其他生产写入。
