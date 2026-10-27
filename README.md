# ProjectRevisit v0.1

ProjectRevisit 是一款本地项目知识检索与面试复习助手。使用 Streamlit、Python Services、LangChain、Chroma、SQLite 和阿里云百炼。所有日常操作均有中文图形界面入口；不需要 Docker 或云服务器。

## Windows 10 安装与启动

建议使用 **64 位 Python 3.12**。32 位 Python 不适合 Chroma 的二进制依赖。

安装依赖后，可双击 `start.bat`，或者在项目目录执行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run ui/app.py
```

全新机器首次安装：先安装 Python 3.12 x64，然后在项目目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m streamlit run ui/app.py
```

`requirements-lock.txt` 固定 Windows/Python 3.12 使用的依赖版本。可省略锁文件安装这一步，直接安装项目声明的兼容版本范围，但这样解析到的依赖可能不同。

浏览器访问 **http://127.0.0.1:8501**。以后双击 `start.bat` 即可启动。停止时在启动窗口按 **Ctrl+C**。服务仅监听本机回环地址，请勿将其暴露到公网。

## 首次使用

1. 左侧创建“示例项目 A”和“示例项目 B”。这些名称完全虚构，应用也支持用户自行创建任意项目名称，底层 UUID 始终独立。
2. 进入“AI 设置”，核对服务商、实际 HTTPS Base URL、地域与模型。默认使用北京传统接口和 `qwen3.7-flash` / `qwen3.7-text-embedding-flash` / 1024 维。新业务空间请复制百炼控制台的实际地域接口地址。
3. 在密码框输入 API Key，勾选目标地址确认后保存。Key 由 Windows Credential Manager（keyring）保存；更改 Base URL 后需要为新地址提供对应 Key。
4. 如需验证，勾选连接测试费用提示，再点击“测试已保存配置的 API 连接”。只发送合成文本，各调用一次 Embedding 与 LLM；可能产生费用。
5. 选择项目，在“知识库管理”中批量选择 UTF-8 `.md` / `.txt`，点击“保存上传文件”。上传仅保存在本机，此时不会发送 Embedding 请求。
6. 选择要索引的文件，核对外部目标地址与模型，勾选发送文本确认，再点击“建立索引 / 重新索引”。只有此时发送文档分块。
7. 进入“智能问答”输入问题。展开来源证据可查看实际送给模型的文件名、Chunk ID 和原文。切换项目后只显示对应项目的对话。
8. 同名文件的内容变化会更新该文档并标记“需要重新索引”；相同字节内容在同项目内去重。未重新索引的更新文件不会参与检索。
9. 更换 LLM 不影响索引。更改 Embedding、维度、地址或分块配置后会要求手动重新索引，不会自动发送资料或删除旧向量。

`examples/demo_project_alpha.md` 是虚构的图书目录管理工具资料，`examples/demo_project_beta.md` 是虚构的个人任务清单工具资料。两份资料的名称、背景、实现记录与问答均独立编写，不对应真实个人经历，可分别导入两个示例项目。没有 API Key 时仍可创建项目、保存文件、浏览历史；没有兼容索引时直接提示资料不足。

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

实际路径可在界面左下角“本机数据与隐私”查看。原始上传字节、元数据、聊天和引用都在此处；仓库中只保留源码、测试和人工示例。

可在启动前设置 `PROJECT_RAG_DATA_DIR` 指定其他仓库外目录；这会打开一个独立的数据空间，**不会自动迁移原数据**。指向本仓库内部会明确拒绝启动。API Key 不在该目录，而由操作系统安全凭据保存。安全凭据不可用时明确报错，不会降级保存到 JSON、SQLite 或 `.env`。

本地保存、GitHub 上传与第三方 API 请求是三件事。本应用不连接 GitHub。建立索引时会向配置的 API 发送分块；聊天时会发送问题、受限历史与本次证据。Chroma 与 Streamlit 使用统计已关闭，HTTP 请求不跟随重定向。不要在系统上开启 SDK 调试日志来处理私人资料。

`.gitignore` 排除虚拟环境、工具缓存、数据库、Chroma、上传、日志、私人配置及默认的 Markdown/TXT；公开文档仅放行根目录 README、AGENTS 和两个指定的虚构示例。**不要把私人资料放进公开源码或示例中**。开发记录整目录不纳入版本控制。使用 Git 时，提交前执行：

```powershell
git status --short --ignored
git ls-files
git diff --cached --name-only
```

只允许跟踪源码、安全模板、公开文档与合成示例，不能用 `.gitignore` 代替人工审查。已跟踪的敏感文件不会因追加 ignore 规则而自动停止跟踪。

## 架构

```text
ui/app.py -> backend/services/ -> backend/rag/ + backend/storage/
                                       -> SQLite / 文件 / Chroma / 百炼
```

- `services/application.py` 组装应用；UI 只调用 services，负责显示、控件和临时状态。
- `project_service.py` 创建 UUID 项目；`document_service.py` 验证上传、去重、处理索引状态和版本切换。
- `rag/loader.py` 正常化 UTF-8 和换行，`chunker.py` 保留 Markdown 标题路径，`provider.py` 是可替换的 Embedding/LLM 边界。
- `storage/vector_store.py` 使用独立的“项目 + 文档索引代次”Collection，比单项目 Collection 更细。完整写入后 SQLite 才切换活动指针。失败保留原文件与旧代次，失败文档不参与问答。显式重新索引成功后只清理该文档旧向量。
- `qa_service.py` 限定项目与兼容签名，先向量化受限检索问题，再召回 Top-K，交给 `generator.py` 组装证据约束 Prompt。历史 AI 回答只帮助理解指代，不被向量化为知识来源。
- `storage/database.py` 保存项目、文档、消息、规范 UTC 时间与引用快照。每项目一条对话，按 SQLite 自增序号稳定排序。引用不依赖当前原文件版本，因此重启后仍可展示原回答依据。
- 设置中保留当前模型信息，每个文档保存建立索引时的完整非秘密配置与签名。不同模型、维度或地址的向量不会混用。切换配置不会自动删除旧索引。
- 文件锁防止同项目的上传、索引、问答与清空交错。中断后残留“处理中”在获取锁确认无活动任务时转为失败，允许手动重试。
- 后端不依赖 Streamlit，将来可新增 FastAPI 接口调用相同 services，无需重写 RAG。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check backend ui tests scripts
.\.venv\Scripts\python.exe -m compileall -q backend ui scripts
.\.venv\Scripts\python.exe scripts/smoke_runtime.py
```

测试使用临时目录、Fake Embedding/Fake LLM、HTTP MockTransport 和实际 SQLite/Chroma。禁止外网，仅允许 Windows 异步事件循环所需的回环连接。不需要真实密钥，不产生真实百炼费用。

## 当前限制

- 只支持 UTF-8 Markdown/TXT、每份最多 10 MB；同名更新按文件处理。保留上传历史版本，以保护原始资料，当前没有批量清理界面。
- 按文档 Collection 检索适合个人小型资料库；文件数量很大时有额外查询开销。
- 相似度阈值与模型 `supported` 判断不能数学保证回答正确，仍应核对原文。未实现 reranking 或复杂评估。
- 默认调用超时 45 秒，不自动重试付费请求；长文档可能需要等待多批请求。若中断，手动重新索引。
- 为保守满足模型请求限制，单个 Embedding 文本不能超过 8000 UTF-8 字节，批次最多 10 条且合计不超过 8000 字节；默认 Chunk Size 1000 适用。更大的中文分块可能提示降低大小。
- 首次使用时需配置自己的 Key，并明确触发合成连接测试，以确认目标地域、模型权限和凭据可用性。
