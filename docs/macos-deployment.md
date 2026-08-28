# oPanel macOS 部署

## 部署约定

生产环境为 Mac mini M4 / Apple Silicon macOS、原生 Python venv、Node.js/npm、用户级 launchd、SQLite 和 Cloudflare Tunnel。

oPanel 固定监听：

```text
127.0.0.1:38652
```

Cloudflare Tunnel 的 Origin 固定为：

```text
http://127.0.0.1:38652
```

不使用备用端口，不监听 `0.0.0.0`。安装脚本不会自动配置 Cloudflare，也不会让 oPanel 管理 `cloudflared` 的生命周期。

## 1. 安装 oPanel

准备 macOS、Python 3.14（优先）或 Python 3.12+，以及 Node.js 22.18.x 或 >=24.11.0 和 npm，并确保可以访问 Ozon API：

```sh
git clone https://github.com/LI5ee3/oPanel.git
cd oPanel
./scripts/install-macos.sh
```

安装脚本会：

1. 确认当前系统为 macOS，并检查 `38652` 是否已被监听。
2. 优先选择 `python3.14`，否则选择可用的 Python 3.12+。
3. 检查 `node --version` 和 `npm --version`；Node.js 必须满足 `^22.18.0 || >=24.11.0`，不满足时直接停止，不自动安装 Homebrew Node。
4. 在项目根目录创建或更新 `.venv`，安装 `requirements.txt`。
5. 执行 `scripts/build-frontend.sh`：使用 `npm ci`、Vue type-check 和 Vite build，将完整产物写入 `frontend/dist.next/` 并验证 `index.html`、JS/CSS assets 和 `/assets/` 引用。
6. 创建或检查 `.env`，并执行 `chmod 600 .env`。
7. 使用现有 `app.security.migrate_env_password` 迁移旧版 `ADMIN_PASSWORD`。
8. 使用现有 `app.security.password_hash` 生成缺失的 `ADMIN_PASSWORD_SALT` 和 `ADMIN_PASSWORD_HASH`。首次自动生成的管理员密码只在终端显示一次，请立即安全保存。
9. 将 launchd 配置安装到 `~/Library/LaunchAgents/com.opanel.app.plist`，在启动前把 staged build 激活为 `frontend/dist/`，创建 `logs/` 并启动服务。
10. 使用 `scripts/verify-frontend.sh` 请求 `http://127.0.0.1:38652/`、19 个 Vue deep links、Vite/Legacy assets 和 API isolation。

安装不需要 `sudo`。脚本不会覆盖已有 `.env`，也不会删除 `data/`。

### `.env` 配置

在安装后编辑项目根目录 `.env`，填入店铺凭据和需要的可选配置：

```dotenv
SHOP_1_OZON_CLIENT_ID=店铺1的Client-Id
SHOP_1_OZON_API_KEY=店铺1的Api-Key
SHOP_2_OZON_CLIENT_ID=店铺2的Client-Id
SHOP_2_OZON_API_KEY=店铺2的Api-Key
# 可选：Performance API service account，用于只读同步广告 Campaign 与统计
SHOP_1_OZON_PERF_CLIENT_ID=店铺1的Performance-Client-Id
SHOP_1_OZON_PERF_CLIENT_SECRET=店铺1的Performance-Client-Secret
SHOP_2_OZON_PERF_CLIENT_ID=店铺2的Performance-Client-Id
SHOP_2_OZON_PERF_CLIENT_SECRET=店铺2的Performance-Client-Secret
OZON_WEBHOOK_SECRET_1=店铺1Webhook随机密钥
OZON_WEBHOOK_SECRET_2=店铺2Webhook随机密钥
# 若 Ozon Push 的 seller_id 与 Client-Id 不同，再填写对应 Seller ID
# SHOP_1_OZON_SELLER_ID=店铺1的Seller ID
# SHOP_2_OZON_SELLER_ID=店铺2的Seller ID
DINGTALK_WEBHOOK_URL=钉钉自定义机器人Webhook
DINGTALK_SECRET=钉钉机器人加签Secret
```

Performance API 配置为可选项；未填写时不影响 Seller API 和 oPanel 启动。不要在密钥两侧添加引号，也不要提交 `.env`。

修改 `.env` 后重启：

```sh
./scripts/restart.sh
```

## 2. 本地验证

本机固定地址：

```text
http://127.0.0.1:38652
```

查看用户级服务状态：

```sh
launchctl print "gui/$(id -u)/com.opanel.app"
```

查看 launchd 日志：

```sh
tail -f logs/opanel.stdout.log
tail -f logs/opanel.stderr.log
```

如果 stderr 出现 `Operation not permitted`，且项目位于 `~/Library/CloudStorage/` 等受 macOS 隐私控制的目录，这是 LaunchAgent 的路径访问权限问题，不是端口或 plist 参数问题。将项目放到 launchd 可读取的本机用户目录后重新安装，或按组织安全策略授予必要的访问权限；不要改为 root 运行。

服务管理脚本：

```sh
./scripts/start.sh
./scripts/stop.sh
./scripts/restart.sh
```

更新流程：

```sh
./scripts/update.sh
```

`update.sh` 使用以下顺序：

```text
git pull --ff-only
Python dependency update
检查当前 launchd / 38652
staged Vue build（npm ci、type-check、Vite build）
production SQLite 只读检查 sync_runs.status='running'
stop service，并等待 LaunchAgent 消失
frontend/dist → frontend/dist.previous
frontend/dist.next → frontend/dist
start service
验证 root、19 deep links、assets、API isolation
```

构建、type-check、Vite artifact verification 任一失败，或存在运行中的同步任务时，脚本不会停止/重启当前生产服务。验证失败会在服务停止期间恢复 `frontend/dist.previous`，新产物保留为 `frontend/dist.failed/` 供排查。脚本不执行 reset、clean，不覆盖 `.env`，不删除 `data/`。

`frontend/dist.next/`、`frontend/dist.previous/` 和 `frontend/dist.failed/` 都是本地产物目录，不提交 Git。

## 2.1 Production serving

FastAPI 正式从 `frontend/dist/index.html` 提供 `/` 和 Vue history deep links；`/assets/*` 提供 Vite hashed assets，并对 index 设置 `Cache-Control: no-cache`。`/static/*` 继续挂载，用于 `/static/logo.svg`、`/static/morphicons.js` 以及 Phase 20 前保留的 Legacy assets。

`/api/*`、`/static/*` 和 `/assets/*` 不进入 SPA fallback；未知 API 继续返回认证/404 语义，缺失 asset 返回 404。生产入口仍为 `127.0.0.1:38652`，Cloudflare Tunnel Origin 不变。

## 3. 安装 Cloudflare Tunnel

通过 Homebrew 安装 `cloudflared`：

```sh
brew install cloudflared
```

然后按照 Cloudflare Zero Trust 控制台的 Tunnel 流程登录并创建独立的 Tunnel。Tunnel 的账号、凭据和生命周期由 Cloudflare/cloudflared 管理，不要写入 oPanel 的 `.env`，也不要由 oPanel 脚本自动创建或启动。

## 4. Cloudflare Tunnel 目标

在 Cloudflare Zero Trust 的 Public Hostname 中添加示例域名：

```text
panel.example.com
```

Origin Service 设置为：

```text
http://127.0.0.1:38652
```

发布域名后，通过 `https://panel.example.com` 访问 oPanel。Tunnel 与 oPanel 是两个独立服务；oPanel 只负责本机的 FastAPI 服务。

不需要：

- 公网 IPv4
- 公网 IPv6
- DDNS
- 路由器端口映射
- 80
- 443
- Nginx
- Caddy
- Docker

## 5. Ozon Webhook

保留项目现有 Webhook 格式，将发布后的 HTTPS 域名替换为你的域名：

```text
https://你的域名/api/webhooks/ozon/<对应店铺密钥>
```

Cloudflare Tunnel 发布域名后即可将该地址配置到 Ozon。Webhook 业务逻辑和路径不需要修改。

## 6. Mac mini 基础运维

- 禁止 Mac 自动睡眠；允许显示器关闭。
- 如果当前 macOS 和硬件支持，开启断电恢复后自动启动。
- 定期备份 `data/` 和 `.env`；不要把备份提交到 Git。
- 保持 `.env` 权限为 `600`：`chmod 600 .env`。
- `logs/` 是本地日志目录，已加入 `.gitignore`。
