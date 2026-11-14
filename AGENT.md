# AGENT · mdd-cloudrun

- 角色：为「墨督督学习空间」小程序维护微信云托管后端链路
- 代码源：阿里云 8.130.110.58:/opt/mdd-knowledge/apps/knowledge-agent（SSH BatchMode 可直连）
- 同步方式：服务器代码更新后，用 rsync 重新拉取 backend/（排除 venv/runtime），再重打 deploy zip 上传云托管
- 测试：服务器上有 web/tests/（本仓库构建时排除），改动 app 层逻辑前先在服务器跑 `python -m pytest web/tests` 或对照 yeahclass-new/tests
- 红线：服务器 Postgres 公网配置、密钥文件内容、小程序上传/发布操作，均须用户当次明确授权
