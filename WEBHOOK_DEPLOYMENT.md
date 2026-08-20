# Ozon 主动推送部署

## 1Panel 与 HTTPS

Docker 应用监听 `.env` 中的 `APP_PORT`，使用 host 网络。1Panel 网站反向代理目标填写：

```text
http://127.0.0.1:<APP_PORT>
```

外部回调必须使用 HTTPS。反向代理需放行 `POST /api/ozon/push/*`，其他应用接口仍由管理员登录保护。生产容器已关闭 Uvicorn access log，避免 URL 中的店铺 token 进入普通访问日志。

在 1Panel 反向代理层仅允许 Ozon 当前官方推送地址访问该路径：

```text
195.34.21.0/24
185.73.192.0/22
91.223.93.0/24
```

应用不会信任任意 `X-Forwarded-For`，IP 白名单必须配置在 1Panel。

## 两个店铺的回调地址

1. 登录网站，打开“系统设置”。
2. 分别填写两个店铺的 `seller_id` 并保存。
3. 分别复制页面生成的回调 URL。
4. 不要把回调 URL、API 密钥或钉钉密钥提交到 Git 或发到公开渠道。

## 店铺1接入申请模板

```text
收件人：sapi-push@ozon.ru
seller_id：<店铺1 seller_id>
服务器URL：https://<域名>/api/ozon/push/<店铺1 token>
通知类型：
TYPE_PING
TYPE_NEW_POSTING
TYPE_POSTING_CANCELLED
TYPE_STATE_CHANGED
TYPE_FBO_POSTING_NEW
TYPE_FBO_POSTING_CANCELLED
TYPE_FBO_POSTING_STATE_CHANGED
TYPE_FBO_STOCKS_CHANGED
TYPE_STOCKS_CHANGED
```

## 店铺2接入申请模板

```text
收件人：sapi-push@ozon.ru
seller_id：<店铺2 seller_id>
服务器URL：https://<域名>/api/ozon/push/<店铺2 token>
通知类型：
TYPE_PING
TYPE_NEW_POSTING
TYPE_POSTING_CANCELLED
TYPE_STATE_CHANGED
TYPE_FBO_POSTING_NEW
TYPE_FBO_POSTING_CANCELLED
TYPE_FBO_POSTING_STATE_CHANGED
TYPE_FBO_STOCKS_CHANGED
TYPE_STOCKS_CHANGED
```

Ozon 通常最多需要三个工作日完成绑定。此文档只提供配置与申请模板；项目不会发送邮件，也不会修改 Ozon 账号。
