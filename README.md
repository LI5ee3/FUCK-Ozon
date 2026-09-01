# O3Pilot

O3Pilot 是一个面向 Ozon 跨境电商卖家的轻量级经营数据、运营分析与决策辅助系统。采用 FastAPI、SQLite 与 Vue 3 + TypeScript + Vite 前端，支持通过 Ozon Seller API 自动化同步与 CSV 历史数据导入，覆盖 Dashboard、Inventory、Ads、Profit、Risk、Timeliness、Alerts、Sync 等经营场景，并支持 FBP、realFBS、WHD 数据与 DingTalk 通知。

O3Pilot is an unofficial independent project and is not affiliated with or endorsed by Ozon.

O3Pilot 是独立的非官方项目，与 Ozon 无隶属、授权或背书关系。

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
frontend/         正式 Vue 3 + TypeScript + Vite production frontend source（构建输出为 frontend/dist）
frontend/public/assets/
                  Vue public assets 与第三方 License
data/             SQLite 数据库与会话密钥（自动创建，已加入 .gitignore）
scripts/          macOS 安装、启动、停止、重启、更新脚本
deploy/           launchd 服务配置模板
docs/             部署与业务口径文档
```

## Vue 前端与生产入口

`frontend/dist/` 是正式 Vue production frontend；FastAPI 的 `/` 与 Vue history deep links 从这里返回 SPA index，生产前端只由 `frontend/dist` 提供。

生产路由约定：`/` 与 deep links 返回 Vue，`/assets/*` 提供构建资产，`/api/*` 进入后端，`/static/*` 明确返回 404。

- Dashboard / 总览
- Orders / 订单
- Inventory / 销量与备货建议
- Analytics / 流量与搜索分析
- Ads Overview / 广告总览
- Ad Campaigns / 广告活动
- SKU Ads Analysis / SKU 广告分析
- Timeliness / 发货与配送时效
- Risk / 订单取消分析
- Returns / 异常订单明细
- Complaints / 异常订单投诉
- Alerts / 异常预警
- Profit / 实际利润
- Transfer / 数据导入导出
- Sync / 数据同步中心
- Rules / 商品匹配规则
- Push Subscriptions / 推送订阅管理
- DingTalk / 钉钉机器人
- Settings / 系统设置

Vite 默认将 `/api` 代理到稳定的本机 FastAPI 地址 `127.0.0.1:38652`。

```sh
cd frontend
npm ci
npm run dev
```

后端可按现有方式单独启动；若本地手动使用 Uvicorn 默认的 `127.0.0.1:8000`，可设置 `OPANEL_API_TARGET=http://127.0.0.1:8000` 后运行上面的开发命令。

提交前执行项目级核心检查：

```sh
./scripts/check.sh
```

该脚本依次运行仓库 unittest、Vue type-check、Vue unit tests、跨境运费规则 Node test 和 staged production build；不会启动生产服务、操作真实数据库或读取 Ozon 店铺数据。

## macOS + Apple Silicon 部署

生产环境为 Apple Silicon macOS，使用 Python venv、Node.js/npm、launchd 和 Cloudflare Tunnel。Python 3.14 优先，兼容 Python 3.12+；Vue build 支持 Node.js 22（>=22.18）、Node.js 24（>=24.11）或 Node.js >=25。

最简安装：

```sh
git clone https://github.com/LI5ee3/O3Pilot.git
cd O3Pilot
./scripts/install-macos.sh
```

本机固定访问地址：

```text
http://127.0.0.1:38652
```

服务管理入口：

```sh
./scripts/start.sh
./scripts/stop.sh
./scripts/restart.sh
./scripts/update.sh
```

完整的环境配置、`.env`、Cloudflare Tunnel、更新流程、日志、备份恢复和故障排查均以 [`docs/macos-deployment.md`](docs/macos-deployment.md) 为准。

## Ozon Push Webhook

将两个 `OZON_WEBHOOK_SECRET_*` 配置为不可复用的随机字符串，并让 Ozon 能通过 HTTPS 访问：

```text
https://你的域名/api/webhooks/ozon/<对应店铺的密钥>
```

该端点只对 Push Webhook 豁免登录和 CSRF；业务事件会先写入 SQLite 收件箱，再异步补全订单详情。O3Pilot 不会在应用启动时自动注册订阅。

日常使用时进入“推送订阅管理”，按店铺填写对应的公网 Webhook URL，先检测连通性，再选择事件类型并创建、启用订阅；页面会显示当前订阅及状态。对应的受保护接口为：

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

1. 使用安装脚本生成的管理员密码登录。
2. 在“系统设置”中修改两个店铺的显示名称。
3. 在右上角选择单个店铺或合并查看。
4. 进入“数据同步中心”，选择日期范围后分别拉取所需模块。手动同步默认为近 7 天，长时段按自然月串行执行并显示进度，库存只拉取一次当前快照；汇率同步范围独立默认为近三个月。也可按“店铺+模块”分别设置订单、退货、库存及广告统计的 1–24 小时自动同步频率与最近 1–365 天范围，库存固定为实时快照，同槽位成功或运行中的任务不重复创建。
5. 如需补充历史数据，在“数据导入/导出”中选择店铺和数据类型后上传文件。

支持的导入文件：
- Ozon `FBP.csv`、`realFBS.csv`、`WHD.csv`，分隔符为分号。

## 安全说明

- 不要将 `.env`、`data/`、CSV、XLSX 或任何真实店铺数据提交到 Git。
- 公网访问使用 Cloudflare Tunnel 的 HTTPS 域名；O3Pilot 不直接暴露公网端口。
- 只授予 Ozon API 密钥项目所需的最小权限，密钥泄露后应立即轮换。
- 该项目为单管理员系统，不适合直接作为多租户或多用户服务。

## 常见问题

### API 拉取返回 401、403 或 502

检查店铺的 `Client-Id`、`Api-Key`、API 权限和请求日期范围。两个店铺的凭据不能混用。

## 开源协议与鸣谢

### 本项目协议

本项目采用 **[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)** 协议开源。

- 任何人在网络服务器部署、运行修改版本或提供相关网络服务（SaaS），均必须向使用者公开相应修改后的完整源代码。
- 详细条款请参阅根目录下的 [`LICENSE`](LICENSE) 文件。

### 第三方开源鸣谢

本项目前端交互与图标体系引用并改进了以下优秀的开源项目：

- **[Tabler Icons](https://tabler.io/icons)** (by [Paweł Kuna](https://github.com/codecalm))：全站统一采用其 24×24 规范矢量图标定义，遵循 **[MIT License](https://github.com/tabler/tabler-icons/blob/main/LICENSE)**（见 [`frontend/public/assets/TABLER_ICONS_LICENSE`](frontend/public/assets/TABLER_ICONS_LICENSE)）。
- **[Morphicons](https://github.com/guillermolg00/morphicons)** (by [Guillermo López](https://github.com/guillermolg00))：官方 `morphicons` npm 依赖，经 `morphicons/vue` 的 `MorphIcon` 组件提供 Apple Spring 弹簧物理形变动画；O3Pilot 实际使用的 Tabler Icons path 数据收敛在轻量注册表 [`frontend/src/shared/icons/tabler.ts`](frontend/src/shared/icons/tabler.ts)，遵循 **[MIT License](https://github.com/guillermolg00/morphicons/blob/main/LICENSE)**。
