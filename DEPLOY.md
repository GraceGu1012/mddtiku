# DEPLOY · 微信云托管部署指引

## 你需要做的（一次性，约 10 分钟）

### 1. 开通云托管

mp.weixin.qq.com → 左侧「云托管」→ 开通 → 创建环境（地域选**上海**，计费选按量付费）。  
记下**环境 ID**（形如 `xxx-8g0a2b3c`）。

### 2. 创建服务并部署

1. 环境内「服务列表 → 新建服务」：服务名必须填 **`mdd-learner-api`**（与小程序 api.js 中 SERVICE_NAME 一致）
2. 上传方式选「本地上传代码包」，上传本目录的 `deploy-mdd-cloudrun.zip`
3. 监听端口填 **80**；实例规格默认（0.25C 0.5G 即可）；**最小副本数先设 0**（缩容到 0 不计费）

### 3. 配置环境变量（服务设置 → 环境变量）

| 变量                       | 值                                        | 说明                                        |
| ------------------------ | --------------------------------------- | ----------------------------------------- |
| `KNOWLEDGE_DATABASE_URL` | 见本目录「云托管环境变量-私密勿传.txt」             | 2026-11-14 已配好：mddcloud 专用角色 + TLS，库名 mdd_knowledge |
| `KNOWLEDGE_ENCRYPTION_KEY` | 见本目录「云托管环境变量-私密勿传.txt」               | 必须与服务器 master.key 一致，否则 DB 里已加密凭据解不开      |
| `DEEPSEEK_API_KEY`       | 不需要配                                    | 生成任务只跑在阿里云主实例（WORKER=0），云托管不发起 AI 调用 |

不配 `KNOWLEDGE_PUBLIC_ORIGIN`（云托管无网页端 Origin）、`KNOWLEDGE_WORKER` 已在镜像内置为 0。

### 4. 数据库公网回连（✅ 2026-11-14 已完成）

- Postgres 15 已改 `listen_addresses='*'` + SSL（复用 LE 证书），pg_hba 仅放行 `hostssl mdd_knowledge mddcloud` + scram-sha-256
- 专用角色 `mddcloud`（GRANT mddknowledge 成员，非 superuser）；安全组已放行 5432；外网 SSLRequest 验证通过
- 服务器配置备份：`/var/lib/pgsql/data/{postgresql,pg_hba}.conf.bak-20261114-*`；回滚 = 恢复备份 + restart

### 5. 部署验证

服务部署完成后，在云托管「服务设置 → 调用测试」或浏览器访问默认域名 `/api/learn/bootstrap`，返回 JSON 即通。

### 6. 小程序侧

1. 把 `miniprogram-cloud/utils/api.js` 里的 `CLOUD_ENV = 'TO_BE_FILLED'` 改成你的环境 ID
2. 用微信开发者工具打开 `miniprogram-cloud/` 目录预览，或我走 miniprogram-ci 出预览码
3. 注意：`callContainer` 要求小程序与云托管环境绑定（开通时自动绑定），真机需基础库 ≥ 2.4.0

## 回切/对照

- 原域名链路（等备案）不受任何影响；云托管链路是完全独立的新服务
- 备案接入通过后，只需把小程序 api.js 换回原版（BASE_URL 版），云托管可缩容 0 保底

## 已知限制

- 云托管实例**缩容到 0 时容器本地文件丢失**：learner 刷题流程不写本地文件，无影响；若以后要在云托管实例上跑材料上传/生成，需接对象存储（云托管内置 COS 挂载）
- 工作台（材料工作台/出题管理）仍只在阿里云域名端使用，云托管实例只服务小程序学习端
