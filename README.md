# FUCK Ozon

FUCK Ozon 是一个面向 Ozon 卖家的双店铺、单管理员数据分析网站。项目使用 FastAPI、SQLite 和原生 HTML/CSS/JavaScript，可以独立拉取 Ozon Seller API 数据，也可以导入 Ozon CSV 与马帮成本表进行补充分析。

## 主要功能

- 两个 Ozon 店铺独立管理或合并查看。
- 订单、财务、退货、Premium 分析、库存、价格和买家问答七个独立 API 拉取模块。
- FBP、realFBS、WHD 三种履约模式分类统计。
- Ozon CSV 订单导入和马帮 XLSX 订单成本导入。
- 总览、订单卡片、SKU 风险、JSONL 订单导出和深色主题。
- 单管理员密码登录，API 密钥与数据库均不进入 Git。

## 统计口径

- 剔除 `status='已取消' AND shipped=0` 的发货前取消订单。
- 订单数按 `posting_number` 去重。
- 商品件数按 `quantity` 求和。
- 页面上的 Ozon 时间统一显示为北京时间。
- 财务拉取自动按不超过 30 天的时间窗分段请求。
- 库存和价格以快照方式保存，各拉取模块只写入自己的数据表。

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
- 如需公网访问，准备域名和 HTTPS 反向代理。

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

```dotenv
ADMIN_PASSWORD=请设置一个高强度管理员密码
SHOP_1_OZON_CLIENT_ID=店铺1的Client-Id
SHOP_1_OZON_API_KEY=店铺1的Api-Key
SHOP_2_OZON_CLIENT_ID=店铺2的Client-Id
SHOP_2_OZON_API_KEY=店铺2的Api-Key
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

## 首次使用

1. 使用 `.env` 中的 `ADMIN_PASSWORD` 登录。
2. 在“系统设置”中修改两个店铺的显示名称。
3. 在左上角选择单个店铺。
4. 进入“独立同步中心”，选择日期范围后分别拉取所需模块。页面默认为近三个月。
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
- `.env`：管理员密码、端口和 Ozon API 凭据。

恢复时将两者放回项目根目录，确认 `.env` 权限为 `600`，再启动容器。

## 安全说明

- 不要将 `.env`、`data/`、CSV、XLSX 或任何真实店铺数据提交到 Git。
- 公网部署必须使用 HTTPS，不要直接暴露容器端口。
- 只授予 Ozon API 密钥项目所需的最小权限，密钥泄露后应立即轮换。
- 该项目为单管理员系统，不适合直接作为多租户或多用户服务。

## 常见问题

### 登录提示未设置 `ADMIN_PASSWORD`

确认 `.env` 位于项目根目录，包含非空的 `ADMIN_PASSWORD`，然后重启服务。

### API 拉取返回 401、403 或 502

检查店铺的 `Client-Id`、`Api-Key`、API 权限和请求日期范围。两个店铺的凭据不能混用。

### Docker 容器已启动但无法访问

先执行 `docker compose logs app`，然后检查 `.env` 中的 `APP_PORT`、服务器防火墙和反向代理配置。

### 数据库位置

默认数据库为 `data/fuck-ozon.db`。Docker 部署时 `data/` 会挂载到容器内的 `/app/data`。
