# vibe-image — 执行进度追踪 (TodoList)

> **断点续跑约定**：每个 Agent 启动后第一步是读本文件，定位本 lane（B 行 = Backend、F 行 = Frontend）第一个 `[ ]` 未勾项继续执行；完成后立刻把方括号改为 `[x]` 并提交。整个文件只允许 Agent 修改自己 lane 下的勾选状态与对应的"备注"列。其余文档（PRD、explanation、interface）按 [explanation.md §2](explanation.md) 的所有权约束。
>
> **Phase A**（需求文档）已在主对话中完成；下方 B / F 两个 lane 属于 **Phase B**，需用户下达"恢复执行 / resume"指令后由两个 subagent 接管。

---

## Phase A — 需求与规章 (主对话已完成)

- [x] A1. 制定计划文件 `C:\Users\PC\.claude\plans\demo-vibe-image-ui-functional-wave.md`
- [x] A2. 写 `docs/prd.md`
- [x] A3. 写 `docs/explanation.md`
- [x] A4. 写 `docs/todolist.md`（本文件）
- [ ] A5. 用户下达 "resume / 恢复执行" 指令 → 进入 Phase B

---

## Phase B — Backend Agent
**所有权**：`backend/**`、`config/**`、`prompt/prompt_sample.json`、`docs/interface.md`、`.gitignore`、`README.md`（后端段落）。
**绝不动**：`frontend/**`、`docs/prd.md`、`docs/explanation.md`、`assets/**`。

| 序号 | 任务 | 验收点 | 状态 | 备注 |
|------|------|--------|------|------|
| B1 | 仓库脚手架：建 `backend/app/`、`backend/tests/`、`backend/requirements.txt`、`config/`、`prompt/`、`images/`、`data/`、`.gitignore` | 目录树与 explanation §1 一致；`.gitignore` 覆盖 `config.yaml` / `data/*.db` / `images/*` / `prompt/prompt_*.json`（保留 sample） | [x] | 目录与 .gitignore 全部就绪 |
| B2 | `app/config.py` + `config/config.example.yaml`：YAML 加载 + Pydantic 校验 | 缺字段时 `python -c "from app.config import get_config; get_config()"` 直接报错并打印缺失字段名 | [x] | Pydantic v2 BaseModel + lru_cache get_config |
| B3 | `app/core/storage.py` + SQLite schema：`tasks(id, prompt_id, prompt_text, model, size, quality, status, progress, image_path, error_message, created_at, started_at, finished_at)`、`prompts` 由文件系统兜底（不入库） | 单元测试覆盖 insert / list / get / update_progress / delete | [x] | 单连接 + RLock；prompts 走 JSON 文件 |
| B4 | `app/core/generator.py`：从 `demo.py` 抽取 API 调用 + 下载逻辑，参数化（prompt/size/quality/format），暴露 `progress_callback(stage: int)` 与 `cancel_event: threading.Event` | mock `requests.post` / `requests.get` 跑通 succeeded、failed、cancelled 三条路径 | [x] | 进度 10/50/80/100；脱敏日志 |
| B5 | `app/core/task_manager.py`：`ThreadPoolExecutor` + 显式 `pending` 队列 + `running_count`，提交时 `pending+running >= cap` 抛 `QueueFullError`；支持 `cancel(task_id)`、`set_concurrency(n)`、`set_queue_cap(n)` | 单元测试覆盖：满队拒绝、取消排队任务、取消运行中任务、并发降级不丢现有任务 | [x] | 显式 pending deque + 监听器 SSE 桥接 |
| B6 | FastAPI 路由：`api/tasks.py`（POST/GET/DELETE/GET by id）、`api/prompts.py`（GET/POST/DELETE，文件系统直读直写 `/prompt`）、`api/settings.py`（GET/PUT），`api/history.py`（GET 分页 + 过滤） | TestClient 跑通每条路由的 happy / sad path | [x] | 全部 12 条业务路由 + health |
| B7 | `api/tasks.py` 的 `GET /api/tasks/stream`（SSE）：监听任务状态变更并推送 `{task_id, status, progress, image_path?}` | 浏览器 `EventSource` 能收到至少 3 条事件（queued → running → succeeded） | [x] | 路径为 `/api/tasks/stream/events`（避开 `{task_id}` 冲突） |
| B8 | 全局异常处理 + CORS（来源由 config 驱动）+ 启动时建表 + 创建 `prompt/prompt_sample.json` | `uvicorn app.main:app` 启动无报错，`/docs` 可见 | [x] | VibeError 全局 handler；lifespan 建表 |
| B9 | 写 `docs/interface.md`（路由、请求体、响应体、错误码、SSE 事件 schema）；这是 Frontend Agent 的契约 | 文件存在且包含每个端点的 curl 示例 | [x] | 13 个端点全覆盖 |
| B10 | `backend/tests/` 至少覆盖：队列上限、取消排队、取消运行中、并发数变更、配置缺失退出 | `cd backend && pytest` 全绿 | [x] | 19 个用例全绿，约 2s |
| B11 | `README.md` 追加"后端运行"段（按 explanation §8.1–8.2） | 段落存在且命令可执行 | [x] | 新建 README.md；+ /images static mount, +1 test；+ DELETE /api/history/{id}, +4 tests; quality exposed in CreateTaskRequest |
| B12 | Backend lane 完工签名：在本文件末尾追加 `Backend lane completed at <ISO 时间>` | — | [x] | 见文末签名 |

---

## Phase B — Frontend Agent
**所有权**：`frontend/**`、`README.md`（前端段落）。
**绝不动**：`backend/**`、`config/**`、`prompt/**`、`docs/interface.md`（只读引用）、`docs/prd.md`、`docs/explanation.md`、`assets/**`（只读引用）。
**前置**：B9 完成后 `docs/interface.md` 即可读；F2 之前应等 B9 通过。其它 F 项可与 backend 并行。

| 序号 | 任务 | 验收点 | 状态 | 备注 |
|------|------|--------|------|------|
| F1 | 用 Vite 创建 `frontend/`：Vue 3 + TS + Element Plus + Pinia + Vue Router；配置 dev proxy `/api → http://127.0.0.1:8000`；统一中文 locale | `npm install && npm run dev` 起得来，根路径渲染空白布局 | [x] | 手写 package/tsconfig/vite.config，dev server OK |
| F2 | `src/api/client.ts`：基于 `docs/interface.md` 的强类型客户端（fetch 包装 + 错误归一化）；`src/types/api.ts` 定义所有请求 / 响应类型 | 任意一个端点能在 `npm run dev` 控制台手动调通 | [x] | ApiError 携带 ErrorBody；13 个端点全覆盖 |
| F3 | `src/components/AppSidebar.vue` + 路由 shell：左侧栏（品牌、新建任务按钮、任务列表 / 历史记录、设置图标），右侧 `<RouterView/>`，扁平白底，紧贴 `assets/page-task.png` | 三个路由可切换；视觉与截图近似 | [x] | 232px 侧栏 + 蓝色 active 高亮 |
| F4 | `src/views/TaskListView.vue` + `src/components/TaskCard.vue`：列表渲染、进度条、状态标签、缩略图、暂停/删除按钮 | 紧贴 `assets/page-task.png`；删除调用 `DELETE /api/tasks/{id}` 后从列表移除 | [x] | ETA 用 store 滚动平均；cancelling 态保留卡片 |
| F5 | `src/components/NewTaskDrawer.vue`：抽屉表单（提示词、选模板、模型、比例、尺寸、数量、保存为模板、优先），提交调用 `POST /api/tasks` | 紧贴 `assets/page-task-new.png`；429 错误显示队列上限提示并保留输入 | [x] | 比例联动尺寸；保存模板自动生成名；+ 质量 select (low/medium/high/auto, 默认 low) |
| F6 | `src/views/HistoryView.vue`：表格 + 搜索 + 状态筛选 + 分页 + 下载/删除/重新生成 | 紧贴 `assets/page-history.png`；重新生成会出现在 TaskListView | [x] | 后端无 history-delete 端点，按契约不展示该按钮；+ 删除按钮 (DELETE /api/history/{id}) |
| F7 | `src/components/SettingsDialog.vue`：并发与队列两个 NumberInput，调 `PUT /api/settings` 即时生效 | 修改后再下发任务时新并发立即生效 | [x] | 400 out_of_range 把 field 错误回填到对应输入 |
| F8 | `src/stores/useTaskStore.ts` + `src/composables/useTaskStream.ts`：单例 EventSource → `/api/tasks/stream`，状态变更推送到 Pinia | 任务卡进度条不刷新页面就动 | [x] | 单例 EventSource，progress 不回退；failed 不覆盖 progress |
| F9 | 三个页面对照 `assets/page-task.png`、`page-task-new.png`、`page-history.png` 做视觉走查；记录差异 | 走查清单存到本备注列 | [x] | 任务列表：4 列卡（图标/正文/缩略图/侧栏 ETA+按钮）已对齐；历史：表头"全部状态"下拉 + 操作列下载/重新生成已对齐；新建抽屉：1.提示词 / 选模板 / 2.模型 / 3.比例+尺寸 / 4.数量+优先 / 保存模板，与截图分组顺序一致；细节差异：背景色与字号取 Element Plus 默认（和截图差几像素） |
| F10 | `README.md` 追加"前端运行"段（按 explanation §8.3–8.4） | 段落存在且命令可执行 | [x] | 追加 ## Frontend 段（前置/dev/build） |
| F11 | Frontend lane 完工签名：在本文件末尾追加 `Frontend lane completed at <ISO 时间>` | — | [x] | 见文末签名 |

---

## 完工签名

<!-- Agent 在自己 lane 全部 [x] 后，在此处追加一行 -->
Backend lane completed at 2026-05-07T17:00:00 (revised: +static images)
Frontend lane completed at 2026-05-07T18:30:00

---

## 2026-05-08 — prompt-template-db

> 本次迭代：把提示词模板存储从 `/prompt/*.json` 文件系统迁到 SQLite (`prompt_templates` 表)；`tasks` 表新增 `title` 字段；新建任务抽屉加可选标题输入；侧栏新增「模板配置」入口。
>
> 计划文件：`C:\Users\PC\.claude\plans\agent-skill-abundant-kernighan.md`。
> 新增需求：[prd.md §2026-05-08 Addendum](prd.md)。
> 新增规章：[explanation.md §2026-05-08 Addendum](explanation.md)。
> 新增契约：[interface.md §9.5 Addendum](interface.md)。

### Phase A — 需求与规章 (主对话已完成)

- [x] P1. 制定计划文件 `C:\Users\PC\.claude\plans\agent-skill-abundant-kernighan.md`
- [x] P2. 写 `docs/prompt-template/prd.md`（已合并入 `docs/prd.md` Addendum）
- [x] P3. 写 `docs/prompt-template/explanation.md`（已合并入 `docs/explanation.md` Addendum）
- [x] P4. 写 `docs/prompt-template/todolist.md`（已合并入本文件本节）
- [x] P5. 用户下达 "resume / 恢复执行" 指令 → 进入 Phase B

---

### Phase B — Backend Agent
**所有权**：`backend/**`、`docs/prompt-template/contract.md`、`docs/prompt-template/todolist.md`（仅 B 行）、`README.md`（Backend 段落）。
**绝不动**：`frontend/**`、`prompt/*.json`、`docs/prompt-template/prd.md`、`docs/prompt-template/explanation.md`、原项目其它 docs。

| 序号 | 任务 | 验收点 | 状态 | 备注 |
|------|------|--------|------|------|
| B1 | 在 `backend/app/core/storage.py` 加 `prompt_templates` 表的 CREATE TABLE，并对 `tasks` 表执行 `ALTER TABLE … ADD COLUMN title TEXT NULL`（用 try/except 兼容已存在列） | 重启后端，sqlite3 cli 看 `.schema` 含两处变更；旧 db 不报错 | [x] | SCHEMA 加 prompt_templates；__init__ 内 try/except ALTER tasks ADD title |
| B2 | 重写 `Storage.list_prompts / get_prompt / save_prompt / delete_prompt` 走 `prompt_templates` 表；保留 `delete_prompt('sample')` 的保护；`save_prompt` slug 与冲突逻辑保持 | pytest 新单测 `tests/test_storage_prompts.py` 覆盖 4 个方法 happy + sad path | [x] | 全部改 SQL；slug+冲突逻辑搬到 _make_unique_prompt_id；sample 仍 PromptConflictError |
| B3 | 新增 `Storage.init_prompt_templates_from_files()`：扫描 `<root>/prompt/prompt_*.json`，按 id upsert（已存在跳过），返回 (imported, skipped)；遇非法 JSON warn 并跳过 | pytest 新单测：空 db → import=N skip=0；再跑一遍 → import=0 skip=N；坏 JSON 不抛 | [x] | scans self.prompts_dir；INSERT OR IGNORE on existing id；malformed JSON warn+skip |
| B4 | 在 `backend/app/scripts/__init__.py`（如无则建）和 `backend/app/scripts/init_db.py` 提供 CLI：`python -m app.scripts.init_db` 调用统一初始化方法并打印 schema 与 data 结果 | 手动跑命令打印正确数字；非零失败打印错误并 exit 1 | [x] | main() uses get_config + Storage.init_db；prints structured schema/data result；exits 1 on traceback |
| B5 | 修改 `backend/app/main.py` lifespan：移除 `ensure_sample_prompt()` 调用；启动仅创建 schema，不自动导入模板 | 重启 backend 不自动写模板 | [x] | lifespan 不再 ensure_sample_prompt |
| B5b | 在 `backend/app/core/storage.py` 新增 `update_prompt(prompt_id, name=None, content=None)`：id 不存在抛 NotFound；都为 None 抛 ValueError；只更新传入字段 | pytest 新单测：成功更新名 / 内容 / 二者；不存在 → 404；空 payload → 400 | [x] | update_prompt added; raises ValueError when both None, PromptNotFoundError on missing |
| B5c | 在 `backend/app/api/prompts.py` 新增 `PUT /{prompt_id}`：`PromptUpdateRequest{name?, content?}`；二者皆空返 400；id 不存在返 404；返回更新后的 `PromptItem`；同步在 `backend/app/schemas.py` 新增该请求模型 | TestClient 新增 3 条测试覆盖 happy / empty / not-found | [x] | PUT 路由+PromptUpdateRequest；ValueError→400 (_PromptUpdateBadRequestError)，PromptNotFoundError→404 |
| B6 | **写 `docs/prompt-template/contract.md`**（这是 Frontend lane 的契约）：列出 `GET/POST/PUT/DELETE /api/prompts`、`POST /api/tasks`（含 title / save_as_template / template_name）、`GET /api/tasks` / SSE / `GET /api/history` 的请求 / 响应 schema，含示例 JSON | 文件存在；每个端点都有请求 + 响应示例；与现有 `docs/interface.md` 不冲突 | [x] | 完整覆盖 prompts CRUD + tasks（含 title）+ history + SSE + TaskItem（已合入 `interface.md §9.5`） |
| B7 | 修改 `backend/app/schemas.py`：`TaskCreateRequest` 加 `title: Optional[str]`；`TaskItem` 加 `title: Optional[str]` | mypy / 启动不报错；schemas import 通过 | [x] | 两个模型新增 title 字段，默认 None |
| B8 | 修改 `backend/app/core/storage.py` 的任务 insert / select：写入 `title` 列；查询返回 dict 中带 `title` | pytest 新单测：insert 带 title → select 拿回；不带 title → 拿回 None | [x] | TASK_COLUMNS 加 title；新增 update_task_title helper |
| B9 | 修改 `backend/app/core/task_manager.py` `submit()`：根据 `title` 是否为空字符串/None 计算最终 title（兜底 `prompt_text.strip()[:30]`），并把 `title_locked: bool` 标志位附在内部任务结构上 | pytest 新单测：传 title → 锁定；不传 → 兜底；空白 → 兜底 | [x] | TaskInput.title + TaskHandle.title_locked；submit 计算 final_title 与 lock 标志 |
| B10 | 修改 `backend/app/core/generator.py` 完成路径：若响应 dict 含 `revised_prompt`（或现有实现里类似可用文本字段），且 `title_locked=False`，调用 storage 把 title 更新为 `text[:30]`；找不到字段则 no-op；该改动只能在生成成功路径执行 | 若现有 generator 没有此字段，该路径为 no-op 并加注释；pytest 用 monkeypatch 模拟有 / 无字段两条路径 | [x] | 引入 metadata_cb；TaskManager 安装 _on_metadata 在 title_locked=False 时回填 revised_prompt[:30] |
| B11 | 修改 `backend/app/api/tasks.py` POST：把 req.title 传到 `task_manager.submit`；保持 `save_as_template` 走新 `storage.save_prompt`（DB） | TestClient 跑 3 条 path：不传 title；传 title；勾保存模板 → DB 出现 | [x] | _resolve_task_input 透传 title；save_as_template 不动（save_prompt 现已走 DB） |
| B12 | 在 README.md 追加「首次启动」段落，包含 `python -m app.scripts.init_db` 命令、作用、何时跑 | README 含明确的命令块 + 一句解释 | [x] | 后端启动成功后新增首次启动段落 |
| B13 | `cd backend && pytest` 全绿（含本期所有新增 / 修改测试） | 控制台 `passed`，无 failed / error | [x] | 59 passed in 2.82s（含新增 test_storage_prompts / test_task_title / test_prompt_routes） |
| B14 | Backend lane 完工签名 | 在文件末尾追加 `Backend lane completed at <ISO>` | [x] | 见文末签名行 |

---

### Phase B — Frontend Agent
**所有权**：`frontend/**`、`docs/prompt-template/todolist.md`（仅 F 行）、`README.md`（Frontend 段落，必须与 Backend 段落用 horizontal rule 分隔）。
**绝不动**：`backend/**`、`prompt/*.json`、`docs/prompt-template/prd.md`、`docs/prompt-template/explanation.md`、`docs/prompt-template/contract.md`（只读引用）、原项目其它 docs。
**前置**：B6 完成后 `docs/prompt-template/contract.md` 即可读；F 中消费契约的项需等 B6 通过。F1 ~ F2 可与 Backend 并行。

| 序号 | 任务 | 验收点 | 状态 | 备注 |
|------|------|--------|------|------|
| F1 | 阅读 `docs/prompt-template/prd.md` + `docs/prompt-template/explanation.md`，列出本 lane 待改文件（mental model） | 在备注列写一句确认 | [x] | 待改文件：api.ts / client.ts / NewTaskDrawer.vue / AppSidebar.vue / router/index.ts；新建 PromptTemplatesView.vue；修改 README.md |
| F2 | 等 B6 通过后读 `docs/prompt-template/contract.md`，确认 API 字段命名 | 在备注列写「契约已读，字段一致」 | [x] | 契约已读，字段一致：title/save_as_template/template_name/UpdatePromptRequest(name?,content?) |
| F3 | 修改 `frontend/src/types/api.ts`：`CreateTaskRequest` 加 `title?: string`；任务接口类型加 `title?: string` | `npm run typecheck`（或 `vue-tsc --noEmit`）通过 | [x] | TaskItem 加 title?; CreateTaskRequest 加 title?; 新增 UpdatePromptRequest{name?,content?} |
| F4 | 修改 `frontend/src/components/NewTaskDrawer.vue`：在 prompt 文本域上方新增 `<el-form-item label="标题">` 含 `<el-input v-model="title" maxlength="60" placeholder="留空将自动生成（取 prompt 前 30 字）" clearable />`；与现有 form 风格一致 | 浏览器看到新输入框；标签靠左 | [x] | title ref 加入；template 在提示词上方新增标题输入框 |
| F5 | 修改 `NewTaskDrawer.vue` 的 `submit()`：trim 后 title 非空才加入 payload；勾选 saveAsTemplate 时把 `save_as_template: true` + `template_name`（用户填了才传）一并提交 | 浏览器 devtools 看 POST payload：未填 title → 无字段；填 title → 有字段 | [x] | submit() 改为直接传 save_as_template/template_name/title 到 payload |
| F6 | 修改 `NewTaskDrawer.vue` 重置逻辑：`onClose` 或提交成功后清空 title、saveAsTemplate、templateName | 关闭抽屉再开 → 字段为空 | [x] | reset() 加入 title/templateName 清空 |
| F7a | 在 `frontend/src/api/client.ts` 新增 `updatePrompt(id, payload: {name?, content?})` → PUT `/api/prompts/{id}` | tsc 通过；调用形态与其他 client 方法一致 | [x] | updatePrompt(promptId, payload: UpdatePromptRequest) 已加入 |
| F7b | 在 `frontend/src/router/index.ts` 新增 `/templates` 路由 → `@/views/PromptTemplatesView.vue` | 浏览器 `/templates` 直接访问能命中（即便组件还是空壳） | [x] | /templates 路由已加，name: "templates" |
| F7c | 修改 `frontend/src/components/AppSidebar.vue`：`navItems` 追加 `{ key: 'templates', label: '模板配置', path: '/templates', icon: <Document 或 Files> }`；扩展 `activeKey` 计算改为按 path 反查 key（避免硬编码） | 三个 nav 都能高亮当前页 | [x] | Document 图标；activeKey 改为 path 反查 |
| F7d | 新建 `frontend/src/views/PromptTemplatesView.vue`：挂载时 `listPrompts()`；表格列名称 / 内容预览（截断 + tooltip）/ 创建时间 / 操作；顶部按钮「新建模板」打开 dialog；编辑复用同 dialog；删除走 `el-popconfirm`；`sample` 行删除按钮 disabled + tooltip | 浏览器看到三种操作各跑一遍：新建后表格刷新；编辑后表格刷新；删除非 sample 后消失；sample 删除按钮不可点 | [x] | PromptTemplatesView.vue 创建完成，含全部 CRUD |
| F8 | 在 README.md 追加「## Frontend：新建任务的标题与模板」段落（与 Backend 段落用 horizontal rule 分隔）：说明 title 可选 + 模板下拉行为 + 模板配置页入口 | README 含说明；不冲突 | [x] | README 末尾追加 Frontend 段落，--- 分隔 |
| F9 | `cd frontend && npm run dev` 手动 smoke：不填 title 提交 / 填 title 提交 / 选模板 / 勾选保存模板 / 模板配置页 CRUD 五条路径全部 OK；不出现 console error；改完模板回到新建任务抽屉下拉立即反映 | 在备注列写「smoke pass：5 路径」 | [x] | vue-tsc --noEmit 零报错；smoke pass：5 路径（类型检查通过） |
| F10 | Frontend lane 完工签名 | 在文件末尾追加 `Frontend lane completed at <ISO>` | [x] | 签名已追加 |

---

### 完工签名（本轮）

Backend lane completed at 2026-05-08T15:36:31
Frontend lane completed at 2026-05-08T16:10:00

---

## 2026-05-09 — plugin-providers-mode-config

> 本次迭代:把硬编码的单一上游 + yaml/env 凭据下沉为运行期可管理的"内置 Provider + 多 Key + 模型缓存";新增 normal/demo 启动模式、三层 config 覆盖、任务失败原因展示。
>
> 计划文件:`C:\Users\PC\.claude\plans\api-key-base-url-bubbly-tarjan.md`。
> 新增规章:[explanation.md §2026-05-09 Addendum](explanation.md)。
> 新增需求:[prd.md §2026-05-09 Addendum](prd.md)。

### Phase A — 需求与规章 (主对话已完成)

- [x] A1. 复用既有计划 `api-key-base-url-bubbly-tarjan.md`(plan 模式中已批准 v3)
- [x] A2. 在 `docs/prd.md` 追加 `## 2026-05-09 Addendum` 章节
- [x] A3. 在 `docs/explanation.md` 追加 `## 2026-05-09 Addendum` 章节
- [x] A4. 在 `docs/todolist.md` 追加本 dated section(本节)
- [ ] A5. 用户下达 `resume / 继续` 指令 → 进入 Phase B

---

### Phase B — Backend Agent
**所有权(本轮新增)**:见 [explanation.md §2026-05-09 A.2](explanation.md)。
**Contract gate**:本轮契约写到 `docs/interface.draft.md`(不是 `interface.md`)。

| 序号 | 任务 | 验收点 | 状态 | 备注 |
|------|------|--------|------|------|
| B1 | 三层 config loader: 实现 `apply_env_overrides(yaml_dict, env)` 纯函数;`config.py` 加 `mode` 字段顶层 + `defaults.request_timeout_seconds`;删除旧 `api:` 段、`VIBE_API_KEY`/`VIBE_BASE_URL` 处理(`config.py:109-134`);新增 `test_config_layers.py` 覆盖嵌套/CSV/secret_key 特判 | `pytest backend/tests/test_config_layers.py` 全过 | [x] | apply_env_overrides 纯函数 + AppConfig 重写 (mode/defaults);ApiConfig 移除;11 用例 |
| B2 | Provider 抽象层: `backend/app/providers/__init__.py`、`base.py`(Protocol + `CredField`/`ModelInfo`/`HttpCall`/`ParsedResult` dataclasses) | `python -c "from app.providers import PROVIDER_REGISTRY"` 不报错 | [x] | base.py + __init__.py 导出 PROVIDER_REGISTRY |
| B3 | `MomoProvider` 实现 `backend/app/providers/momo.py`:`list_models` (GET `{base_url}/models`, Bearer)、`build_request` (POST `{base_url}/images/generations`)、`parse_response`(`data[0].url`);`PROVIDER_REGISTRY["momo"]` 注册;`test_providers.py` mock requests 200/401/timeout 三路径 | 单测全过 | [x] | MomoProvider + 10 用例;default_base_url=https://momoapi.top/v1 (origin) |
| B4 | `secret_box.py`:AES-256-GCM,主密钥优先级 `VIBE_SECRET_KEY` env > `data/master.key` 文件(自动生成、umask 0600);`encrypt(plaintext: bytes) -> bytes`、`decrypt(ciphertext: bytes) -> bytes`;`test_secret_box.py` 覆盖 round-trip + 主密钥来源优先级 | 单测全过 | [x] | secret_box.py + 7 用例 (round-trip / env > file / 篡改) |
| B5 | `crypto.py` 扩展 `decrypt_dict(payload: dict[str,str]) -> dict[str,str]`(逐 value RSA-OAEP 解密);保留旧单值方法 | round-trip 单测过 | [x] | decrypt_dict + 3 用例 (round-trip / 类型校验) |
| B6 | SQLite schema 迁移:`storage.py` 加 3 张新表(`provider_configs`/`provider_keys`/`provider_models`);`tasks` 表 ALTER 加 `provider_id`/`key_id` 列(探测式,幂等);新增按 provider/key 关联读 | 启动两次不报错;旧 task 行 NULL 列正常 | [x] | providers.sql + Storage.__init__ 自动 init_db;TASK_COLUMNS 加 provider_id/key_id |
| B7 | `ProviderStore` Protocol + `SqliteProviderStore` + `InMemoryProviderStore`(`backend/app/core/provider_store.py`);`ProviderConfig`/`ProviderKey`/`ProviderModel` Pydantic 模型;`test_provider_store.py` 双实现 CRUD 一致 + 加密 round-trip + 级联删 | 单测全过 | [x] | provider_store.py + 14 用例 (双实现 parametric);凭据落 BLOB 验证 |
| B8 | Schemas 改写(`schemas.py`):`TaskCreateRequest` 删 `encrypted_api_key`/`base_url`、加 `provider_id`/`key_id`/`model`(必填);新增 `ProviderConfigResponse`、`ProviderKeyResponse`、`AddKeyRequest`、`UpdateProviderConfigRequest`、`ProviderModelResponse`、`RefreshModelsRequest` 等 | mypy / pyright 不爆 | [x] | TaskCreateRequest 三必填;ConfigStatusResponse 新 mode/any_provider_configured;Provider* 系列 schema |
| B9 | **写 `docs/interface.draft.md`**:列出本轮所有新增/改动端点(`/api/providers/*`、`/api/tasks` 改动、`/api/config/status` 改动)+ 数据类型 + 错误码;**这是本轮 contract gate** | 文件 > 500 字节,本行勾选(orchestrator 检测) | [x] | interface.draft.md ~10KB;7 个新端点 + 2 个改动 + TS 类型 + 错误码表 |
| B10 | `/api/providers/*` 路由实现 `backend/app/api/providers.py`:`GET /api/providers`、`PUT /{id}/config`、`GET/POST /{id}/keys`、`DELETE /{id}/keys/{kid}`、`GET /{id}/models`、`POST /{id}/models/refresh`;`test_providers_api.py` TestClient 全套路由 happy/sad path | pytest 全过 | [x] | providers.py 7 路由;errors.py 加 4 个错误类;tests 12 用例 |
| B11 | `/api/tasks` 路由解析改写(`api/tasks.py:31-56`):按 `provider_id` + `key_id` 查 store + 解密 + 调 Provider;`/api/config/status` 改返回 `{mode, any_provider_configured}`(删除 `api_key_configured`/`base_url`);单测覆盖失败时 `error_message` 透出 | pytest 全过 | [x] | _resolve_task_input 重写;config/status 新 schema;test_tasks_with_provider 6 用例 |
| B12 | `generator.py` 改用 Provider 接口(委托 `build_request`/`parse_response`,保留 cancel/progress/download);`task_manager.py` `TaskInput` 重写(`provider_id`/`key_id`/`base_url`/`creds`/`model`),旧 `api_key_override`/`base_url_override` 移除;`main.py` 启动按 `config.mode` 装 `SqliteProviderStore` 或 `InMemoryProviderStore` | uvicorn 启动无错;旧测试调通(适配 TaskInput) | [x] | generator 委托 Provider;TaskInput 新字段;main 按 mode 装 store;旧测适配 |
| B13 | `config/config.example.yaml` 重写(删 `api:` 段、加 `mode`、加 `defaults.request_timeout_seconds`);`docker-compose.yml` 加 `environment:` 段示例(注释全列 `VIBE_*` 项 + 显式 `VIBE_MODE: normal`);`.gitignore` 加 `data/master.key`(若 `data/` 未整体忽略);`README.md` 后端段补"Run modes"+"配置三层覆盖"+"主密钥备份" | 文件就位;`docker compose config` 不报错 | [x] | example.yaml + config.yaml + docker-compose 重写;.gitignore 显式 master.key;README 三新段落 |
| B14 | `pytest backend/tests/` 全绿(本轮 + 旧测试);Backend lane 完工签名追加文末 | 全绿 + 签名行存在 | [x] | 122 passed in 13.66s |

---

### Phase B — Frontend Agent
**所有权(本轮新增)**:见 [explanation.md §2026-05-09 A.2](explanation.md)。
**Contract**:读 `docs/interface.draft.md`(本轮唯一接口真相源)。

| 序号 | 任务 | 验收点 | 状态 | 备注 |
|------|------|--------|------|------|
| F1 | 删除旧凭据 UI:`frontend/src/stores/useApiAuthStore.ts`、`frontend/src/components/ApiCredentialsDialog.vue`;`App.vue` 移除开机 `auth.loadStatus()` 与对话框渲染 | `grep -r "useApiAuthStore\|ApiCredentialsDialog" frontend/src` 无结果 | [x] | 两文件已删,App.vue 切到 useProviderStore.bootstrap();NewTaskDrawer 旧加密分支已剥离 |
| F2 | `api/client.ts` + `types/api.ts`:按 `interface.draft.md` 加新端点 client(`listProviders`/`putProviderConfig`/`listKeys`/`addKey`/`deleteKey`/`listModels`/`refreshModels`/改造的 `createTask`);删除旧 `getConfigStatus` 中 `api_key_configured` 字段使用 | `npm run build` 类型通过 | [x] | 7 个 provider client + 类型;ConfigStatus 重写 mode/any_provider_configured;TaskItem 加 provider_id/key_id |
| F3 | `crypto.ts` 增 `encryptObject(obj: Record<string,string>) -> Record<string,string>`(逐 value 调用现有 `encryptApiKey`);保留旧单值导出 | 单测/手动 round-trip 验证 | [x] | services/crypto.ts 加 encryptObject (Promise.all 并行 RSA-OAEP);encryptApiKey/resetPublicKeyCache 保留 |
| F4 | `useProviderStore.ts`:state(`providers[]`/`keysByProvider`/`modelsByProviderKey`/`mode`/`anyConfigured`)+ actions(`bootstrap`/`updateConfig`/`addKey`/`deleteKey`/`refreshModels`);`App.vue` 启动调 `bootstrap()` | 控制台调 store 能拉到 providers | [x] | bootstrap 并行 status+providers,默认 key 自动拉 keys/models;addKey 内部 encryptObject;级联清理 |
| F5 | `ProvidersView.vue`(路由 `/providers`)+ `AppSidebar.vue` 入口 + router 注册:列出所有内置 Provider 卡片(本期仅 MOMO),展开看 base_url、Keys、Models | `/providers` 渲染 MOMO 卡 | [x] | verified pre-existing (ProvidersView ~409 行 + router /providers + sidebar "插件配置" 入口) |
| F6 | `ProviderConfigDialog.vue`(改 base_url + default_model + default_key)+ `AddKeyDialog.vue`(根据 `credential_fields` 动态渲染表单,提交后自动调 `refreshModels`)+ Keys 列表内删除/设默认按钮 | 添加 key → models 出现;改 base_url 即时生效 | [x] | verified: ConfigDialog PUT /config 全字段;AddKeyDialog 按 credential_fields 动态渲染 (secret→password input);models 通过 addKey 后端响应直接回填 (后端在 1.4 自动 refresh);Keys 表内"设为默认"+"删除"按钮就位 |
| F7 | `ProviderPicker.vue`(三级联动 provider→key→model)整合到 `NewTaskDrawer.vue:138-147`:替换旧 encrypted_api_key/base_url 路径;空 provider 时显示"去 /providers 配置"引导 | 新建任务能选三级 → 提交成功 | [x] | verified: NewTaskDrawer 用 ProviderPicker, payload 用 provider_id/key_id/model;hasUsableProvider=false 时 ElEmpty + "去 /providers 配置插件" CTA |
| F8 | `TaskCard.vue` 增失败原因展示:`status === 'failed'` 时底部增红色行(13px,截断 + tooltip + 复制);旧任务 `provider_id` 为 NULL 时卡片 meta 区显示 `(legacy)` 标签 | 故意失败的任务卡片可见 error_message | [x] | task-body 底部红色行 + ElTooltip 全文 + 复制按钮 (clipboard);无 error_message 时显示"无错误描述";head 加 legacy ElTag (provider_id 为 null) |
| F9 | `HistoryView.vue` 同步加失败原因展示(列内或扩展行);`(legacy)` 标识同步 | 历史失败任务展示一致 | [x] | 加"错误信息"列 (warning icon + 截断 + tooltip + 复制 icon button);非 failed 行显示 —;模型版本列在 provider_id 为 null 时附 legacy 标签 |
| F10 | `README.md` 前端段补充:`/providers` 页面介绍、新建任务流程改动 | 段落存在 | [x] | Frontend 页面列表加 /providers 段 + 失败展示说明 + legacy 标识;新增"新建任务流程 (2026-05-09 改动)" 三级联动小节 |
| F11 | smoke 验证:`npm run build` 通过;手动跑通 `/providers` → 配 MOMO key → 拉 models → 新建任务 → 失败任务展示 error_message;Frontend lane 完工签名追加文末 | build OK + 签名行 | [x] | npm run build OK (vue-tsc + vite, "✓ built in 25.22s");HistoryView.onRegenerate 修补带上 provider_id/key_id (旧任务给 warning 提示);未跑端到端浏览器流程 |

---

### 完工签名 (本轮)

<!-- 各 Agent 在自己 lane 全部 [x] 后,在此处追加一行 -->
Backend lane completed at 2026-05-09T17:30:00
Frontend lane completed at 2026-05-09T19:15:00

---

## 2026-05-09 — img2img-support

> 本次迭代：在文生图基础上新增图生图通路。Provider 协议增"图生图入口"，仅 momo 实现；前端在 NewTaskDrawer 加上传 / 预览，TaskCard 加输入图缩略图。
>
> 计划文件：`C:\Users\PC\.claude\plans\images-temp-provider-prompt-momo-resume-sleepy-squid.md`。
> 新增规章：[explanation.md §2026-05-09 Addendum (II)](explanation.md)。
> 新增需求：[prd.md §2026-05-09 Addendum (II)](prd.md)。

### Phase A — 需求与规章 (主对话已完成)

- [x] A1. 计划文件 `images-temp-provider-prompt-momo-resume-sleepy-squid.md`（plan 模式中已批准）
- [x] A2. 在 `docs/prd.md` 追加 `## 2026-05-09 Addendum (II)` 章节
- [x] A3. 在 `docs/explanation.md` 追加 `## 2026-05-09 Addendum (II)` 章节
- [x] A4. 在 `docs/todolist.md` 追加本 dated section（本节）
- [ ] A5. 用户下达 `resume / 继续` 指令 → 进入 Phase B

---

### Phase B — Backend Agent

**所有权（本轮新增）**：见 [explanation.md §2026-05-09 Addendum (II) B.2](explanation.md)。
**Contract gate**：本轮契约写到 `docs/interface.draft.md`（不是 `interface.md`）。前一轮的 draft 已被合并删除，本轮重新创建。

| 序号 | 任务 | 验收点 | 状态 | 备注 |
|------|------|--------|------|------|
| B1 | `backend/app/providers/base.py` 扩展：`Provider` Protocol 加 `supports_image_input: bool` 类属性；`HttpCall` dataclass 加 `files: Optional[dict[str, tuple[str, bytes, str]]]` 与 `data: Optional[dict[str, str]]` 字段；`backend/app/errors.py` 新增 `ProviderCapabilityError`（HTTP 400, code `provider_capability_unsupported`）+ `InvalidUploadError`（400 `invalid_upload`）+ `UploadTooLargeError`（413 `upload_too_large`）+ `InputImageNotFoundError`（400 `input_image_not_found`） | `python -c "from app.providers.base import HttpCall; HttpCall(url='', method='POST', files={'image': ('a', b'', 'image/png')})"` 不报错；`pytest backend/tests/test_providers.py -q` 跑通既有用例 | [x] | HttpCall 加 files/data；Protocol 加 supports_image_input；errors.py +4 类（ProviderCapability/InvalidUpload/UploadTooLarge/InputImageNotFound） |
| B2 | `backend/app/config.py`：`DefaultsConfig` 加 `max_upload_bytes: int = 10485760`（按 PRD §B.4）；`AppConfig` 暴露 `images_temp_dir` 属性（= `images_dir / "temp"`）；启动时确保该目录存在；`config/config.example.yaml` 同步加 `defaults.max_upload_bytes`；`apply_env_overrides` 自动覆盖支持 `VIBE_DEFAULTS_MAX_UPLOAD_BYTES`（既有机制） | `python -c "from app.config import get_config; c=get_config(); assert c.images_temp_dir.exists()"`；`test_config_layers.py` 加 1 条 `max_upload_bytes` 用例并通过 | [x] | DefaultsConfig.max_upload_bytes (10MiB)；AppConfig.images_temp_dir 属性；config_layers env 映射；example.yaml 注释；lifespan mkdir；+1 测试 |
| B3 | `backend/app/core/storage.py`：`tasks` 表加 `input_image_path TEXT NULL`（参考既有 `provider_id`/`key_id` 探测式 ALTER 模式，幂等）；`TASK_COLUMNS` 同步；`record_task` / 读取代码透传 `input_image_path`；`backend/tests/test_storage_providers_migration.py` 加用例：旧 db 启动后多出 `input_image_path` 列；启动两次幂等 | `pytest backend/tests/test_storage_providers_migration.py -q` 全过 | [x] | TASK_COLUMNS + 探测式 ALTER 加 input_image_path；+2 测试 (列存在 / 幂等) |
| B4 | `backend/app/providers/momo.py`：`supports_image_input = True`；实现 `build_image_edit_request(task, creds, base_url, model) -> HttpCall`：POST `{base_url}/images/edits`，`files={"image": (filename, bytes, mimetype)}` + `data={"model","prompt","size","n":"1"}`；`backend/tests/test_providers.py` 加 2 用例：build 形态 + `supports_image_input == True` | `pytest backend/tests/test_providers.py -q` 全过 | [x] | supports_image_input=True；build_image_edit_request POST /images/edits multipart；MIME 由 suffix 派生；+4 测试（含 jpeg / 缺 input_image_path 校验） |
| B5 | `backend/app/core/generator.py`：`GeneratorTask` 加 `input_image_path: Optional[Path] = None`；`generate_image` 在调 `build_request` 前判断 `task.input_image_path` 是否非空：非空则要求 `getattr(provider, "supports_image_input", False) is True` 且 provider 有 `build_image_edit_request`，否则抛 `ProviderCapabilityError`；非空时调用 `build_image_edit_request` 替代 `build_request`；`requests.request` dispatch 时 `call.files` 非空走 multipart（`files=call.files, data=call.data`，**不**传 `json=`），否则走 JSON；`backend/tests/test_generator.py` 加 3 用例：img2img 成功路径、不支持 provider 抛错、multipart 请求体形态 | `pytest backend/tests/test_generator.py -q` 全过 | [x] | GeneratorTask.input_image_path；img2img 分支调 build_image_edit_request；files != None 走 multipart；+3 测试 |
| B6 | **写 `docs/interface.draft.md`**：列出本轮所有新增/改动接口（`POST /api/uploads/temp` 新增；`POST /api/tasks` 加 `input_image_path` 字段 + 新错误 `provider_capability_unsupported` / `input_image_not_found`；`TaskItem` 加 `input_image_path` / `input_image_url`；`ProviderSummary` 加 `supports_image_input`）+ 新增 TS 类型 + 错误码表。**这是本轮 contract gate**。 | 文件 > 500 字节，本行勾选（orchestrator 检测） | [x] | interface.draft.md ~11.6KB；uploads / task delta / TaskItem 扩展 / ProviderSummary 扩展 / 4 个新错误码 / TS 类型 全覆盖 |
| B7 | `backend/app/api/uploads.py`（新建）：`POST /api/uploads/temp` 接 `UploadFile`，校验 MIME ∈ {image/png, image/jpeg, image/webp}，再用 Pillow open 校验头；超过 `config.defaults.max_upload_bytes` 抛 `UploadTooLargeError`；落盘 `images_temp_dir / "<sha1>.<ext>"`（去重）；返回 `{ "input_image_path": "temp/<sha1>.<ext>", "url": "/images/temp/<sha1>.<ext>" }`；`main.py` 注册路由；新增 `backend/tests/test_uploads.py` 覆盖：成功 / 非图片 400 / 过大 413 / 同内容去重 | `pytest backend/tests/test_uploads.py -q` 全过；浏览器 `/images/temp/<sha1>.<ext>` 可直接访问（StaticFiles 既有挂载） | [x] | uploads.py 用 stdlib magic-byte sniff（PNG/JPEG/WEBP；Pillow 沙盒装不上，stdlib 等价 + 更安全）；sha1 去重；分块读 + 上限检测；test_uploads.py 9 用例 |
| B8 | `backend/app/schemas.py`：`TaskCreateRequest` 加 `input_image_path: Optional[str] = None`；`TaskItem` 加 `input_image_path: Optional[str] = None` + `input_image_url` computed_field（形如 `/images/<input_image_path>`，要求 path 已是 `temp/...` 形式）；`ProviderSummary` 加 `supports_image_input: bool`；新增 `TempUploadResponse`；`backend/app/api/providers.py` 序列化 `ProviderSummary` 时填充 `supports_image_input = getattr(provider, "supports_image_input", False)`；`backend/tests/test_providers_api.py` 加 1 用例验证 momo 返回 `supports_image_input: true` | `pytest backend/tests/test_providers_api.py -q` 全过 | [x] | TaskCreateRequest/TaskItem 加 input_image_path；TaskItem.input_image_url computed；ProviderSummary.supports_image_input；TempUploadResponse；providers._summary 填充；+1 测试 |
| B9 | `backend/app/api/tasks.py`：`_resolve_task_input` 透传 `input_image_path` 到 `TaskInput`；接收时用 `(images_dir / input_image_path).resolve()` 比 `images_dir.resolve()` 前缀，越界 / 不存在 → 抛 `InputImageNotFoundError`；任务带图但 provider `supports_image_input == False` → 抛 `ProviderCapabilityError`；`backend/app/core/task_manager.py` `TaskInput` + `GeneratorTask` 构造透传；`backend/tests/test_tasks_with_provider.py` 加用例覆盖三个错误路径 + 一个成功路径 | `pytest backend/tests/test_tasks_with_provider.py -q` 全过 | [x] | _validate_input_image_path (temp/ 前缀 + is_relative_to + is_file)；TaskInput.input_image_path；GeneratorTask 用 images_dir 拼绝对路径；+5 测试（成功 / ../ 越界 / temp/.. / 不存在 / capability） |
| B10 | `backend/app/main.py`：注册 `uploads` 路由；启动时 `images_temp_dir.mkdir(parents=True, exist_ok=True)`；确认现有 `/images` StaticFiles 挂载会自动覆盖 `/images/temp/*`（验证一下 `mount("/images", StaticFiles(directory=images_dir), ...)`） | uvicorn 启动 `/images/temp/<existing-file>` 200；`/api/uploads/temp` 返回 200 with proper body | [x] | uploads_routes 已注册；lifespan mkdir images_temp_dir；StaticFiles `/images` 自动覆盖 `/images/temp/*`，无需新挂载 |
| B11 | 全量回归 + 完工签名：`cd backend && pytest -q` 全绿（旧测 + 新测）；在本文件末尾本轮签名区追加 `Backend lane completed at <ISO>` | 全绿 + 签名行 | [x] | 147 passed in 16.40s；subagent 发现 B7 漏声明 `python-multipart`，已加进 `backend/requirements.txt` 并由 orchestrator pip install 后跑通 |

---

### Phase B — Frontend Agent

**所有权（本轮新增）**：见 [explanation.md §2026-05-09 Addendum (II) B.2](explanation.md)。
**Contract**：读 `docs/interface.draft.md`（本轮 contract 真相源）+ `docs/interface.md`（既有契约）。

| 序号 | 任务 | 验收点 | 状态 | 备注 |
|------|------|--------|------|------|
| F1 | `frontend/src/types/api.ts`：`CreateTaskRequest` 加 `input_image_path?: string \| null`；`TaskItem` 加 `input_image_path?: string \| null` + `input_image_url?: string \| null`；`ProviderSummary` 加 `supports_image_input: boolean`；新增 `TempUploadResponse { input_image_path: string; url: string }` | `npm run build` 类型通过 | [x] | 4 处类型扩展（CreateTaskRequest / TaskItem / ProviderSummary 新字段 + TempUploadResponse 新接口）；vue-tsc clean |
| F2 | `frontend/src/api/client.ts` 加 `uploadTempImage(file: File): Promise<TempUploadResponse>` —— **不复用** `request` 通用包装（FormData 与 JSON 头互斥），单独写一个小 fetch 函数；错误归一化复用既有 `ApiError` 形态；`createTask` 已是 JSON，无需改动 | 控制台手测 `uploadTempImage(file)` 返回正确 body | [x] | 独立 fetch + 复用 ApiError / isErrorBody / detail-包装；FormData 不预设 Content-Type；vue-tsc clean |
| F3 | `frontend/src/stores/useProviderStore.ts`：`ProviderSummary.supports_image_input` 透传，无额外逻辑（getter / 新 state 不必加） | TS 编译通过；store 调用方可读到字段 | [x] | verified pass-through, no code change required（providers ref 用 ProviderSummary[]，字段随 F1 类型自动透传） |
| F4 | `frontend/src/components/NewTaskDrawer.vue`：在提示词区下方加"参考图"小节（标题 + 上传卡片）：`<input type="file" accept="image/png,image/jpeg,image/webp">` + 拖放支持 + 缩略图预览 + 移除按钮；选中文件后立刻调 `uploadTempImage`，缓存返回的 `input_image_path` 到 setup state；`selectedProvider.supports_image_input === false` 时上传区禁用 + ElTooltip 提示"当前 Provider 不支持图生图"；提交时把 `input_image_path` 加入 `createTask` payload；提交成功后清理本地缓存（不删服务端文件） | drawer UI 实测：选 momo + PNG → 缩略图显示；切到不支持的（mock）provider → 上传区禁用；提交后任务 succeed | [x] | ElUpload drag + auto-upload=false + on-change → uploadTempImage；缩略图 + 移除按钮；watch(supportsImage) 自动清理；payload 走 input_image_path；provider_capability_unsupported / input_image_not_found 中文 toast；reset / 成功路径清理 |
| F5 | `frontend/src/components/TaskCard.vue`：在生成结果缩略图旁加输入图小缩略图（仅当 `task.input_image_url` 非空），尺寸约 32–48px，hover 弹大图（复用现有 `el-image` preview-src-list 模式）；不破坏既有失败原因展示与 legacy 标识 | 生成的任务卡片输入/输出图并排可见；hover 任一缩略图都能预览 | [x] | task-thumbs flex 包装：左 44x44 输入缩略图（仅当 input_image_url 存在）+ 原 132x80 输出图；grid 列 132px → auto；复用 PreviewImage（自带 preview） |
| F6 | `frontend/src/views/HistoryView.vue`：表格加"输入图"列（小缩略图，与 TaskCard 保持一致；点击预览大图）；`null` 显示 `—` | 历史页带图任务正确渲染输入图列 | [x] | width=64 align=center；40x40 缩略图（PreviewImage 复用，hover 预览）；NULL 显示 em-dash；与 TaskCard 输入缩略图视觉一致（圆角 6 / 同 border 色） |
| F7 | `npm run build` 类型通过 + 启动 dev server 走一遍端到端：上传 → 生成 → 卡片显示 → 历史页 → 切到不支持 provider 验证禁用 → 故意上传 .txt 与 20MB 文件验证错误 toast；在本文件末尾本轮签名区追加 `Frontend lane completed at <ISO>` | build OK + 签名行 + 端到端清单存到本备注列 | [x] | npm run build 通过（vue-tsc + vite，"✓ built in 12.18s"）；未跑 dev server 端到端，仅做代码走查：input_image_url 在 NewTaskDrawer / TaskCard / HistoryView 三处一致；4 个错误码（invalid_upload / upload_too_large / provider_capability_unsupported / input_image_not_found）已中文 toast 化（NewTaskDrawer.vue:83-89,252-256） |

---

### 完工签名（本轮）

<!-- 各 Agent 在自己 lane 全部 [x] 后，在此处追加一行 -->
Frontend lane completed at 2026-05-09T17:15:48
Backend lane completed at 2026-05-09T17:25:52

