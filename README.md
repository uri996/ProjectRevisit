# ProjectRevisit v0.1

ProjectRevisit 是一款本地项目知识检索与面试复习助手。使用 Vue 3、TypeScript、Vite、FastAPI、Python Services、LangChain、Chroma、SQLite 和阿里云百炼。所有日常操作均有中文界面；不需要 Docker、账号或云服务器。旧 Streamlit 界面仅保留为回退入口。

## Windows 10 安装与启动

建议使用 **64 位 Python 3.12** 和 **Node.js 24 LTS（24.12+）**。32 位 Python 不适合 Chroma 的二进制依赖。Node/npm 仅用于首次安装、开发和重新构建，日常启动只需 Python 与已构建的前端。

安装依赖后，可双击 `start.bat`，或者在项目目录执行：

```powershell
.\.venv\Scripts\python.exe scripts/launch_windows.py
```

全新机器首次安装：先安装 Python 3.12 x64，然后在项目目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe scripts/launch_windows.py
```

`requirements-lock.txt` 固定 Windows/Python 3.12 使用的依赖版本。可省略锁文件安装这一步，直接安装项目声明的兼容版本范围，但这样解析到的依赖可能不同。

浏览器访问 **http://127.0.0.1:8765**。以后双击 `start.bat` 即可启动；一个 Python 进程同时提供 API 和 Vue 生产资源，并在健康检查成功后打开浏览器。窗口保留错误，缺少前端构建时会提示构建命令。停止时按 **Ctrl+C**，无需管理额外的 Vite 进程。`--no-browser` 可禁用自动打开，`--port` 可更换本机端口。

开发时分别运行 `.\.venv\Scripts\python.exe scripts/launch_windows.py --api-only --no-browser` 和 `cd frontend; npm run dev`，访问 `http://127.0.0.1:5173`。Vite 仅监听本机并代理 `/api` 至 8765。旧版回退命令：`.\.venv\Scripts\python.exe scripts/launch_streamlit.py`，访问 8501；两个入口使用相同数据空间，请避免同时对同一项目执行付费操作。

## 首次使用

1. 左侧创建“示例项目 A”和“示例项目 B”。这些名称完全虚构，应用也支持用户自行创建任意项目名称，底层 UUID 始终独立。
2. 进入“AI 设置”，核对服务商、实际 HTTPS Base URL、地域与模型。默认使用北京传统接口和 `qwen3.7-flash` / `qwen3.7-text-embedding-flash` / 1024 维。新业务空间请复制百炼控制台的实际地域接口地址。
3. 在密码框输入 API Key，勾选目标地址确认后保存。Key 由 Windows Credential Manager（keyring）保存；更改 Base URL 后需要为新地址提供对应 Key。
4. 如需验证，勾选连接测试费用提示，再点击“测试已保存配置的 API 连接”。只发送合成文本，各调用一次 Embedding 与 LLM；可能产生费用。
5. 选择项目，在“知识库管理”中批量选择 UTF-8 `.md` / `.txt`，点击“保存上传文件”。上传仅保存在本机，此时不会发送 Embedding 请求。
6. 选择要索引的文件，核对外部目标地址与模型，勾选发送文本确认，再点击“建立索引 / 重新索引”。只有此时发送文档分块。
7. 进入“智能问答”输入问题。消息时间按浏览器本地时区显示。展开来源证据可查看文件名、章节和原文，继续展开“完整 Chunk ID”可查看标识。切换项目后只显示对应项目的对话，旧请求完成后只更新原项目。
8. 同名文件的内容变化会更新该文档并标记“需要重新索引”；相同字节内容在同项目内去重。未重新索引的更新文件不会参与检索。
9. 更换 LLM 不影响索引。更改 Embedding、维度、地址或分块配置后会要求手动重新索引，不会自动发送资料或删除旧向量。

`examples/demo_project_alpha.md` 是虚构的图书目录管理工具资料，`examples/demo_project_beta.md` 是虚构的个人任务清单工具资料。两份资料的名称、背景、实现记录与问答均独立编写，不对应真实个人经历，可分别导入两个示例项目。没有 API Key 时仍可创建项目、保存文件、浏览历史。配置可用 Key 后，即使没有兼容索引或检索无命中，明确提问仍会调用 LLM 提供标注为通用知识的帮助，可能产生费用；没有项目证据时不生成项目事实或基于资料的推断，也不会自动建立索引。

## 推荐问题

在“智能问答”右侧推荐面板选择“项目复盘”或“面试准备”。默认显示三道基础问题，可展开全部；浏览基础推荐不需要 API Key，也不调用 API。消息与推荐分别滚动，输入框固定在聊天区底部。窄屏使用可关闭的推荐抽屉，移动端导航也可收起。

展开“根据简历生成”，填写简短项目介绍和目标岗位（例如示例项目 A 的虚构图书目录工具、后端开发），勾选发送与费用确认，再点击“生成 / 重新生成问题”。应用复用 AI 设置中当前的 Qwen 模型、目标地址与系统安全凭据，仅发送这两项输入，不读取知识库或聊天，不生成答案，也不声明真实面试命中率。返回 5–10 道结构化问题，每道包含考察方向和简短理由；格式错误或请求失败不会覆盖上次成功结果，可手动重试。

在右侧“个性化推荐”中查看已保存结果。每个项目最近一次成功生成的问题、对应描述及目标岗位保存在现有私人数据目录的 SQLite 中，重新进入项目后恢复；浏览、刷新或切换页面不会重新生成。重新生成仅更新当前项目的推荐，不覆盖聊天或索引。本次界面迁移不增加或修改 SQLite 表结构。

**点击任意推荐问题会直接使用当前项目的正常 RAG 问答，可能产生问答费用**：问题与回答进入原聊天记录，来源证据照常展示，可继续自由追问。回答按需区分项目事实、基于资料的分析建议、AI 通用知识与待核实事实，不必每次列出所有类别。事实与分析分别标明来源编号，引用原文需能在对应检索片段中核对；通用知识不伪造项目引用。实际困难、职责、成果或历史动机未记载时仍不能编造，但可提供明确标注的核查方向、技术分析和改进建议。旧资料的版本范围不会自动等同于当前代码实现，应用不会读取仓库补全事实。没有可用 API Key 或推荐生成失败时，基础推荐仍可浏览。

## 模型与地域

依据 2026-10-27 查阅的官方资料：

- [Qwen3.7 Flash 模型信息](https://help.aliyun.com/zh/model-studio/qwen3-7-flash)：模型 ID 有效，文档列出北京、新加坡等区域。实际权限与业务空间以控制台为准。
- [Flash Embedding 模型信息](https://help.aliyun.com/en/model-studio/qwen3-7-text-embedding-flash)：支持 256、512、768、1024 维，默认 1024；该页面列出北京服务信息。
- [Embedding 地域与调用说明](https://www.alibabacloud.com/help/en/model-studio/embedding)：新加坡列表包含 `qwen3.7-text-embedding` 与 `text-embedding-v4`，未列出 Flash Embedding。选择新加坡 Flash 配置时应用明确提示，不会静默换模型。请自行确认并填写当地可用模型。
- [中文 Embedding 指南](https://help.aliyun.com/zh/model-studio/embedding) 展示业务空间域名形式：`https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` 或 `https://<WorkspaceId>.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`。占位符必须替换为控制台实际值。
- 也提供传统北京 `https://dashscope.aliyuncs.com/compatible-mode/v1` 与新加坡 `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` 地址输入示例；是否适用于你的业务空间需以控制台为准。
- 集成使用 [LangChain 官方 Chroma 适配器](https://docs.langchain.com/oss/python/integrations/vectorstores/chroma)，未使用旧版 community Chroma 接口。百炼请求通过 OpenAI 兼容 SDK 发送原始字符串和 `dimensions`，不使用 OpenAI tokenizer 重新编码文本。

模型可用性会变化，应用不尝试无提示的模型回退。连接失败应检查地域、模型授权、维度、Key 和额度；错误不会输出服务端原始响应。

## 数据与隐私

产品正式名称为 **ProjectRevisit**；为兼容已有数据，内部存储目录、环境变量和系统凭据服务标识保留原名称。

Windows 默认私人数据目录：

```text
%LOCALAPPDATA%\ProjectRAGAssistant\
  originals/<project UUID>/<document UUID>/<revision>.utf8
  metadata.sqlite3
  chroma/
  settings.json
  locks/
```

侧栏不展示数据路径。如需本机排查，请在“AI 设置 → 高级选项”主动点击“主动查看完整数据路径”。原始上传字节、元数据、聊天、推荐和引用都在上述数据目录中；仓库中只保留源码、测试和人工示例。Windows Keyring 服务标识仍是 `ProjectRAGAssistant.v0.1`。

当前项目 UUID 保存在标签页的 sessionStorage，导航和刷新时恢复；没有已保存选择的新会话默认选择首个项目。提问草稿和编辑中的表单仅保留在页面内存，刷新不保存。浏览器存储不保存资料、简历、聊天或 API Key。密钥输入仅临时用于提交本机后端，提交后清空；已保存密钥永不返回浏览器。

可在启动前设置 `PROJECT_RAG_DATA_DIR` 指定其他仓库外目录；这会打开一个独立的数据空间，**不会自动迁移原数据**。指向本仓库内部会明确拒绝启动。API Key 不在该目录，而由操作系统安全凭据保存。安全凭据不可用时明确报错，不会降级保存到 JSON、SQLite 或 `.env`。

本地保存、GitHub 上传与第三方 API 请求是三件事。本应用不连接 GitHub。建立索引时会向配置的 API 发送分块；聊天时会发送问题、受限历史与本次证据。Chroma 与 Streamlit 使用统计已关闭，HTTP 请求不跟随重定向。不要在系统上开启 SDK 调试日志来处理私人资料。

FastAPI 默认只监听 127.0.0.1，限制 Host 为 127.0.0.1 / localhost；写接口要求来自当前本机应用端口或 Vite 5173 的 Origin，不允许任意跨域来源。前端不直接连接 Qwen、Chroma 或 SQLite。校验错误不回显输入，日志不输出 API Key、私人路径或资料。

`.gitignore` 排除虚拟环境、工具缓存、数据库、Chroma、上传、日志、私人配置及默认的 Markdown/TXT；Markdown 文档仅放行根目录 README 和两个指定的虚构示例。Agent 指导文件和开发记录整目录仅保留在本地，不纳入版本控制；无秘密的依赖锁文件可以提交。**不要把私人资料放进公开源码或示例中**。使用 Git 时，提交前执行：

```powershell
git status --short --ignored
git ls-files
git diff --cached --name-only
```

只允许跟踪源码、安全模板、公开文档与合成示例，不能用 `.gitignore` 代替人工审查。已跟踪的敏感文件不会因追加 ignore 规则而自动停止跟踪。

## 架构

```text
frontend/src/ -> HTTP /api -> backend/api/ -> backend/services/
                                               -> backend/rag/ + backend/storage/
                                               -> SQLite / 文件 / Chroma / 百炼
```

- `frontend/src/api.ts` 封装请求；`store.ts` 按项目维护临时状态；Vue Router 提供概况、知识库、问答和设置页面。
- `backend/api/` 定义 Pydantic 契约、路由、本机访问边界和请求互斥；`services/application.py` 组装原有 Service，API 不重写业务。
- `project_service.py` 创建 UUID 项目；`document_service.py` 验证上传、去重、处理索引状态和版本切换。
- `rag/loader.py` 正常化 UTF-8 和换行，`chunker.py` 保留 Markdown 标题路径，`provider.py` 是可替换的 Embedding/LLM 边界。
- `storage/vector_store.py` 使用独立的“项目 + 文档索引代次”Collection，比单项目 Collection 更细。完整写入后 SQLite 才切换活动指针。失败保留原文件与旧代次，失败文档不参与问答。显式重新索引成功后只清理该文档旧向量。
- `qa_service.py` 限定项目与兼容签名，先向量化受限检索问题，再召回 Top-K，交给 `generator.py` 组装证据约束 Prompt。历史 AI 回答只帮助理解指代，不被向量化为知识来源。
- `storage/database.py` 保存项目、文档、消息、规范 UTC 时间与引用快照。每项目一条对话，按 SQLite 自增序号稳定排序。引用不依赖当前原文件版本，因此重启后仍可展示原回答依据。
- 设置中保留当前模型信息，每个文档保存建立索引时的完整非秘密配置与签名。不同模型、维度或地址的向量不会混用。切换配置不会自动删除旧索引。
- 文件锁防止同项目的上传、索引、问答与清空交错。中断后残留“处理中”在获取锁确认无活动任务时转为失败，允许手动重试。
- 旧 `ui/` 仅作为 Streamlit 回退，不是新界面的依赖。后端不导入 Streamlit。

## 本机 API

| 接口 | 用途 |
| --- | --- |
| `GET /api/health` | 启动健康检查 |
| `GET /api/projects`、`POST /api/projects` | 项目列表与创建；项目选择由前端保留 UUID |
| `GET /api/projects/{id}/documents`、`POST /api/projects/{id}/documents` | 文档状态与 multipart 文件上传 |
| `POST /api/projects/{id}/documents/{document_id}/index` | 手动确认索引 |
| `GET /api/projects/{id}/messages`、`DELETE /api/projects/{id}/messages` | 读取或二次确认清空聊天 |
| `POST /api/projects/{id}/questions` | 原 QAService 问答与引用 |
| `GET /api/recommendations/presets` | 免费预设 |
| `GET /api/projects/{id}/recommendations`、`POST /api/projects/{id}/recommendations` | 恢复或生成问题 |
| `GET /api/settings`、`PUT /api/settings` | 非秘密配置、密钥状态和安全更新 |
| `POST /api/settings/test` | 明确确认的合成连接测试 |
| `GET /api/settings/data-location` | 主动查看数据位置 |

索引、问答、推荐生成、清空聊天和连接测试提交独立的 UUID `request_id` 及 `confirmed`。重复请求 ID 返回 409；同项目长操作互斥，Service 仍保留跨进程文件锁。请求不会自动重试，重复 ID 的防护保留在当前服务进程中至多 24 小时；服务重启或网络中断后请先刷新历史、文档状态，再决定是否手动重试。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check backend ui tests scripts
.\.venv\Scripts\python.exe -m compileall -q backend ui scripts
.\.venv\Scripts\python.exe scripts/smoke_runtime.py
cd frontend
npm run typecheck
npm test
npm run build
npm run test:e2e
```

后端测试使用临时目录、Fake Embedding/Fake LLM、HTTP MockTransport 和实际 SQLite/Chroma。禁止外网，仅允许回环连接。前端包含 Vitest 交互测试和 Playwright 实际 Chrome 端到端测试；后者使用独立的临时后端、Mock Qwen，测试辅助接口仅存在于测试服务器。需要已安装 Google Chrome；截图与测试产物被 Git 忽略。运行启动检查前先完成前端构建。无需真实密钥，不产生真实百炼费用。

## 当前限制

- 只支持 UTF-8 Markdown/TXT、每份最多 10 MB；同名更新按文件处理。保留上传历史版本，以保护原始资料，当前没有批量清理界面。
- 按文档 Collection 检索适合个人小型资料库；文件数量很大时有额外查询开销。
- 当前校验能保证引用 ID 来自本次检索，并区分事实来源和分析依据。模型使用本次请求内的短来源编号，程序映射回真实 Chunk ID；来源原文直接从检索片段展示，模型无需复写引文。如果模型另外提供引文，仍须通过原文匹配检查。不能数学证明每条自然语言结论被原文蕴含或推理正确，仍应人工核对。旧聊天与旧格式回答继续兼容，不重写记录。未实现 reranking 或复杂评估。
- 问答失败时，安全错误码区分请求失败（`LLM_REQUEST`）、JSON 无法解析（`LLM_JSON`）、输出截断（`LLM_TRUNCATED`）、未知来源（`QA_SOURCE_UNKNOWN`）、引文不匹配（`QA_QUOTE`）等阶段，不包含模型回答、资料或密钥。可提供错误码排查；应用不会自动重试模型请求或产生额外修复调用。
- 默认调用超时 45 秒，不自动重试付费请求；长文档可能需要等待多批请求。若中断，手动重新索引。
- 为保守满足模型请求限制，单个 Embedding 文本不能超过 8000 UTF-8 字节，批次最多 10 条且合计不超过 8000 字节；默认 Chunk Size 1000 适用。更大的中文分块可能提示降低大小。
- 首次使用时需配置自己的 Key，并明确触发合成连接测试，以确认目标地域、模型权限和凭据可用性。
- 当前回答为非流式：提交后立即显示问题和处理中状态，完成后一次展示回答与引用。请求不会因页面切换而自动取消或重发；响应只更新发起请求的项目。
