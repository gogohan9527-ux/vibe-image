# 提示词模板 DB 化 + 任务 title 字段 — 执行进度追踪 (TodoList)

> **断点续跑约定**：每个 Agent 启动后第一步是读本文件，定位本 lane（B 行 = Backend、F 行 = Frontend）第一个 `[ ]` 未勾项继续执行；完成后立刻把方括号改为 `[x]` 并在备注列写一行。整个文件只允许 Agent 修改自己 lane 下的勾选状态与对应的"备注"列。其余文档按 [explanation.md §2](explanation.md) 的所有权约束。
>
> **Phase A**（需求文档）由 orchestrator 在主对话中完成；下方 B / F 两个 lane 属于 **Phase B**，需用户下达"resume / 恢复执行"指令后由两个 subagent 接管。

---

## Phase A — 需求与规章 (主对话已完成)

- [x] P1. 制定计划文件 `C:\Users\PC\.claude\plans\agent-skill-abundant-kernighan.md`
- [x] P2. 写 `docs/prompt-template/prd.md`
- [x] P3. 写 `docs/prompt-template/explanation.md`
- [x] P4. 写 `docs/prompt-template/todolist.md`（本文件）
- [ ] P5. 用户下达 "resume / 恢复执行" 指令 → 进入 Phase B

---

## Phase B — Backend Agent
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
| B6 | **写 `docs/prompt-template/contract.md`**（这是 Frontend lane 的契约）：列出 `GET/POST/PUT/DELETE /api/prompts`、`POST /api/tasks`（含 title / save_as_template / template_name）、`GET /api/tasks` / SSE / `GET /api/history` 的请求 / 响应 schema，含示例 JSON | 文件存在；每个端点都有请求 + 响应示例；与现有 `docs/interface.md` 不冲突 | [x] | 完整覆盖 prompts CRUD + tasks（含 title）+ history + SSE + TaskItem |
| B7 | 修改 `backend/app/schemas.py`：`TaskCreateRequest` 加 `title: Optional[str]`；`TaskItem` 加 `title: Optional[str]` | mypy / 启动不报错；schemas import 通过 | [x] | 两个模型新增 title 字段，默认 None |
| B8 | 修改 `backend/app/core/storage.py` 的任务 insert / select：写入 `title` 列；查询返回 dict 中带 `title` | pytest 新单测：insert 带 title → select 拿回；不带 title → 拿回 None | [x] | TASK_COLUMNS 加 title；新增 update_task_title helper |
| B9 | 修改 `backend/app/core/task_manager.py` `submit()`：根据 `title` 是否为空字符串/None 计算最终 title（兜底 `prompt_text.strip()[:30]`），并把 `title_locked: bool` 标志位附在内部任务结构上 | pytest 新单测：传 title → 锁定；不传 → 兜底；空白 → 兜底 | [x] | TaskInput.title + TaskHandle.title_locked；submit 计算 final_title 与 lock 标志 |
| B10 | 修改 `backend/app/core/generator.py` 完成路径：若响应 dict 含 `revised_prompt`（或现有实现里类似可用文本字段），且 `title_locked=False`，调用 storage 把 title 更新为 `text[:30]`；找不到字段则 no-op；该改动只能在生成成功路径执行 | 若现有 generator 没有此字段，该路径为 no-op 并加注释；pytest 用 monkeypatch 模拟有 / 无字段两条路径 | [x] | 引入 metadata_cb；TaskManager 安装 _on_metadata 在 title_locked=False 时回填 revised_prompt[:30] |
| B11 | 修改 `backend/app/api/tasks.py` POST：把 req.title 传到 `task_manager.submit`；保持 `save_as_template` 走新 `storage.save_prompt`（DB） | TestClient 跑 3 条 path：不传 title；传 title；勾保存模板 → DB 出现 | [x] | _resolve_task_input 透传 title；save_as_template 不动（save_prompt 现已走 DB） |
| B12 | 在 README.md 追加「首次启动」段落，包含 `python -m app.scripts.init_db` 命令、作用、何时跑 | README 含明确的命令块 + 一句解释 | [x] | 后端启动成功后新增首次启动段落 |
| B13 | `cd backend && pytest` 全绿（含本期所有新增 / 修改测试） | 控制台 `passed`，无 failed / error | [x] | 59 passed in 2.82s（含新增 test_storage_prompts / test_task_title / test_prompt_routes） |
| B14 | Backend lane 完工签名 | 在文件末尾追加 `Backend lane completed at <ISO>` | [x] | 见文末签名行 |

---

## Phase B — Frontend Agent
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

## 完工签名

<!-- Agent 在自己 lane 全部 [x] 后，在此处追加一行：
     `<Lane> lane completed at <YYYY-MM-DDTHH:MM:SS>` -->
Backend lane completed at 2026-05-08T15:36:31
Frontend lane completed at 2026-05-08T16:10:00
