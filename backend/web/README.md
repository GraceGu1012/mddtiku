# 本机知识内容工作台

## 2026-11-13 · 同页材料工作台与多Agent流程

- “材料与解析”和“生成内容”合并为“材料工作台”，旧 #generate / #materials 均进入同页。支持手动批量上传、统一格式预览/确认、课时/范围和生成配置、三阶段执行结果、材料历史分页。仍支持CSV、文字版PDF、DOCX；视频ASR与DOC转换未新增。
- 本地解析适配不同格式并保留出处；确认解析后“开始分析并生成”自动依次执行：解析分析Agent → 关键知识点Agent → 出题Agent（含独立核验调用）。每批预留最多4次调用，沿用选定模型快照，独立保存各阶段结果/时间/错误；不是单纯改三个状态文案。知识点必须带逐字原文引用，生成内容必须关联有效知识点ID。缺知识点时跳过生成并显示0条原因。
- 失败重试新建流程并沿用原模型/提示词，复用成功的分析/知识点，只预留未完成阶段的调用额度（4、3或2次）；失败历史保留，重复点击不会重复入队。原件实际SHA变化/缺失时阻止重试；原失败任务已写出待审结果时禁止直接重跑以防重复收费。
- 新增PostgreSQL agent_prompt_versions / agent_steps；jobs.kind=pipeline，config.pipeline_version=1，冻结三段提示词/模型/材料SHA。分析/提取模板可在同页编辑并查看历史；出题模板继续在设置页管理。旧parse/generate历史如实保留，没有补造Agent日志。
- UI：任务轮询不覆盖配置输入；预览按所选范围最多20片段，加载时禁用范围输入避免异步覆盖；模板、输入、模型输出均转义。审核隔离与AI推理来源标记保留，未审核不展示给学员。
- 测试：60项后端通过；新增12项pipeline测试覆盖完整编排/失效引用/断点重试及幂等/额度/提示词快照/历史分页/材料篡改。13组fake API浏览器检查通过，包含3个视口、上传重复、范围预览、轮询保护、重试确认和版本保存，未使用真实库测试数据。
- 已选择性发布至云端4312；发布前备份runtime/backups/20261113-072343，代码回退/opt/mdd-knowledge/ui-backups/pipeline-20261113-0723。旧材料/题库/审核/模型及凭据/主提示词/学情8类摘要一致，见runtime/validation-pipeline-data-before/after.json。本机和云端均已执行幂等增量初始化，禁止全库覆盖。
- 真实云流程验证job `4800e9f765b5452cabf3302e65bb0ca3`：通过新页面提交2017 PDF第1页、1卡+1单选，顺序调用analysis/knowledge/generation/verification，提取2知识点、生成2条待审内容；所有知识点与结果引文逐字匹配第1页、结果关联有效知识点ID、正式库不可见。累计12276 tokens，价格未配置（未知）。服务重启后整份流程详情完全一致，见runtime/validation-pipeline-live.json；旧失败任务未重跑。
- 材料工作台可直接查看模型、三段提示词版本、调用数、token/成本摘要；未知和部分未知分别显示。桌面/手机从材料历史恢复三阶段结果、知识点原文跳转已实测，见runtime/validation-pipeline-cloud-browser.json。新结果仍需教学人工审核，不宣称AI医学事实合格率。
- 兼容回归：已更新4个原浏览器脚本的旧材料/生成选择器；模型7流程/8布局、UI30布局/3材料列表宽度、3组来源展示通过。browser.cjs已更新并通过语法检查，但本轮未单独运行其旧上传解析worker流程；新统一页面的上传交互由13组fake专项覆盖，既有解析由后端测试覆盖。

### 使用顺序

1. 打开“材料工作台”，上传资料或选择已保存的材料。
2. 同页预览原文，确认解析；字幕需选独立课时。
3. 选择模型、范围、题型和卡片/题目数量，点击“开始分析并生成”。
4. 查看分析、知识点、生成结果；从材料执行历史回看任一批次，完成后到审核工作台人工审核。

Agent模板编辑在材料页展开“Agent提示词”。修改只影响新流程；失败重试继承原快照，如要使用新模板应创建新流程。用户提供内容中的指令不会被当作流程指令。默认AI推理补全只改变答案来源，不能补造十年真题覆盖统计。

新接口：POST /api/pipelines；GET /api/pipelines/{id}；POST /api/pipelines/{id}/retry；GET /api/materials/{id}/history（offset/limit分页）；GET/POST /api/agent-prompts。统一解析仍走原本地文件队列，不引入新的ASR服务或模型供应商。

以下为历史版本记录：

## 2026-11-12 · 无标准答案材料的AI推理补全

- 按用户新要求放宽此前“答案只能来自原文”的业务规则。生成页默认“允许 AI 推理补全”，可切回“仅依据原文答案”；材料缺标准答案可生成候选答案、知识卡及逐选项解析。题干条件不足或无法确定结论时仍减少数量。
- `answer_origin=material/ai_inference`随生成批次/条目保存，原文引文始终逐字核验；AI推理引用只定位题面/知识点，不冒充答案证据。所有推理内容强制逐条人工核验与至少8字说明，不能批量通过；未审核不进入学员库。老师端、学员网页、导出及原生小程序源码均保留来源区分。
- 云端4312已更新，提示词追加v7，保留用户手改v6及所有旧版本；本机数据库追加v6（两端版本号独立）。新任务冻结answer_policy_version=2及answer_mode；旧任务保留旧策略，已有结果不回填来源标记。2017—2026覆盖统计仍由核验数据计算，不由模型补编。
- 验证：48项Web后端、6项旧生成、4项解析、13项小程序测试通过；桌面/手机审核、两种生成方式提交、学员来源标识5组浏览器检查通过（无页面错误、提交拦截）。桌面原CSV路径已不存在，解析回归改用已核对SHA256的存档原件，未改解析程序。
- 云备份：runtime/backups/20261112-225852；代码回退：/opt/mdd-knowledge/ui-backups/inference-20261112-2258。原材料/题库/审核/模型及凭据/学习记录均保留。真实小批验证结果如下，不将生成成功视为医学事实合格率。
- 真实云端小批验证：job `520175340d22485595ee778273128927`，2017 PDF第1页，DeepSeek deepseek-flash，提示词v7，1卡+1单选均成功入待审核，均为ai_inference且suspect=true，正式库不可见，未代替用户通过审核。两次调用usage合计13087（输入4375/输出8712），价格未配置所以cost=null。原文逐字/页码与大纲覆盖未知标记核对通过；这验证生成链路，不代表人工医学事实验收。结果见runtime/validation-answer-inference-live.json。
- 原材料、原题库条目、审核记录、模型配置/加密凭据、答题及卡片进度的发布前后摘要一致，新增仅本次2条待审内容及对应生成/调用/提示词版本，见validation-inference-preserved-data.json。旧失败/零条任务没有重跑。

2026-11-12：审核页右侧编辑区上限760px，左侧列表加宽；提交审核时间为items.created_at首次进入待审核时间（北京时间），非最后修改/退回时间。验证见tests/browser-review-layout.cjs及runtime/validation-review-*.json。

2026-11-12：学员端新增#profile我的页，移动底部固定四项：首页、错题本、知识卡、我的。账号区为当前浏览器档案，统计与学习入口来自现有API。70组布局/8类交互及云端只读检查通过，见tests/browser-mobile-nav.cjs与runtime/validation-mobile-*.json。

云端入口：https://8.130.110.58:4312/ 与 /learn。自签HTTPS，用户已明确要求免登录；运维、限制与备份见[云部署说明](deploy/README.md)。下方本机阶段说明中的“未部署”为历史状态。

## 学员端使用（2026-11-10）

[学员入口](http://127.0.0.1:4312/learn) / [老师入口](http://127.0.0.1:4312/)。教师导航可直接打开学员端。无需另外启动服务或数据库。

1. 老师生成内容后，先在审核台核对答案和出处并通过审核。
2. 学员刷新学习页即可看到新增题目/卡片；按材料、知识点、题型和数量开始练习，题量不足按实际数量出题。优先安排未练习题，不伪造章节或真题归属。
3. 提交后服务端判分，多选需集合完全相等；答案、AI辅助解析、原文引文分开展示。出处在新标签打开，保留当前作答位置。
4. 最近答错的同版本题进入错题本；新一组重练答对后自动移出。知识卡先翻面再自评，自评和测验成绩分开记录。
5. 学习记录可继续未完成的练习；题目撤回/修改后旧版本停止使用，历史提交和累计统计保留。未审核/打回/归档内容不展示。

learner.py新增学员API；static/learner.html、learner.css、learner.js构成界面。PostgreSQL新增learners（随机Cookie摘要）、practice_sessions（题目ID/版本顺序）、practice_attempts（提交/服务端判分/答案快照）、card_progress（每卡最近自评）。重复提交相同答案不重复计数；不同答案需新练习。今日统计按Asia/Shanghai。

同一浏览器保留档案；HTTPOnly/SameSite Cookie有效期一年，清除Cookie或换浏览器会新建档案；数据库旧记录仍在。当前没有找回/跨设备账号、班级权限、收费会员或微信登录，不能直接开放公网。学习页面不调用模型，不产生额外生成费用。

## 当前 UI 与生成质量

工作台与学员端沿用用户8897/UI规范：主色#1d6fd1、背景#f5f7fb，桌面168px侧栏/64px顶栏/32px控件、手机44px点击区域。工作台设置分模型/额度/提示词页签；学员端窄屏为底部导航。来源与列表保持清晰、少文字，全部图标SVG。

当前提示词（云v7、本机v6）保留出处逐字引用与统计证据约束，使用learning_design：大纲节点、已核验真题ID、考查目标、易错依据和逐项解析。learning_quality.py校验并计算覆盖，模型不能自填次数/年份；真题按试卷/年份/题号去重。缺大纲和完整2017—2026对照时均显示“待核验”，不是0或“未考过”。目前pending_exam_context是空核验上下文，真实题目—大纲映射库/导入UI尚未开发。默认allow_inference模式下，材料只有题干/选项时可用学科知识推导答案，标记AI推理并逐条人工核验；source_only模式仍在缺答案依据时返回不足。两种模式都禁止用考试说明、题量、页码凑专业知识内容。

历次v4/v5/v6/v7均作为追加版本保存，不覆盖之前提示词；任务冻结所用版本。已有结果不被新提示词追溯改写。真实旧批次主要是试卷结构题，保留待用户审核；本次没有主动发起付费模型生成。

## 本轮专项验证

- 学员新增7组后端测试：审核可见性/答案隔离、幂等与错题重练、浏览器档案隔离、撤回/版本、单多选与判断判分、知识卡自评/出处、筛选和CSRF；总计40项Web测试通过。
- tests/browser-learner.cjs在独立测试库走双端审核发布、作答、引用上下文、刷新、错题清除、卡片自评、档案隔离、撤回、多选/判断交互；1440/1024/768/390/320宽度7种页面共35组布局，无页面错误。
- runtime/validation-learner-browser.json、validation-learner-live.json记录交互与真实库只读检查；learner-live-home-1440.png和learner-live-home-390.png为实际页面预览。真实库5题+5卡，不在真实库写测试作答。
- 测试服务实际重启后，同一浏览器Cookie恢复学习记录、结果、自评与正确续练位置，见validation-learner-restart.json；测试库pg_dump恢复到knowledge_agent_learner_restore_20261110_092255，四张学习表逐行摘要一致，见validation-learner-backup.json。
- 原有10张内容/配置/任务表的摘要重启前后相同，见validation-learner-existing-data.json。新增学习记录随完整pg_dump一起备份，不需要额外导出。学员身份Cookie应由浏览器保留，丢失Cookie不会删除数据库数据。
- HZ规范验证36组布局、模型设置7流程8组布局已通过，详见validation-hz-ui.json和validation-models-browser.json。

入口：http://127.0.0.1:4312/ 。这是连接 PostgreSQL 的本机内部工具，已具备真实的审核入库能力。不是完整生产版；2026-11-12已增加云端部署（用户后续要求免登录），见deploy/README.md。

## 当前实现

- 已导入4份材料和当前对话生成的5卡+5题；导入幂等，重启不覆盖编辑、审核或提示词历史。当前初始10条已由用户审核（5卡+5题），另有10条旧提示词真实生成结果待审核。
- CSV、文字版PDF、DOCX批量上传，单文件500MB上限，显示上传进度、重复文件识别。原件保存在runtime/materials，数据库保存关联路径和哈希。
- 单worker持久化任务队列，显示位置与失败原因；预览确认后才能生成。字幕按课时/序号/时间、PDF按页、DOCX按章节/正文或表格顺序定位。
- 审核台编辑题干、答案、选项、解释、难度、标签；AI原版不变，操作前后版本及原因留痕。通过、打回、退回待审核、二次确认归档。未审核不进入正式库；已通过内容编辑后自动撤出正式库。
- 批量审核为事务：任一版本过期或存疑，整批取消。存疑和人工编辑后的内容只能逐条复核，并填写依据说明。引文和原件哈希不符时程序拒绝通过。
- 卡片库、题目库分开，支持搜索题干/标签与题型筛选。CSV/Excel导出仅包含已通过内容，保留长文本与换行并阻止公式执行。Excel单格超过32767字符时拒绝并提示改用CSV。
- 提示词保存为新版本；多个模型的名称、供应商、Base URL、模型ID、Key、JSON Mode、启停和单价可配置，每日总调用上限可修改；任务保存提交时的完整配置和提示词快照。
- 多模型兼容接口已实现，生成页选择本次模型；缺Key、停用、过期配置或额度不足会明确阻止。每批最多20条、输入最多3万字，生成＋语义核验最多2次调用。原始usage保留；无法取得usage/价格时保持未知。

## 架构和技术栈

Python 3.9、FastAPI 0.115.6、Uvicorn 0.34.0；PostgreSQL 16.14，psycopg2；PyMuPDF、python-docx；HTML、独立CSS/原生JS，无前端构建依赖。实际依赖版本见requirements.txt。

`app.py`提供API与页面；`processing.py`负责解析、单worker队列、模型调用和引文检查；`bootstrap.py`建立表并幂等导入样本；`schema.sql`是PostgreSQL初始化脚本。

数据表：materials原始材料和解析结果；prompt_versions不可变提示词；settings全局额度；model_profiles模型配置；model_credentials加密凭据历史；batches生成批次；items原版/当前版/来源/审核状态；audit操作历史；jobs队列；calls原始usage。正式库由`approved_library`视图限定。不存在SQLite或浏览器本地存储替代数据库的情况。

## 启动、停止、配置Key

在项目根目录执行（这台机器已安装所需依赖并建好数据库）：

```sh
apps/knowledge-agent/web/run.sh
```

服务只监听127.0.0.1:4312，单进程单worker。停止时在启动终端按Ctrl+C。再次运行同一脚本恢复，不清空数据。数据库默认`dbname=knowledge_agent host=/tmp`，可通过服务端`KNOWLEDGE_DATABASE_URL`覆盖。初始化不会创建数据库本身；换机器先安装PostgreSQL、用`createdb knowledge_agent`建独立库，再安装requirements.txt。

在“模型与提示词”点击“添加模型”，填写显示名称、供应商、Base URL、API模型ID和Key。支持DeepSeek、通义千问、智谱GLM、Kimi及自定义Chat Completions兼容接口。供应商预设只填接口地址，不虚构账户可用的模型ID。模型名和API模型ID可不同，例如“日常出题”与供应商实际模型ID。

Key输入框固定为密码框；保存后清空，不提供明文查看或读取接口。编辑时Key留空保留原值，填写新Key则创建加密凭据新版本。凭据使用Fernet认证加密保存在PostgreSQL，主密钥默认单独存runtime/master.key（权限600，runtime目录700，已被.gitignore排除），也可由服务端环境变量KNOWLEDGE_ENCRYPTION_KEY提供。主密钥不能丢失或随意替换，丢失时程序拒绝创建替代密钥并要求恢复备份。旧环境变量DEEPSEEK_API_KEY仍仅兼容旧版默认DeepSeek配置/旧任务。

用户2026-11-10提供的DeepSeek Key已加密保存；官方/models只读检查返回200，当前模型在返回列表中。此检查不是生成调用，不代表卡片生成质量、usage或付费流程已实测。

生成页选择模型后，任务冻结模型ID、供应商、Base URL、配置版本、价格、提示词和凭据版本引用；不存Key明文或密文到任务JSON。换Key或改模型不改变已排队任务。停用模型阻止新任务，不取消已排队任务。更改接口地址须重新输入该接口Key，避免将旧Key发送到不同服务。

支持公网HTTPS Base URL，调用/chat/completions，拒绝查询参数、内网/本地地址及重定向，不读取系统代理。每次调用前解析域名并排除非公网地址。仅支持此兼容协议，不等同支持所有供应商的原生接口、Responses或Anthropic协议。JSON Mode可按模型关闭；模型仍须返回规定JSON，程序不会静默补齐无依据的答案。

模型支持独立单价，全局设置所有模型合计的每日调用上限。默认`deepseek-flash`、每日上限0（暂停）。正式发起前由用户设置额度；每批预留2次调用，保守计入当天额度，失败也不自动释放，避免不明计费时重复调用。日期按Asia/Shanghai计算。单价为每百万token，暂不计缓存折扣，估价不是账单。保存提示词立即作用于下一个新提交任务，已排队任务保持原快照。

DeepSeek接口基于[官方调用文档](https://api-docs.deepseek.com/quick_start/pricing)及[Chat Completions文档](https://api-docs.deepseek.com/api/create-chat-completion/)，2026-11-09核对。另于2026-11-10核对[通义Base URL](https://help.aliyun.com/zh/model-studio/base-url)、[智谱兼容接口](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)和[Kimi官方调用方式](https://platform.kimi.com/docs/get-api-key)。调用保存的公网HTTPS端点，禁止重定向；模型别名和价格可能变化，实际接入时再次核对。

## 验证结果与复现

- 当前40项Web后端测试＋6项生成证据测试＋4项解析测试通过，共50项。新增密钥加密/不回显、留空保留/替换版本、地址变更保护、模型选择与快照、跨模型额度、停用/冲突、解密主密钥丢失及接口校验。覆盖审核隔离、编辑撤回、并发版本冲突、批量回滚、存疑拦截、删除确认、伪造引文拒绝、提示词/配置快照、额度、usage原样记录、导出换行和公式、文件去重、DOCX正文表格顺序。
- 独立测试库实际浏览器走通10组流程；7个页面在1440/768/390/320px的28次布局检查通过，无运行时错误。见runtime/validation-browser.json。
- 真实服务重启后，材料、批次、条目、审核记录、提示词、配置六表逐行摘要一致。见runtime/validation-restart.json。
- 真实数据库备份恢复到`knowledge_agent_restore_20261109`，六表逐行摘要及4个原件哈希一致。见runtime/validation-backup.json。未重启共享PostgreSQL实例。
- 多模型浏览器验证7组流程、设置与生成页四宽度共8次布局通过；API响应未泄露测试Key，见validation-models-browser.json。加密凭据备份恢复与解密检查见validation-models-storage.json。
- 测试数据库`knowledge_agent_test`、材料目录`runtime/test_materials`、主密钥runtime/test-master.key独立。测试会重置测试库，不能指向真实库；运行单元测试时先停止4313测试服务，避免并行修改测试库。

```sh
# 第一次才需要创建测试库
createdb knowledge_agent_test
python3 -B -m unittest discover -s apps/knowledge-agent/web/tests -v
python3 -B -m unittest discover -s apps/knowledge-agent/generation/tests -v
python3 -B -m unittest discover -s apps/knowledge-agent/intake/tests -v
```

浏览器维护测试`tests/browser.cjs`需要Playwright和本机Chrome，固定访问4313。先初始化干净测试库、用KNOWLEDGE_DATABASE_URL指定测试库、KNOWLEDGE_STORAGE_DIR指定绝对测试材料路径、KNOWLEDGE_PORT=4313启动服务；再执行测试脚本。不要把该脚本的地址改成真实4312，因为它会在测试库中执行通过/编辑等操作。

## 备份与恢复

执行`apps/knowledge-agent/web/backup.sh`，在runtime/backups/时间戳目录生成`database.dump`、`materials.tar.gz`、SHA256SUMS。备份包含数据库（包括加密后的模型Key）和原始文件，不包含加密主密钥或环境变量Key。必须单独安全备份runtime/master.key或KNOWLEDGE_ENCRYPTION_KEY，恢复时配回原主密钥；不要把主密钥公开或提交仓库。新增模型凭据已在knowledge_agent_models_restore_20261110验证与原库一致，使用原主密钥解密一致。采用PostgreSQL官方[pg_dump自定义归档与恢复方式](https://www.postgresql.org/docs/16/app-pgdump.html)。原件目前只追加不覆盖，数据库先备份、原件后打包，可对应数据库快照；归档可能多包含稍后上传的文件。

恢复先建一个新的空数据库，执行`pg_restore --no-owner --exit-on-error --dbname=新库 database.dump`，对照哈希并恢复原件。不要覆盖现有库，不使用`--clean`，不要删除用户数据。跨机器恢复须将materials.path映射到新原件目录，核对4份或更多全部原件哈希后才切换KNOWLEDGE_DATABASE_URL。实际恢复验证已在独立库完成。

## 明确未完成 / 能力边界

- DeepSeek Key已配置；用户已发起2次真实生成任务（1完成、1输出截断失败），保留3条原始usage调用记录。已完成批次主要是试卷结构题，尚未进行20条专业知识质量评测/供应商账单对账。v5新增专业内容限制后尚未再次做付费生成验证。
- 视频ASR、关键帧、DOC转换、扫描PDF OCR未接入；DOCX仅合成文件测过，尚无用户真实Word样本。Word图片、文本框、复杂公式不提取；PDF题号识别不等于完整结构化真题导入。
- 三份PDF缺明确答案来源；字幕暂不关联试卷。自动生成可以报告材料不足或失败，不能补答案。医学内容未回听原音视频或由专家独立确认。
- 仅本机内部使用；学习档案以浏览器Cookie区分。Host/Origin/CSRF和学员档案隔离不替代生产身份/角色权限，管理API仍是本机工具；没有对外注册、机构隔离或云部署。用户指定云主机8.130.110.58，本次只读访问其参考原型与UI规范，未部署。
- 上传上限500MB已实现，但500MB压力与内存峰值未实测。解析会读文件/全文结构，占用可显著高于文件大小；建议先拆分大文件。一次一个解析或生成任务；没有承诺处理时长。视频转录资源要求需选择ASR后评估。
- 尚无条目级重新生成、全局标签合并管理、按材料类型拆分提示词管理、解析模型提示词。题型可选，但复杂难度分布、全量自动分段生成未做。
- 页面按题型/关键词筛选；后端支持材料/难度筛选但界面尚未展示。审核统计为操作次数，不是假设的首次审核质量通过率；三份各20条评测基线未完成。
- 任务中断后标失败，不自动重试付费调用；可能发生“供应商已计费但未返回usage”，需人工核对账单。模型调用结果先保存待审核，再标完成；单worker运行，不允许多进程部署。
- “删除”仅归档、隐藏，原件和审核历史保留；没有批量清空或物理删除接口。后续不可逆清理需另行确认。

排错先查看页面失败原因、任务提交时的提示词与模型快照、API HTTP状态和usage；保留原件、数据库和版本历史，不重新建库掩盖问题。
