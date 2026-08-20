# FUCK Ozon

双店铺、单管理员的 Ozon 数据分析网站。FastAPI + SQLite + 原生前端，统计统一剔除发货前取消订单，前端时间统一显示北京时间。

## 部署

```sh
chmod +x deploy.sh
./deploy.sh
```

首次运行会把随机 `20000–60000` 端口和随机管理员密码写入权限收紧的 `.env`。容器使用 host 网络，交由 1Panel 配置反向代理；数据持久化到 `./data`。

API 密钥未写入源码。在 `.env` 中配置 `SHOP_1_OZON_CLIENT_ID`、`SHOP_1_OZON_API_KEY`、`SHOP_2_OZON_CLIENT_ID`、`SHOP_2_OZON_API_KEY`，并执行 `chmod 600 .env`。

## 本地验证

```sh
python -m pip install -r requirements.txt
ADMIN_PASSWORD=dev-password uvicorn app.main:app --reload
python -m unittest tests.test_import -v
```

已实现登录、双店铺改名、CSV/马帮成本导入、总览、订单卡片、SKU风险、JSONL订单导出、主题切换，以及订单、财务、退货、Premium、库存、价格、买家问答七个独立 API 拉取。财务自动按不超过30天拆分；库存和价格保存当前快照；所有模块各写各自数据表。
