# HANDOFF · mdd-cloudrun

写给零上下文的接手会话。项目背景见 README.md，部署步骤见 DEPLOY.md。

## 任务目标
gesturedraw.fun 被阿里云 SNI 拦截（ERR_CONNECTION_RESET），原方案（等备案接入）保留；为小程序新开一条**微信云托管**链路：callContainer → 云托管容器 → 公网回连阿里云 PostgreSQL。

## 已完成（2026-11-14）
- 后端代码已从服务器拉到 `backend/`（FastAPI 单应用，端口 14312 起家，DB=Postgres，密钥在服务器 /etc/mdd-knowledge/service.env）
- 依赖梳理完成：KNOWLEDGE_DATABASE_URL / KNOWLEDGE_STORAGE_DIR / KNOWLEDGE_ENCRYPTION_KEY（可 env 直传，不必带 master.key 文件）/ DEEPSEEK_API_KEY / KNOWLEDGE_WORKER / KNOWLEDGE_PUBLIC_ORIGIN
- 改造完成（仅 3 处）：app.py 云托管模式放开 Host 检查（CSRF/Origin/长度校验保留）；Dockerfile 对齐服务器目录布局；miniprogram-cloud/utils/api.js 改 callContainer
- 语法验证通过（py_compile + node --check）；部署包 deploy-mdd-cloudrun.zip 已打好（2.5M）

## 当前阻塞 / 待用户动作
1. 用户开通微信云托管（DEPLOY.md 第 1-3 步），拿到环境 ID 后回填 miniprogram-cloud/utils/api.js 的 CLOUD_ENV
2. **数据库公网回连方案需用户明确同意**（Postgres 对公网开放 5432 + 新建 mddcloud 角色），确认后由助手执行服务器配置
3. DEEPSEEK_API_KEY / KNOWLEDGE_ENCRYPTION_KEY 需用户从云托管控制台配置（值在服务器 /etc/mdd-knowledge/service.env 与 master.key，不要写进仓库）

## 下一步
- 云托管部署后验证 /api/learn/bootstrap 返回 JSON
- 小程序走 miniprogram-ci 出预览码真机验证（上传脚本在 yeahclass-new/scripts/ci-upload.mjs，工程指到 miniprogram-cloud/ 即可）
- 缩容到 0 的文件丢失限制：learner 流程无本地写，安全；后续若要云托管跑生成任务需接 COS 挂载 + 打开 KNOWLEDGE_WORKER

## 踩过的坑
- 本会话 shell 直接跑 npm/python 长命令会被 brokered-sandbox 注入搞超时，统一用 `env -i PATH=... HOME=... TMPDIR=... LANG=...` 白名单环境执行
- 服务器 nginx 有「仅允许本机访问」中间件，靠 `proxy_set_header Host 127.0.0.1:14312` 绕过——云托管没有 nginx 这层，所以必须在应用层放行（已用 KNOWLEDGE_CLOUD=1 实现）
- bootstrap.initialize() 启动即读 `/srv/designs/knowledge-agent-intake/data/manifest.json`（ROOT=APP.parents[1]），容器布局必须带 designs/ 种子数据，否则启动崩溃
