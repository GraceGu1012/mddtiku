# 小程序「十年真题」模块（2026-11-15）

## 范围与状态

用户要求托管、非托管两个版本均增加「十年真题」。本轮已完成两工程源码和本地验证，未部署后端、未上传微信开发版、未提交审核或正式发布。

- 非托管：`/Users/grace/Project-10/yeahclass-new/miniprogram`，继续使用 HTTPS `wx.request` 和机构账号。
- 托管：`/Users/grace/Project-10/mdd-cloudrun/miniprogram-cloud`，继续使用 `wx.cloud.callContainer`，环境及服务配置未改。
- 两版首页均新增入口，年度列表从接口实时获取并按年份倒序显示；不硬编码年份、套数或题量。
- 列表与详情显示原题数、候选答案数、未解决题数和候选知识卡数，支持加载、空列表、错误和重试。

## 内容边界

现有2017—2026共10套、1650题仍全部待审核。用户本次要求增加客户端模块，不等于授权审批草稿。

学员仅能查看年度目录和整理进度；不返回草稿题面、答案、解析、证据或知识卡内容，不开放整卷作答、评分、错题记录、积分。教研账号（admin/reviewer/teacher）可逐题预览，保留共用题干、选项、原卷页码、候选答案、未解决原因、逐字证据、关联知识点、知识卡和检索候选。附图题明确提示回教研工作台查看原图，本轮未迁移原件或实现小程序附图预览。不是完整知识图谱页面。

托管后端当前没有机构登录及 principal，因此只能进入学员目录/进度模式；不会仅凭客户端字段开放教研草稿。非托管后端沿用现有机构会话和数据库 schema 隔离。没有合并升级托管版既有账号体系。

## 接口

两后端增加 `exam_learning.py` 并在 `app.py` 末尾注册：

- `GET /api/learn/exam-papers`：字段白名单的年度汇总、服务端 `can_preview`。
- `GET /api/learn/exam-papers/{id}`：套卷汇总；仅教研身份返回题号列表。
- `GET /api/learn/exam-papers/{id}/questions/{number}`：服务端再次校验教研身份，未授权403、不存在404；只读。

新页面 `pages/exam-papers/` 与 `pages/exam-paper/` 在两版完全一致。首页仅增加入口，`utils/api.js` 未修改。没有新增依赖、数据库迁移、模型调用或审批动作。

## 验证

- 主工程后端133项通过，含新增目录字段白名单、学员草稿403、匿名401、跨机构404、教研原题保留测试。
- 主工程 `npm test` 87项通过；年度小程序9项在托管工程另跑通过，包括真实网络适配器的请求路径、Cookie与机构/服务头。
- 托管后端新增3项兼容测试通过（旧匿名链路只返回汇总、草稿读取与写入拒绝、空列表/404）。
- 两版首页和新页面的微信原生WXML/WXSS编译通过。未运行微信开发者工具或真机，编译和逻辑测试不替代真机验收。
- 云库只读核对：10套、1650题；mddcloud 对 exam_papers、exam_questions 均有SELECT权限。未改库或部署服务。

命令（主工程根目录）：

```sh
npm test
python3 -m unittest discover -s apps/knowledge-agent/web/tests -p 'test_*.py'
EXAM_MINI_ROOT=/Users/grace/Project-10/mdd-cloudrun/miniprogram-cloud node --test tests/annual-exams-mini.test.cjs
```

托管工程：`python3 -m unittest discover -s backend/web/tests -p 'test_exam_learning.py'`。

## 上线后续

先发布两份后端的 `exam_learning.py` 和路由注册，再上传对应小程序版本，避免新页面调用不存在的接口。两工程使用同一个微信 AppID，上传时需明确通道及版本，不能把两个工程当成两个独立小程序同时发布。云托管本次没有推送Git或触发容器重部署；阿里云本次未重启。发布前再次核对云端基线与运行任务，保留账号、学情和模型配置。
