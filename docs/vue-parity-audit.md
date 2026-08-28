# Phase 18：全站 Vue Parity / Full QA 审计

## 结论

**Phase 18：BLOCKED。**

静态代码、API 契约、认证/CSRF、隔离数据库读写和自动化检查均已执行；必需的 Legacy/Vue 浏览器逐页比对未完成，因为当前环境缺少规定的 Browser runtime（`browser-client.mjs` 无法加载）。因此不能把桌面、窄屏、浅色、深色、Console 或真实浏览器交互标记为通过，也不进入 Phase 19。

本次没有发现可由静态/API证据确认的 P0/P1/P2 parity defect；浏览器未执行意味着视觉、响应式和真实交互缺陷仍未完成排除。

## 审计范围与证据

| 项目 | 结果 |
| --- | --- |
| 审计 revision | `06b8569 Finalize login and app shell` |
| Legacy 对照 | `static/index.html`、`static/app.js`、现有 FastAPI API |
| Vue 范围 | 19 个页面 route，另含 Login / App Shell |
| 代码允许范围 | `frontend/`、`tests/test_vue_parity.py`、本文件、README 的 blocked 记录 |
| 明确未修改 | `app/`、`static/`、`scripts/`、`deploy/`、`requirements.txt`、DB schema、`.env`、Vite/package 文件 |
| 证据分级 | `PASS` = 静态/API/自动化证据；`BLOCKED` = 需要浏览器的验收项 |

## QA 环境与安全边界

| 项目 | 记录 |
| --- | --- |
| 临时 QA root | `/tmp/opanel-phase18-wL9fzO`，已删除 |
| Backend | `127.0.0.1:38653`，仅临时复制目录 |
| Vue Vite | 目标 `127.0.0.1:5174`；未将 QA 服务留在后台 |
| DB source | 生产 `data/opanel.db` 仅以 SQLite backup API 只读打开，再复制到临时 DB |
| QA 数据 | 两店快照；只在复制库关闭 scheduler/notification 后使用 |
| Temporary Admin Auth | 使用临时密码哈希/盐建立登录链路；密码、hash、cookie 未写入报告 |
| External credentials | Ozon、DingTalk、Performance、Webhook credentials 均未注入 |
| 生产保护 | 未读取生产 `.env`/session secret；未写生产 DB；未调用生产 Ozon/DingTalk |

## 全局 Gate

| Gate | 结果 | 证据/备注 |
| --- | --- | --- |
| 19 route 静态入口 | PASS | router 显式 lazy import，未发现 PlaceholderView |
| Auth 登录 | PASS | 临时 QA backend：正确密码 HTTP 200，随后 Session authenticated |
| Wrong password once | PASS | 临时 QA backend 返回 HTTP 401 |
| Session restore | PASS | 登录后 GET `/api/session` 返回 authenticated |
| Logout | PASS | POST `/api/logout` 返回 HTTP 200，随后 Session 为未认证 |
| Protected 401 | PASS | 未认证访问 `/api/shops` 返回 HTTP 401 |
| CSRF | PASS | 受保护 POST 无 token 返回 403；带真实 QA token 可通过 |
| Deep-link HTML | PASS（HTTP only） | Vite dev server 返回 19 个 route 的 HTTP 200；这不是浏览器交互验收 |
| Legacy/Vue browser compare | BLOCKED | Browser plugin 规定的 module 路径不存在 |
| Console/Network browser gate | BLOCKED | 未能取得真实浏览器 Console/Network |
| Desktop 1440×900 | BLOCKED | 未执行 |
| Narrow 390×844 | BLOCKED | 未执行 |
| Light/Dark/system | BLOCKED | 代码存在主题状态机，但未完成浏览器切换验收 |

## 19-route parity matrix

所有 route 的 `Status` 都受同一 Browser gate 约束。`Static/API` 记录的是已完成的源代码和接口核对，不等同于浏览器 PASS。

| Route | Legacy 页面/loader | Vue view | API / 数据契约 | 控件、字段与行为 | Loading / Error / Empty | Mutation / 外部副作用 | Static/API | Desktop Light / Dark / Narrow | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/` | `#overview` / `loadOverview`, `loadTrend` | `DashboardView.vue` | `/api/summary`、`/api/order-trend` | 店铺、日期快捷范围、周/月/日趋势；GMV、订单、渠道、时效、Top 5 | loading、重试错误、各面板 `NEmpty` | 只读 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/orders` | `#orders` / `loadOrders` | `OrdersView.vue` | `/api/orders`，`shop_id/channel/status/q/page/from/to` | 搜索、渠道、日期、状态 chips、服务端分页、订单展开、复制 | NDataTable loading、错误重试、空订单 | 只读 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/analytics` | `#analytics` / `loadAnalyticsData`, `loadProductQueries`, `loadProductQueryDetails` | `AnalyticsView.vue` | `/api/analytics/data`、`/api/analytics/product-queries`、`details` | 流量/搜索 tabs、SKU、日期、独立页码、关键词详情 | 三组 loading/error/empty 独立处理 | 只读；无外部凭据时 502 为预期环境结果 | PASS* | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/ads` | `#adOverview` / `loadAdOverview` | `AdsView.vue` | `/api/performance/overview` | 日期、9 项广告 KPI、趋势 | loading、错误重试、无日统计 empty | 只读；Performance 无凭据时不调用外部服务 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/ads/campaigns` | `#adCampaigns` / `loadAdCampaigns` | `AdCampaignsView.vue` | `/api/performance/campaign-stats` | 日期、状态、排序、50 条分页；campaign、预算、曝光、点击、CTR、花费、DRR、ROAS | table loading、错误重试、empty | 只读 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/ads/skus` | `#adSkus` / `loadAdSkus` | `AdSkusView.vue` | `/api/performance/sku-stats` | 日期、SKU/商品搜索、排序、50 条分页、复制 SKU；保留 shop 维度 | table loading、错误重试、empty | 只读 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/timeliness` | `#timeliness` / `loadTimeliness` | `TimelinessView.vue` | `/api/timeliness` | 日期、订单搜索、渠道/店铺时效矩阵、明细分页 30 | loading、错误重试、矩阵/明细 empty | 只读；P50/P90 等由后端返回 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/risk` | `#risk` / `loadRisk`, `renderRiskItems` | `RiskView.vue` | `/api/risk`、`/api/risk/reasons` | 日期、SKU/货号/商品搜索、≥15% 高危筛选、原因展开、订单号/主货号复制；FBP/realFBS/WHD | loading、错误重试、矩阵/原因/明细 empty | 只读；取消率和合并统计不在 Vue 重算 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/returns` | `#returns` / `loadReturns`, `loadRfbsReturns` | `ReturnsView.vue` | `/api/returns`、`/api/rfbs-returns` | 取消/退货 tabs、日期、独立搜索和页码、上一页/下一页、复制 | 两分支独立 loading/error/empty | 只读；不调用 Complaints | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/alerts` | `#alerts` / `loadAlertSummary`, `loadAlerts`, `loadAlertRules` | `AlertsView.vue` | `/api/alerts`、summary、`/api/alert-rules` | 状态/严重级别/分类/搜索、预警摘要、已读、规则开关和配置 | loading、错误重试、列表 empty | acknowledge、evaluate、rule PUT；只在 QA DB 验证 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/complaints` | `#complaintPlaceholder` / `loadShippingComplaints`, `loadReceivedDisputes` | `ComplaintsView.vue` | shipping/received GET + PUT | 发货未收货/已收货纠纷 tabs、状态/搜索/日期/分页、复制、买家留言、编辑表单、截止日期/金额 | 两分支独立 loading/error/empty | 两个 PUT 在临时 DB 验证；业务分支保持独立 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/inventory` | `#stock` / `loadStock` | `InventoryView.vue` | `/api/stock` | SKU、货号、商品名、库存参考口径、风险、排序、分页 50；FBP/realFBS/WHD 展示 | loading、错误重试、empty | 只读；不在 Vue 创建算法 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/profit` | `#profit` / `loadProfitPage`, `renderProfitCalculator` | `ProfitView.vue` | 无 API；`utils/profit.ts` | 店铺币种、FBP/realFBS、香港/深圳、售价、采购价、重量、汇率、费用/利润 | 输入未完整时显示 `—`/提示 | 纯前端，无网络/DB 副作用 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/transfer` | `#transfer` / `loadImports`, export handlers | `TransferView.vue` | `/api/import/{kind}`、`/api/imports`、四项 export | CSV 拖放/选择、店铺、渠道、50MB 校验、日期、orders/risk/returns/complaints JSONL 导出 | import/history loading/error/empty；单项 export loading | import 会写 DB；本轮未用业务文件写入；四项 export HTTP 已验 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/sync` | `#sync` / `loadSync`, `loadExchangeRates`, `loadAutoSync` | `SyncView.vue` | sync、Performance sync、exchange、auto-sync endpoints | 手动模块/日期、汇率、自动同步开关/频率/范围、历史轮询 | 各模块 loading/error/empty；有限轮询 | 外部同步未执行（无凭据）；仅读取快照配置 | PASS* | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/rules` | `#rules` / `loadRules` | `RulesView.vue` | `/api/product-rules` GET/PUT | 短名称搜索/新增/编辑/删除；SKU/货号合并、成员、冲突 | loading、重试、列表 empty | 短名称 PUT 在 QA DB 验证；合并路径未做额外写入 | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/push-subscriptions` | `#pushSubscriptions` / `loadPushSubscriptions` | `PushSubscriptionsView.vue` | Ozon push types/check/set/list/enable/delete | 每店 webhook、事件 checkbox、检测、注册/更新、启停、删除；mask/fallback/partial error | 每店 loading、API/列表/操作错误、empty | 外部 Ozon mutation 未执行；源代码保留 mask 和 `Promise.allSettled` 分店隔离 | PASS* | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/dingtalk` | `#dingtalk` / `loadDingtalk` | `DingTalkView.vue` | `/api/dingtalk/settings` GET/PUT | 摘要、每日汇总开关、推送时间、星期、最近投递 | loading、重试、保存错误 | 计划 PUT 在 QA DB 验证；模板/发送仍为 backend-only | PASS | BLOCKED / BLOCKED / BLOCKED | BLOCKED |
| `/settings` | `#settings` / `loadSettings`, `saveShopNames`, probe handlers | `SettingsView.vue` | `/api/shops`、`/api/ozon/probe/{shop_id}` | system/light/dark、店铺展示名、API 权限诊断、复制身份信息 | loading、重试、每店 probe 状态/错误 | 店铺名 PUT 在 QA DB 验证；Ozon probe 未执行 | PASS* | BLOCKED / BLOCKED / BLOCKED | BLOCKED |

`*` 表示 API 主路径已检查；该页面含外部服务或浏览器交互，不能由无凭据 HTTP 结果替代完整 UI 验收。

## API、数据和业务口径核验

- `/api/summary`、`/api/orders`、广告、时效、风险、Returns、Complaints、库存、Alerts、DingTalk、Rules、Sync、shops 和四项 export 均完成认证 HTTP smoke；`shop_id=0/1/2` 的组合/分店结构按接口返回检查。
- `/api/analytics/data` 与 `/api/analytics/product-queries` 在没有外部 Seller/Ozon credentials 的隔离环境返回 502，记录为预期环境限制，不改后端或伪造成功数据。
- `/api/stock` 默认排序返回 200；响应核对 `lead_time_days=25`、`target_cover_days=60`、`inbound_included=false`。库存口径仍为预测需求 FBP + realFBS、补货基准仅 FBP、WHD 不参与补货，overstock 边界严格 `>90`。
- 广告页面只调用 Performance 本地统计 API；未把 Seller Analytics API 偷换为广告数据来源。
- export 响应为 `application/x-ndjson`，四项保留模块为 orders、risk、returns、complaints；未恢复 timeliness、stock、rules export。
- 真实字段由后端返回；Vue 未重算风险率、P50/P90、截止日期、合并店铺指标或库存算法。

## Authenticated QA 与临时写入

认证链路在隔离 backend 完成：错误密码 401、正确登录 200、Session restore、protected 401、缺 CSRF 403、带 CSRF 的本地 POST 200、登出 200。

只在复制数据库执行并恢复/删除的写入：

| 功能 | 结果 |
| --- | --- |
| 店铺展示名 | PUT 200；随后恢复原名 |
| DingTalk 计划 | PUT 200；随后恢复原设置 |
| Alert rule | PUT 200；随后恢复原开关 |
| Product short name | 新增/编辑/删除均 200 |
| Shipping complaint | PUT 200；临时记录删除 |
| Received dispute | PUT 200；临时记录删除 |

生产库写入为 0；没有对生产服务 `38652` 执行 stop/start/restart、部署或切换入口。

## Findings

| ID | Severity | Page | Problem | Fix | Test / evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| QA-GATE-001 | Release blocker | 全站 19 routes | 规定的 Browser runtime module 不存在，无法打开认证浏览器、对照 Legacy/Vue、检查 Console/Network、1440×900、390×844、Light/Dark | 无代码修复；需要恢复 Browser plugin runtime 后重跑 Phase 18 | `mcp__node_repl__js` 按 Browser skill 指定路径加载失败 | BLOCKED |

**No P0/P1/P2 parity defects found in the executed static/API scope.** 不能把这句话解释为浏览器验收完成。

## Console / Network

真实浏览器 Console/Network 未取得，因此以下项目为 BLOCKED 而不是“无错误”：unexpected console errors、warnings、404、405、CSRF 403、unhandled rejection。HTTP 层已观察到的 401/403 是预期认证安全行为；Analytics 的 502 是无外部 credentials 的预期隔离环境结果。

## Responsive / Theme

静态 CSS 已存在 1360/1260/1180/1100/980/900/800/720/640 等断点，App shell 在 `max-width:800px` 默认折叠侧栏；`useTheme` 有 system/light/dark 和 `prefers-color-scheme` 监听。但没有浏览器截图或 DOM 实测，19 页面在 1440×900、390×844 的最终状态均保持 BLOCKED。

## Tests and bundle

| Check | Result |
| --- | --- |
| Python `unittest discover -s tests -p 'test_*.py'` | PASS，166 tests |
| `node tests/test_profit_calculator.js` | PASS，5 tests |
| `node --check static/app.js` | PASS |
| `npm run type-check` | PASS |
| `npm run build` | PASS |
| `git diff --check` | PASS |
| `tests/test_vue_shell.py` | included in the 166-test suite |
| `tests/test_vue_parity.py` | added; route/auth/API/frozen-policy/security-boundary checks |

Build produced all 19 lazy route chunks. Shared chunks include `date` 156.88 kB, `client` 170.33 kB, main index 344.11 kB and ECharts renderer 468.67 kB; all route chunks were split separately and the current build emitted no >500 kB warning. Bundle optimization remains outside this phase.

## QA cleanup and release status

- Temporary Backend was stopped; Vite QA process was not left running.
- Temporary QA root, DB copy, temporary password file and session artifacts were deleted.
- `app/`、`static/`、production `.env`、production DB、launchd、Cloudflare Tunnel、38652 production service均未修改。
- Phase 19 未启动；`static/` 仍是生产前端，`frontend/dist` 尚未切换生产入口。

## Phase 18 release gate

| Gate | Status |
| --- | --- |
| Static/API/automated coverage | PASS |
| Authenticated isolated backend | PASS |
| Browser runtime | BLOCKED |
| 19 route Legacy/Vue visual and responsive comparison | BLOCKED |
| Phase 18 overall | **BLOCKED** |
| Phase 19 cutover | NOT STARTED |

下一步只能是先恢复规定的 Browser runtime，再重新执行 19 route 的认证浏览器对照和 Release Gate。
