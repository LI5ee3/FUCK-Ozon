# FUCK Ozon

FUCK Ozon 是一个面向 Ozon 卖家的双店铺、单管理员数据分析网站。项目使用 FastAPI、SQLite 和原生 HTML/CSS/JavaScript，可以独立拉取 Ozon Seller API 数据，也可以导入 Ozon CSV 与马帮成本表进行补充分析。

## 主要功能

- 两个 Ozon 店铺独立管理或合并查看。
- 订单、财务、退货和库存四个独立 API 拉取模块。
- FBP、realFBS、WHD 三种履约模式分类统计。
- Ozon CSV 订单导入和马帮 XLSX 订单成本导入。
- 订单利润、投诉管理、商品匹配规则、SKU 风险、时效、退货和统一库存。
- 订单及七个分析模块可分别导出 UTF-8 JSONL。
- 单管理员 `scrypt` 强哈希登录、CSRF 防护和登录失败限速。
- 九种 Ozon 主动推送事件双店铺隔离接收，订单与库存实时幂等更新。

## 统计口径

- 剔除 `status='已取消' AND shipped=0` 的发货前取消订单。
- 订单数按 `posting_number` 去重。
- 商品件数按 `quantity` 求和。
- 页面上的 Ozon 时间统一显示为北京时间。
- Ozon 财务账单始终按 RUB 保存和显示；订单原币、店铺回款币种、RUB 账单和 CNY 成本分开。
- 缺少可靠汇率时不计算人民币利润，每次换算保留原币、汇率、来源和日期。
- 日期型同步按自然月分段，财务再限制为最多 30 天窗口；各模块只写自己的数据表。

## 技术栈与目录

```text
app/              FastAPI 接口、Ozon API 同步、导入和数据库逻辑
static/           原生前端页面
data/             SQLite 数据库与会话密钥，自动创建且不进入 Git
compose.yaml      Docker Compose 配置
deploy.sh         Linux 服务器一键部署脚本
```

## 方式一：Docker 部署（推荐）

### 1. 环境要求

- 64 位 Linux 服务器。
- 已安装 Docker Engine 和 Docker Compose v2。
- 能够访问 `api-seller.ozon.ru`。

> `compose.yaml` 使用 host 网络，优先用于 Linux 服务器。macOS 和 Windows 建议使用后文的本地 Python 安装方式。

### 2. 下载项目

```sh
git clone https://github.com/LI5ee3/FUCK-Ozon.git
cd FUCK-Ozon
```

### 3. 配置 Ozon API 密钥

在项目根目录创建 `.env`：

```sh
touch .env
chmod 600 .env
```

编辑 `.env`，填入两个店铺的 Seller API 凭据：

```dotenv
SHOP_1_OZON_CLIENT_ID=店铺1的Client-Id
SHOP_1_OZON_API_KEY=店铺1的Api-Key
SHOP_2_OZON_CLIENT_ID=店铺2的Client-Id
SHOP_2_OZON_API_KEY=店铺2的Api-Key
DINGTALK_WEBHOOK_URL=钉钉自定义机器人Webhook
DINGTALK_SECRET=钉钉机器人加签Secret
```

不要在密钥两侧添加引号，也不要把 `.env` 发送给他人或提交到 Git。

### 4. 启动

```sh
chmod +x deploy.sh
./deploy.sh
```

`deploy.sh` 会：

1. 将 `.env` 权限设置为 `600`。
2. 生成一个 `20000–60000` 之间的随机端口。
3. 生成随机管理员密码并只在首次创建时显示。
4. 构建镜像并启动容器。

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

建议使用 Python 3.14：

```sh
git clone https://github.com/LI5ee3/FUCK-Ozon.git
cd FUCK-Ozon
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

然后访问 [http://127.0.0.1:8000](http://127.0.0.1:8000)。首次启动会在 `data/` 目录创建 SQLite 数据库和会话密钥。

## 钉钉机器人

在 `.env` 中填写 `DINGTALK_WEBHOOK_URL`；机器人启用了加签时同时填写 `DINGTALK_SECRET`。重启服务后进入“钉钉机器人”页面，可启用昨日取消订单汇总，并设置北京时间和推送星期。

- 任一独立同步失败后立即发送通知，不受定时汇总开关限制。
- 昨日汇总只读取数据库，不会自动拉取订单。
- 同一统计日期成功发送后不会重复发送。
- Webhook 和 Secret 不保存到 SQLite，也不会返回前端。

## Ozon 主动推送

部署和申请步骤见 [WEBHOOK_DEPLOYMENT.md](WEBHOOK_DEPLOYMENT.md)。每个店铺使用独立回调地址；回调 token 只在登录后的“系统设置”中显示。

## 首次使用

1. 使用生成哈希时输入的管理员密码登录。
2. 在“系统设置”中修改两个店铺的显示名称。
3. 在左上角选择单个店铺。
4. 进入“独立同步中心”，选择日期范围后分别拉取所需模块。页面默认为近三个月；长时段按自然月串行执行并显示进度，库存只拉取一次当前快照。
   也可按“店铺+模块”分别设置订单、财务、退货和库存的每日自动同步，自定义北京时间及最近 1–365 天范围，同日成功任务不重复创建。
5. 如需补充历史数据，在“数据导入/导出”中选择店铺和数据类型后上传文件。

支持的导入文件：

- Ozon `FBP.csv`、`realFBS.csv`、`WHD.csv`，分隔符为分号。
- 马帮 `.xlsx` 成本表，必须包含“订单编号”、“汇率(原币)”和“商品总成本”列。

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

默认数据库为 `data/fuck-ozon.db`。Docker 部署时 `data/` 会挂载到容器内的 `/app/data`。
