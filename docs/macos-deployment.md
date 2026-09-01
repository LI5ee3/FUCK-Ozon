# O3Pilot macOS 部署

## 部署约定

生产环境为 Mac mini M4 / Apple Silicon macOS、原生 Python venv、Node.js/npm、用户级 launchd、SQLite 和 Cloudflare Tunnel。

O3Pilot 固定监听：

```text
127.0.0.1:38652
```

Cloudflare Tunnel 的 Origin 固定为：

```text
http://127.0.0.1:38652
```

不使用备用端口，不监听 `0.0.0.0`。安装脚本不会自动配置 Cloudflare，也不会让 O3Pilot 管理 `cloudflared` 的生命周期。

当前生产状态：Phase 20 Static Cleanup 已完成。FastAPI 从 `frontend/dist/` 提供 Vue SPA，`/assets/` 提供构建资产，`/static/*` 明确返回 404。

## 1. 安装 O3Pilot

准备 macOS、Python 3.14（优先）或 Python 3.12+，以及 Node.js 22（>=22.18）、Node.js 24（>=24.11）或 Node.js >=25 和 npm，并确保可以访问 Ozon API：

```sh
git clone https://github.com/LI5ee3/O3Pilot.git
cd O3Pilot
./scripts/install-macos.sh
```

安装脚本会：

1. 确认当前系统为 macOS，并检查 `38652` 是否已被监听。
2. 优先选择 `python3.14`，否则选择可用的 Python 3.12+。
3. 检查 `node --version` 和 `npm --version`；Node.js 必须为 22（>=22.18）、24（>=24.11）或 >=25，不满足时直接停止，不自动安装 Homebrew Node。
4. 在项目根目录创建或更新 `.venv`，安装 `requirements.txt`。
5. 执行 `scripts/test.sh` 和 `scripts/build-frontend.sh`：安装前端依赖，运行 Python/Vue/Profit 测试与类型检查，再将完整产物写入 `frontend/dist.next/` 并验证 `index.html`、JS/CSS assets 和 `/assets/` 引用。
6. 创建或检查 `.env`，并执行 `chmod 600 .env`。
7. 按下方“管理员初始化”说明迁移旧版密码或生成新的管理员凭据。
8. 将 launchd 配置安装到 `~/Library/LaunchAgents/com.opanel.app.plist`，在启动前把 staged build 激活为 `frontend/dist/`，创建 `logs/` 并启动服务。
9. 使用 `scripts/verify-frontend.sh` 请求 `http://127.0.0.1:38652/`、19 个 Vue deep links、`/assets/` 当前资产、`/static/*` 404 和 API isolation。

安装不需要 `sudo`。脚本不会覆盖已有 `.env`，也不会删除 `data/`。

### 1.1 `.env` 配置

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

Performance API 配置为可选项；未填写时不影响 Seller API 和 O3Pilot 启动。不要在密钥两侧添加引号，也不要提交 `.env`。

修改 `.env` 后重启：

```sh
./scripts/restart.sh
```

### 1.2 管理员初始化

安装脚本以 `.env` 中是否存在 `ADMIN_PASSWORD_HASH` 决定是否生成管理员凭据；服务登录同时需要 `ADMIN_PASSWORD_SALT` 和 `ADMIN_PASSWORD_HASH`：

- 如果只有旧版 `ADMIN_PASSWORD`，且没有密码哈希，脚本会将其迁移为新的 `scrypt` 盐值和哈希，并移除旧字段。
- 如果没有可迁移的旧密码，脚本会生成随机初始密码，将盐值和哈希写入 `.env`，并只在终端显示初始密码一次，请立即安全保存。
- 已有 `ADMIN_PASSWORD_HASH` 时，脚本不会覆盖现有管理员凭据。后续登录和服务启动依赖 `.env` 中的 `ADMIN_PASSWORD_SALT` 与 `ADMIN_PASSWORD_HASH`。

应用启动时也会执行旧版 `ADMIN_PASSWORD` 的迁移检查，因此恢复包含旧版密码字段的 `.env` 后，启动服务会按同一规则完成迁移。

不要把初始密码、密码哈希或 `.env` 提交到 Git。修改管理员凭据或其他配置后，确认权限为 `600`，再执行 `./scripts/restart.sh`。

## 2. 本地验证与服务管理

### 2.1 本地验证

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

安装脚本已经执行 production serving 验证。需要手动复核时运行：

```sh
./scripts/verify-frontend.sh
```

### 2.2 服务管理

```sh
./scripts/start.sh
./scripts/stop.sh
./scripts/restart.sh
```

这些脚本只管理 O3Pilot 的用户级 LaunchAgent，不管理 `cloudflared`。`restart.sh` 会等待旧的 LaunchAgent 完全卸载后再启动，避免 stop/start 竞态。

### 2.3 更新流程

```sh
./scripts/update.sh
```

`update.sh` 使用以下顺序：

```text
git pull --ff-only
Python dependency update
完整测试门禁（npm ci、Python unittest、Vue type-check/unit tests、shipping test）
staged Vue build（Vite build 和 artifact verification）
检查当前 launchd，并请求 http://127.0.0.1:38652/api/session
production SQLite 只读检查 sync_runs.status='running'
stop service，并等待 LaunchAgent 消失
frontend/dist → frontend/dist.previous
frontend/dist.next → frontend/dist
start service
验证 root、19 deep links、assets、API isolation
```

构建、type-check、Vite artifact verification 任一失败，或存在运行中的同步任务时，脚本不会停止/重启当前生产服务。新服务启动或 production serving 验证失败时，脚本会在服务停止期间恢复 `frontend/dist.previous`，新产物保留为 `frontend/dist.failed/` 供排查。脚本不执行 reset、clean，不覆盖 `.env`，不删除 `data/`。当前生产切换已通过该流程完成。

`frontend/dist.next/`、`frontend/dist.previous/` 和 `frontend/dist.failed/` 都是本地产物目录，不提交 Git。

### 2.4 Production serving

FastAPI 正式从 `frontend/dist/index.html` 提供 `/` 和 Vue history deep links；`/assets/*` 提供 Vite hashed assets，并对 index 设置 `Cache-Control: no-cache`。Legacy static frontend 已删除，`/static/*` 明确返回 404。

`/api/*`、`/static/*` 和 `/assets/*` 不进入 SPA fallback；`/static/*` 不会返回 Vue index，未知 API 继续返回认证/404 语义，缺失 asset 返回 404。生产入口仍为 `127.0.0.1:38652`，Cloudflare Tunnel Origin 不变。

## 3. Cloudflare Tunnel

O3Pilot 与 `cloudflared` 是两个独立服务。O3Pilot 只负责本机的 FastAPI 服务，`start.sh`、`stop.sh`、`restart.sh` 和 `update.sh` 不创建、启动、停止或更新 `cloudflared`。Tunnel 的账号、凭据和生命周期由 Cloudflare 管理。

### 3.1 安装 `cloudflared`

通过 Homebrew 安装并确认版本：

```sh
brew install cloudflared
cloudflared --version
```

### 3.2 创建 remotely-managed Tunnel

推荐使用 Cloudflare 官方控制台创建 remotely-managed Tunnel：

1. 确认域名已经添加到 Cloudflare，并使用 Cloudflare 名称服务器。
2. 登录 [Cloudflare Dashboard](https://one.dash.cloudflare.com/)。
3. 进入 **Networking > Tunnels**（或当前控制台对应的 Tunnel 管理页面）。
4. 选择 **Create a tunnel**，类型选择 `cloudflared`。
5. 选择 macOS 和当前 Mac 对应的架构，在 Connector 页面复制 Cloudflare 当前生成的安装命令。
6. 在运行 O3Pilot 的 Mac 上原样执行控制台生成的命令。命令通常类似：

   ```sh
   sudo cloudflared service install <TUNNEL_TOKEN>
   ```

7. 等待 Connector 上线，在 Cloudflare 控制台确认 Tunnel 状态为 `Healthy`。

`<TUNNEL_TOKEN>` 只是命令格式示例，不要替换为真实 Token 写入文档。Token 是敏感凭据：不要写入 `.env`，不要提交到 Git，不要出现在截图、Issue 或日志中。若 Token 泄露，应在 Cloudflare Tunnel 中刷新或轮换 Token，再按照控制台生成的新命令重新安装 Connector。

### 3.3 发布 O3Pilot 域名

在刚创建的 Tunnel 中添加 Published Application / Public Hostname：

1. 打开 **Routes > Add route > Published application**（或当前控制台中的 **Public Hostname** 配置）。
2. 选择已接入 Cloudflare 的域名并设置主机名，例如：

   ```text
   panel.example.com
   ```

3. Service / Origin 选择 `HTTP`，地址设置为：

   ```text
   http://127.0.0.1:38652
   ```

4. 保存后通过以下地址访问 O3Pilot：

   ```text
   https://panel.example.com
   ```

Origin 必须指向 O3Pilot 的本机固定地址；不使用备用端口，也不监听 `0.0.0.0`。该架构不需要公网 IPv4、公网 IPv6、DDNS、路由器端口映射、在主机或路由器开放 80/443 入站端口、Nginx、Caddy 或 Docker。

### 3.4 故障排查与维护

#### Tunnel 为 `Healthy`，但域名返回 `502`

先从运行 O3Pilot 的 Mac 直接检查本机入口：

```text
http://127.0.0.1:38652
```

确认该地址可以访问，再核对 Published Application / Public Hostname 的 Origin 是否仍为 `http://127.0.0.1:38652`。如果本机入口异常，查看 O3Pilot stderr 日志：

```sh
tail -f logs/opanel.stderr.log
```

同时检查用户级 LaunchAgent 状态：

```sh
launchctl print "gui/$(id -u)/com.opanel.app"
```

本机服务恢复后，可运行 `./scripts/verify-frontend.sh` 验证 production serving；如果本机地址正常而域名仍返回 `502`，再检查 Tunnel 的 Origin、Connector 和 Cloudflare 控制台状态。

#### Tunnel 为 `Down` 或 `Inactive`

- 检查 Mac 网络连接。
- 检查 macOS 上 `cloudflared` 服务是否仍在运行，并查看 Cloudflare 控制台中的 Connector 状态。
- 受限网络环境应允许 Cloudflare Tunnel 到 Cloudflare 的出站 `7844` 端口；按当前 Cloudflare 文档，QUIC 使用 UDP、HTTP/2 使用 TCP，其他目标和要求以[官方防火墙说明](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/)为准。
- 不要用 O3Pilot 的服务脚本代替 `cloudflared` 的服务管理；根据安装方式和 Cloudflare 当前文档处理 Connector 服务。

#### 更新 `cloudflared`

如果通过 Homebrew 安装，更新命令为：

```sh
brew upgrade cloudflared
```

更新后按照当前 Cloudflare 文档和本机实际安装方式重启或重新加载 `cloudflared` 服务，不在此文档中指定一个可能不适用于所有安装方式的固定 `launchctl` 命令。O3Pilot 的 `update.sh` 不更新或重启 `cloudflared`。

官方参考：[创建 remotely-managed Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)、[`cloudflared` 下载说明](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/)与[更新说明](https://developers.cloudflare.com/tunnel/downloads/update-cloudflared/)。

## 4. Ozon Webhook

### 4.1 生成 Webhook Secret

在项目根目录、安装并激活项目 `.venv` 后，使用 Python 标准库生成随机 Secret：

```sh
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

分别执行两次，为两个店铺生成不同的值，并填入：

```dotenv
OZON_WEBHOOK_SECRET_1=店铺1的Webhook随机密钥
OZON_WEBHOOK_SECRET_2=店铺2的Webhook随机密钥
```

两个店铺不得共用同一个 Secret。Secret 不应使用容易猜测的固定字符串，也不要提交到 Git、放入 README、Issue、截图或公开日志。

### 4.2 配置 Webhook 地址

保留项目现有 Webhook 格式，将发布后的 HTTPS 域名和对应店铺 Secret 组合为：

```text
https://你的域名/api/webhooks/ozon/<对应店铺密钥>
```

该端点只对 Ozon Push Webhook 豁免登录和 CSRF；业务事件会先写入 SQLite 收件箱，再异步补全订单详情。O3Pilot 不会在应用启动时自动注册订阅。日常使用时进入“推送订阅管理”，按店铺填写公网 Webhook URL，先检测连通性，再选择事件类型并创建、启用订阅。

如果整个 O3Pilot 域名启用了 Cloudflare Access，必须确保 Ozon 能够直接请求 `/api/webhooks/ozon/*`；否则 Ozon Push 请求可能被 Access 登录页或身份验证拦截。

## 5. Mac mini 基础运维

- 禁止 Mac 自动睡眠；允许显示器关闭。
- 如果当前 macOS 和硬件支持，开启断电恢复后自动启动。
- `logs/` 是本地日志目录，已加入 `.gitignore`；日志文件名以 `deploy/com.opanel.app.plist` 为准。

### 5.1 备份与恢复

默认生产数据目录为 `data/`：`data/opanel.db` 是 SQLite 数据库，`data/session_secret` 和 `data/session_generation` 是会话相关持久化文件，目录中其他文件也应一并保留。`.env` 保存管理员密码盐值/哈希、Ozon Seller/Performance API 凭据、Webhook Secret 和钉钉配置。

备份时建议先停止 O3Pilot 服务，再完整保存项目根目录下的以下内容：

- `data/`
- `.env`

不要只备份单个 SQLite 文件，也不要把备份提交到 Git。

恢复到已经完成安装的项目时：

1. 停止 O3Pilot 服务：

   ```sh
   ./scripts/stop.sh
   ```

2. 将备份的 `data/` 和 `.env` 恢复到项目根目录对应位置。
3. 确认 `.env` 权限：

   ```sh
   chmod 600 .env
   ```

4. 启动 O3Pilot：

   ```sh
   ./scripts/start.sh
   ```

5. 访问并验证：

   ```text
   http://127.0.0.1:38652
   ```

恢复流程不执行 SQLite 在线恢复、migration rollback 或数据库修复；如需从损坏备份恢复，应先使用一份可验证的完整备份。

## 6. O3Pilot 故障排查

### 登录提示未设置管理员密码哈希

确认项目根目录 `.env` 存在，并包含 `ADMIN_PASSWORD_SALT` 和 `ADMIN_PASSWORD_HASH`。如果首次安装未完成初始化，停止服务后重新执行安装流程；安装脚本会在没有可迁移旧密码时生成随机初始密码并只显示一次。恢复过 `.env` 后，确认权限为 `600`，再运行 `./scripts/restart.sh`。

如果 `.env` 中只有旧版 `ADMIN_PASSWORD` 且没有密码哈希，安装脚本会将其迁移为新的 `scrypt` 盐值和哈希，并移除旧字段。

### 服务已启动但本机无法访问

先查看用户级 LaunchAgent：

```sh
launchctl print "gui/$(id -u)/com.opanel.app"
```

再查看实际 stderr 日志：

```sh
tail -f logs/opanel.stderr.log
```

如果 stderr 出现 `Operation not permitted`，且项目位于 `~/Library/CloudStorage/` 等受 macOS 隐私控制的目录，这是 LaunchAgent 的路径访问权限问题，不是端口或 plist 参数问题。将项目放到 launchd 可读取的本机用户目录后重新安装，或按组织安全策略授予必要的访问权限；不要改为 root 运行。

### 固定端口已被占用

安装脚本会用 `lsof` 检查 `38652` 端口；如果已有进程监听，脚本会显示占用信息并停止安装，不会切换到其他端口。先处理占用该端口的进程，再重新运行安装。

### 默认数据库位置

按当前生产脚本，默认数据库为 `data/opanel.db`，会话相关文件位于 `data/session_secret` 和 `data/session_generation`。`update.sh` 会以只读方式检查 `data/opanel.db` 中是否存在运行中的同步任务；因此生产备份和恢复应保留整个 `data/` 目录。
