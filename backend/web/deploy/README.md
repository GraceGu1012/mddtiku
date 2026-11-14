# 4312 云部署 · 2026-11-12

2026-11-13 收尾备份：runtime/backups/20261113-073142，dump目录检查包含agent_steps与agent_prompt_versions表数据；本轮验证流程在服务重启后完整保留。发布10个运行文件与本机SHA一致。

2026-11-13 多Agent材料工作台：增量表agent_steps/agent_prompt_versions；bootstrap创建两个Agent默认模板，仅首次插入，主生成模板历史不变。新/static/pipeline.js需与index.html/app.py一起发布。云备份20261113-072343，代码回退ui-backups/pipeline-20261113-0723。回退旧worker前必须核对kind=pipeline队列，不能把新流水线任务交给不认识该kind的旧worker；保留数据库新增表与用户数据。

2026-11-12 23:00 答案策略更新：默认允许AI推理补全，云提示词追加v7，保留v6和旧历史；新任务answer_policy_version=2，旧任务仍用快照。备份runtime/backups/20261112-225852，代码回退ui-backups/inference-20261112-2258；回退时不要删除新待审内容，需将兼容的旧提示词另存新版并保留来源标记。发布后旧数据摘要一致，新建真实验证任务520175340d22485595ee778273128927生成1卡+1单选，均待审核。不要以回滚为由恢复整库覆盖用户新数据。

- 工作台：https://8.130.110.58:4312/；学员：https://8.130.110.58:4312/learn。
- Nginx 4312 HTTPS（用户明确要求免登录），转发到127.0.0.1:14312；应用不直接监听公网。HTTP同端口跳转HTTPS。
- 目前使用IP自签证书，有效期365天，首次访问浏览器会提示。后续有域名可替换正式证书。TLS私钥在服务器/etc/mdd-knowledge/tls.key，不进入源码。
- 2026-11-12按用户明确要求取消访问口令，无需登录；老师与学员入口均公开，尚无角色分权。此前访问凭据文件仅作历史保留，Nginx不再使用。

## 路径及运行

- 源码/虚拟环境：/opt/mdd-knowledge；运行用户mddknowledge。
- PostgreSQL数据库mdd_knowledge，UTF-8；本机Unix socket peer认证，无需数据库密码。迁移前本机PG16、云PG15，使用plain SQL迁移，14表标准化摘要一致，4文件哈希一致。
- 资料：/opt/mdd-knowledge/apps/knowledge-agent/runtime/materials。
- 配置：/etc/mdd-knowledge/service.env；加密主密钥master.key为mddknowledge所有、600权限，与数据库备份分开保管。
- systemd：mdd-knowledge.service，已开机启动、故障自动重启，单进程单队列worker。
- Nginx：/etc/nginx/conf.d/mdd-knowledge-4312.conf；只增本项目配置，无其他服务变更。

服务器运维命令：

```sh
systemctl status mdd-knowledge
journalctl -u mdd-knowledge -n 100 --no-pager
systemctl restart mdd-knowledge
systemctl stop mdd-knowledge
```

改服务配置重启前检查排队/执行中任务，避免中断收费生成。无需重建数据库。

## 备份与恢复

```sh
runuser -u mddknowledge -- env KNOWLEDGE_DATABASE_URL="dbname=mdd_knowledge host=/var/run/postgresql user=mddknowledge" sh /opt/mdd-knowledge/apps/knowledge-agent/web/backup.sh
```

备份在云端runtime/backups，含PostgreSQL custom dump和材料，不含master.key；主密钥另行安全保管。恢复始终用新的UTF-8数据库验证，不覆盖原库。使用模板template0显式创建UTF8，服务器默认模板是SQL_ASCII，不能直接照默认createdb建中文库。首次错误编码的导入副本保留为mdd_knowledge_import_ascii，应用不连接该库。

install-cloud.sh是首次部署脚本，目标库存在即拒绝，不可当更新脚本反复运行。更新代码先备份，复制明确变更文件、运行测试、重启并检查；已有资料/题库/模型配置均保留。

如需撤回本次发布，停止mdd-knowledge，将本项目Nginx配置移出conf.d后nginx -t再reload；保留数据库、材料和密钥，不做删除。

## 数据及验证

迁移快照：4材料、20条内容（10已审核/10待审）、5提示词版本、1模型配置/凭据、2生成任务、3调用日志。原有学习记录也迁移，但本机Cookie不会跨IP自动登录原档案。云端和本机之后独立写入，不自动同步。

42项Web测试通过，含云Origin允许/外站拒绝、HTTPS Cookie。初次部署验证未授权401、授权200；随后取消口令，不带凭据页面/API均200，浏览器验证工作台、学员知识卡/出处、手机布局和安全Cookie；仅提交被拒绝的过期配置测试，不修改题库或调用模型。证据位于本机runtime/cloud-release/validation-*.json。
