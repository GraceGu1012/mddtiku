# mdd-cloudrun · 墨督督学习空间（微信云托管通道）

为绕开 gesturedraw.fun 备案拦截（阿里云 SNI 重置），为小程序新增一条**微信云托管**后端链路：
小程序 → `wx.cloud.callContainer`（微信内部通道，免域名/免备案）→ 云托管容器 → 公网回连阿里云 PostgreSQL。
原域名方案（等备案接入）保留不动，两套并存、随时可切。

## 目录结构

```
mdd-cloudrun/
├── Dockerfile              # 云托管容器构建文件（构建上下文=本目录）
├── .dockerignore
├── deploy-mdd-cloudrun.zip # 上传云托管用的部署包（Dockerfile + backend + designs 种子）
├── backend/                # 从服务器 /opt/mdd-knowledge/apps/knowledge-agent 拉取的 FastAPI 应用
│   ├── web/                # app.py 含云托管模式改造（KNOWLEDGE_CLOUD=1 放开 Host 限定）
│   └── intake/
├── designs/knowledge-agent-intake/   # bootstrap 启动所需的种子数据（服务器同款）
├── miniprogram-cloud/      # 云托管版小程序（utils/api.js 走 wx.cloud.callContainer）
└── DEPLOY.md               # 开通/部署/回切完整指引
```

## 与原版后端的差异（Surgical Changes，只改了 3 处）

1. `web/app.py`：新增 `KNOWLEDGE_CLOUD=1` 分支——云托管网关的 Host 不是 127.0.0.1，放开「仅允许本机访问」检查；CSRF/Origin/长度校验全部保留
2. `Dockerfile`：目录布局对齐服务器（`/srv/knowledge-agent` + `/srv/designs`），容器监听 0.0.0.0:80
3. `miniprogram-cloud/utils/api.js`：`wx.request` → `wx.cloud.callContainer`，其余逻辑（cookie/CSRF/401 重试）不变

## 关键约定

- 数据库：**PostgreSQL**（云托管不提供，公网回连阿里云本机 Postgres，见 DEPLOY.md，需用户确认后实施）
- 生成/解析 worker 在云托管实例中**关闭**（`KNOWLEDGE_WORKER=0`），AI 生成任务仍只在阿里云主实例跑，避免两实例抢任务
- 密钥不进镜像：DB 连接串 / DEEPSEEK_API_KEY / KNOWLEDGE_ENCRYPTION_KEY（= 服务器 master.key 内容）都在云托管控制台环境变量里配
