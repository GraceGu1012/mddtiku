# HISTORY · mdd-cloudrun

## 2026-11-14 项目创建
- 背景：gesturedraw.fun 遭阿里云 SNI 拦截（备案接入未完成），原方案保留，新增微信云托管链路
- 拉取后端代码并梳理依赖（FastAPI + psycopg2 + PyMuPDF 等，密钥全走环境变量）
- 3 处改造：app.py 云托管模式、Dockerfile（对齐服务器目录布局）、miniprogram-cloud callContainer 版 API
- py_compile / node --check 通过；deploy-mdd-cloudrun.zip（2.5M）就绪
- 待办：用户开通云托管环境 → 回填 CLOUD_ENV → 数据库公网回连（需用户确认）→ 部署验证 → CI 预览码真机测试

## 2026-11-14 数据库公网回连完成
- 环境ID prod-d1g3ohbkt443313be 已写入 miniprogram-cloud/utils/api.js
- Postgres 15：listen_addresses='*' + SSL（LE 证书），pg_hba 加 hostssl mdd_knowledge mddcloud 0.0.0.0/0 scram；新建角色 mddcloud（GRANT mddknowledge）；配置备份 bak-20261114-*
- 验证：服务器本机 TLS 连接查询 learners 21 行 OK；外网 5432 SSLRequest 探测 OK（安全组已放行）
- 发现：库名是 mdd_knowledge（非 knowledge_agent）；DEEPSEEK_API_KEY 不在 service.env，AI 凭据存 DB 加密列，云托管实例无需配
- 三个环境变量值已写入本地「云托管环境变量-私密勿传.txt」（不进仓库）
