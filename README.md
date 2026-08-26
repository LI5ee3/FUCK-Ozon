# oPanel

oPanel 是一个专为 Ozon 跨境电商卖家打造的轻量级双店铺经营数据看板与分析系统。采用 FastAPI、SQLite 与纯原生现代前端（零构建工具、零外部网络依赖）开发，支持通过 Ozon Seller API 自动化同步与 CSV 历史数据导入，提供全链路的数据分析与决策支持。

## 主要功能

- **双店铺视图**：支持两个 Ozon 店铺独立切换管理或一键合并综合看板。
- **全履约模式支持**：覆盖 FBP、realFBS、WHD 三种履约渠道的销售与库存分类核算。
- **多维度数据分析**：
  - **总览看板**：核心经营 KPI 指标卡与日/月维度订单趋势图。
  - **订单全貌**：多状态筛选、履约时效计算、取消原因与数据异常识别。
  - **取消与风控**：多级取消原因归类穿透、高危商品 SKU 识别及成员贡献度分析。
  - **时效分析**：各物流渠道平均发货/运输/配送时效与长尾订单追踪。
  - **异常与纠纷**：取消明细、rFBS 退货记录以及已收货纠纷索赔追踪。
  - **库存与备货**：结合历史销量与预测算法的 FBP 智能备货建议。
- **数据流与自动化**：
  - **数据同步中心**：按月分段拉取、断点续传及全自动定时同步调度。
  - **导入与导出**：支持官方 CSV 报表导入，订单及各分析模块均可导出 UTF-8 JSONL。
- **商品规则映射**：支持 SKU 中文短名称映射与多 SKU/货号全局合并。
- **钉钉智能通知**：支持同步异常即时告警与昨日经营汇总定时推送。
- **安全与权限**：单管理员 `scrypt` 强哈希凭证校验、CSRF 严格校验与登录频次限速。

## 统计口径

- 剔除 `status='已取消' AND shipped=0` 的发货前取消订单。
- 订单数按 `posting_number` 去重。
- 商品件数按 `quantity` 求和。
- 页面上的 Ozon 时间统一转换为北京时间（UTC+8）。
- 日期型同步按自然月分段；各模块独立写入对应数据表。

## 技术栈与目录

```text
app/              FastAPI 后端服务、Ozon API 同步、CSV 导入及 SQLite 数据持久化
static/           纯原生前端页面（Macaron UI 体系、Tabler 矢量图标、物理形变组件）
data/             SQLite 数据库与会话密钥（自动创建，已加入 .gitignore）
compose.yaml      Docker Compose 服务配置
deploy.sh         Linux 服务器一键部署运维脚本
```

## 方式一：Docker 部署（推荐）

### 1. 环境要求

- 64 位 Linux 服务器。
- 已安装 Docker Engine 和 Docker Compose v2。
- 能够正常访问 `api-seller.ozon.ru`。

> `compose.yaml` 默认使用 host 网络模式，优先推荐用于 Linux 服务器。macOS 和 Windows 建议使用下文的本地 Python 运行方式。

### 2. 下载项目

```sh
git clone https://github.com/LI5ee3/oPanel.git
cd oPanel
```

### 3. 配置 Ozon API 密钥

在项目根目录创建 `.env`：

```sh
touch .env
chmod 600 .env
```

编辑 `.env`，填入两个店铺的 Seller API 凭据及钉钉配置：

```dotenv
SHOP_1_OZON_CLIENT_ID=店铺1的Client-Id
SHOP_1_OZON_API_KEY=店铺1的Api-Key
SHOP_2_OZON_CLIENT_ID=店铺2的Client-Id
SHOP_2_OZON_API_KEY=店铺2的Api-Key
OZON_WEBHOOK_SECRET_1=店铺1Webhook随机密钥
OZON_WEBHOOK_SECRET_2=店铺2Webhook随机密钥
# 若 Ozon Push 的 seller_id 与 Client-Id 不同，再填写对应 Seller ID
# SHOP_1_OZON_SELLER_ID=店铺1的Seller ID
# SHOP_2_OZON_SELLER_ID=店铺2的Seller ID
DINGTALK_WEBHOOK_URL=钉钉自定义机器人Webhook
DINGTALK_SECRET=钉钉机器人加签Secret
```

不要在密钥两侧添加引号，也不要把 `.env` 发送给他人或提交到 Git。

### 4. 启动

```sh
chmod +x deploy.sh
./deploy.sh
```

`deploy.sh` 会自动：

1. 将 `.env` 权限设置为 `600`。
2. 生成一个 `20000–60000` 之间的随机可用端口。
3. 生成随机管理员初始密码（仅在首次创建时在控制台展示）。
4. 构建 Docker 镜像并启动容器服务。

请立即保存终端输出的管理员密码。部署完成后访问：

```text
http://服务器IP:生成的端口
```

### 5. 验证服务

```sh
docker compose ps
docker compose logs --tail=100 app
```

如使用 1Panel、Nginx 或 Caddy，将 HTTPS 反向代理目标设置为：

```text
http://127.0.0.1:APP_PORT
```

`APP_PORT` 的实际值保存在 `.env` 中。

## 方式二：本地 Python 安装

### 1. 创建虚拟环境

建议使用 Python 3.14（或 Python 3.12+）：

```sh
git clone https://github.com/LI5ee3/oPanel.git
cd oPanel
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell 激活虚拟环境的命令为：

```powershell
.venv\Scripts\Activate.ps1
```

### 2. 创建 `.env`

用标准库生成管理员密码的盐和 `scrypt` 哈希：

```sh
python - <<'PY'
from app.security import password_hash
password = input("管理员密码：")
salt, digest = password_hash(password)
print(f"ADMIN_PASSWORD_SALT={salt}\nADMIN_PASSWORD_HASH={digest}")
PY
```

将输出和店铺凭据写入 `.env`：

```dotenv
ADMIN_PASSWORD_SALT=上一步生成的盐
ADMIN_PASSWORD_HASH=上一步生成的哈希
SHOP_1_OZON_CLIENT_ID=店铺1的Client-Id
SHOP_1_OZON_API_KEY=店铺1的Api-Key
SHOP_2_OZON_CLIENT_ID=店铺2的Client-Id
SHOP_2_OZON_API_KEY=店铺2的Api-Key
OZON_WEBHOOK_SECRET_1=店铺1Webhook随机密钥
OZON_WEBHOOK_SECRET_2=店铺2Webhook随机密钥
# 若 Ozon Push 的 seller_id 与 Client-Id 不同，再填写对应 Seller ID
# SHOP_1_OZON_SELLER_ID=店铺1的Seller ID
# SHOP_2_OZON_SELLER_ID=店铺2的Seller ID
DINGTALK_WEBHOOK_URL=钉钉自定义机器人Webhook
DINGTALK_SECRET=钉钉机器人加签Secret
```

macOS/Linux 继续执行：

```sh
chmod 600 .env
```

### 3. 启动本地服务

```sh
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

开启开发热更新：

```sh
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

然后访问 [http://127.0.0.1:8000](http://127.0.0.1:8000)。首次启动会在 `data/` 目录自动创建 SQLite 数据库和会话密钥。

## Ozon Push Webhook

将两个 `OZON_WEBHOOK_SECRET_*` 配置为不可复用的随机字符串，并让 Ozon 能通过 HTTPS 访问：

```text
https://你的域名/api/webhooks/ozon/<对应店铺的密钥>
```

该端点只对 Push Webhook 豁免登录和 CSRF；业务事件会先写入 SQLite 收件箱，再异步补全订单详情。管理员可登录后调用以下受保护接口检测、注册和查询 Ozon 订阅，不会在应用启动时自动注册：

```text
POST /api/ozon/notifications/push-types?shop_id=1
POST /api/ozon/notifications/check
POST /api/ozon/notifications/set
POST /api/ozon/notifications/list
POST /api/ozon/notifications/enable
POST /api/ozon/notifications/delete
```

订单与库存全量同步仍保留作初始化、FBP 数据来源和 Push 纠偏；其中 FBP 库存继续使用 Ozon 的库存接口。

## 钉钉机器人

在 `.env` 中填写 `DINGTALK_WEBHOOK_URL`；机器人启用了加签时同时填写 `DINGTALK_SECRET`。重启服务后进入“钉钉机器人”页面，可启用昨日取消订单汇总，并设置北京时间和推送星期。

- 任一独立同步失败后立即发送通知，不受定时汇总开关限制。
- 昨日汇总只读取数据库，不会自动拉取订单。
- 同一统计日期成功发送后不会重复发送。
- Webhook 和 Secret 不保存到 SQLite，也不会返回前端。

## 首次使用

1. 使用生成哈希时输入的管理员密码登录。
2. 在“系统设置”中修改两个店铺的显示名称。
3. 在右上角选择单个店铺或合并查看。
4. 进入“数据同步中心”，选择日期范围后分别拉取所需模块。页面默认为近三个月；长时段按自然月串行执行并显示进度，库存只拉取一次当前快照。也可按“店铺+模块”分别设置订单、退货和库存的每日自动同步，自定义北京时间及最近 1–365 天范围，同日成功任务不重复创建。
5. 如需补充历史数据，在“数据导入/导出”中选择店铺和数据类型后上传文件。

支持的导入文件：
- Ozon `FBP.csv`、`realFBS.csv`、`WHD.csv`，分隔符为分号。

## 日常运维

查看日志：

```sh
docker compose logs -f app
```

重启：

```sh
docker compose restart app
```

重新构建并更新：

```sh
docker compose up -d --build
```

停止：

```sh
docker compose down
```

备份时请同时保存：

- `data/`：数据库和会话密钥。
- `.env`：管理员密码哈希、端口和 Ozon API 凭据。

恢复时将两者放回项目根目录，确认 `.env` 权限为 `600`，再启动容器。

## 安全说明

- 不要将 `.env`、`data/`、CSV、XLSX 或任何真实店铺数据提交到 Git。
- 公网部署必须使用 HTTPS，不要直接暴露容器端口。
- 只授予 Ozon API 密钥项目所需的最小权限，密钥泄露后应立即轮换。
- 该项目为单管理员系统，不适合直接作为多租户或多用户服务。

## 常见问题

### 登录提示未设置管理员密码哈希

确认 `.env` 位于项目根目录，同时包含 `ADMIN_PASSWORD_SALT` 和 `ADMIN_PASSWORD_HASH`，然后重启服务。旧版 `ADMIN_PASSWORD` 会在部署或启动时一次性转换并从 `.env` 删除。

### API 拉取返回 401、403 或 502

检查店铺的 `Client-Id`、`Api-Key`、API 权限和请求日期范围。两个店铺的凭据不能混用。

### Docker 容器已启动但无法访问

先执行 `docker compose logs app`，然后检查 `.env` 中的 `APP_PORT`、服务器防火墙和反向代理配置。

### 数据库位置

默认数据库为 `data/opanel.db`。Docker 部署时 `data/` 会挂载到容器内的 `/app/data`。

## 开源协议与鸣谢

### 本项目协议

本项目采用 **[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)** 协议开源。

- 任何人在网络服务器部署、运行修改版本或提供相关网络服务（SaaS），均必须向使用者公开相应修改后的完整源代码。
- 详细条款请参阅根目录下的 [`LICENSE`](LICENSE) 文件。

### 第三方开源鸣谢

本项目前端交互与图标体系引用并改进了以下优秀的开源项目：

- **[Tabler Icons](https://tabler.io/icons)** (by [Paweł Kuna](https://github.com/codecalm))：全站统一采用其 24×24 规范矢量图标定义，遵循 **[MIT License](https://github.com/tabler/tabler-icons/blob/main/LICENSE)**（见 [`static/TABLER_ICONS_LICENSE`](static/TABLER_ICONS_LICENSE)）。
- **[Morphicons](https://github.com/guillermolg00/morphicons)** (by [Guillermo López](https://github.com/guillermolg00))：基于其 Apple Spring 弹簧物理形变与几何重采样算法，为本项目定制封装了零外部依赖、自包含内置 52 款图标的纯原生 `<morph-icon>` Web Component（见 [`static/morphicons.js`](static/morphicons.js)），遵循 **[MIT License](https://github.com/guillermolg00/morphicons/blob/main/LICENSE)**。
