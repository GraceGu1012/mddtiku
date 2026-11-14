# MEMORY · mdd-cloudrun

- 云托管环境：用户开通后环境 ID 填 `miniprogram-cloud/utils/api.js` 的 CLOUD_ENV；服务名固定 `mdd-learner-api`
- 数据库：PostgreSQL（用户硬性规则），云托管无 PG，方案=公网回连阿里云 8.130.110.58:5432，专用角色 mddcloud + hostssl + scram + sslmode=require
- 云托管实例 KNOWLEDGE_WORKER=0（生成任务只在阿里云端跑）；KNOWLEDGE_CLOUD=1 是放开 Host 检查的开关
- 代码同步：服务器为准，rsync 拉取时排除 venv/runtime/__pycache__；designs/knowledge-agent-intake 种子数据必须随镜像带上
- 关联文档：DEPLOY.md（部署步骤）、HANDOFF.md（当前状态与阻塞项）
