# 提示词模板 DB 化 + 任务 title 字段 — PRD

> 本文件定义 **要做什么** 与 **何时算做完**。
> 由 orchestrator 在 Phase A 写成；Phase B 任何 lane 都不得修改本文件。
> 如发现需求歧义或缺漏，subagent 在最终回复中反馈，由 orchestrator 决定是否更新。

## 1. 背景

vibe-image 当前的提示词模板存储在 `/prompt/prompt_*.json`（一份模板一个文件），通过 `Storage.list_prompts/save_prompt/delete_prompt` 直接读写文件系统。`NewTaskDrawer.vue` 已有「模板下拉」与「保存为模板」勾选项，但保存逻辑未接入提交流程；任务表无 `title` 字段，无法在列表中区分相似 prompt 的任务。

本期改造把模板存储迁到 SQLite，并在新建任务流程中加入可选标题（不填则自动兜底）。

## 2. 目标

| 序号 | 目标 |
|------|------|
| G1 | 新增 `prompt_templates` 表，所有模板 CRUD 走 DB |
| G2 | 提供独立的初始化方法把 `/prompt/*.json` 同步入库（首次手动调用，不删除 JSON） |
| G3 | `tasks` 表新增 `title` 字段，POST /api/tasks 支持可选 title |
| G4 | NewTaskDrawer 顶部新增标题输入框；勾选「保存为模板」时落库到新表 |
| G5 | title 为空时：先用 `prompt[:30]` 兜底；若 generator 完成响应中有可用文本则覆盖 |
| G6 | 侧边导航新增「模板配置」入口，提供模板列表 + 新建 / 编辑 / 删除 UI |

## 3. 非目标

- 不在任务卡 / 历史页展示 title（仅存库与回包）
- 不做模板下拉的搜索 / 过滤
- 不删除 `/prompt/*.json` 文件（保留作为种子）
- 不做模板版本化、收藏、分类、批量导入导出
- 不引入文本 LLM 调用专门生成标题
- 模板配置页本期不做权限控制（单机使用）

## 4. 核心能力（用户原文）

> 1. 新建任务时 如果勾选将本次提示词保存为模板则存库到提示词模板表
> 2. 项目初始化时，默认将/prompt模板表的数据初始化到模板表中
> 3. 新建任务的UI变更 支持标题 选择模板从库里查 如果不填标题 看是不是有好的办法自动生成标题 或者通过AI的response来保存标题

用户对存储方案的补充：「python独立一个初始化方法 第一次启动时手动去调用这个方法 不删除json 记得加到readme中」。
用户对标题策略的补充：「13结合 如果3没有回填就用1」（先按 prompt 截取兜底，generator 若有可用响应文本则回填）。
用户对 UI 范围的补充：「保留现有将本次任务建为模板 这个勾选项」。

## 5. 角色与场景

**角色**：vibe-image 单机使用者（个人使用者，本地启动前后端）。

| 场景 | 描述 |
|------|------|
| S1 | 首次启动后手动执行初始化命令，把 `/prompt/*.json` 全部导入 `prompt_templates` 表 |
| S2 | 用户打开新建任务抽屉，从下拉中选已有模板，prompt 自动填入；可选填写标题 |
| S3 | 用户输入新 prompt + 勾选「保存为模板」+ 选填 template_name，提交后该模板出现在下次的下拉里 |
| S4 | 用户提交时不填标题 → 后端用 `prompt[:30]` 写入 title；任务完成时若 generator 返回 revised_prompt 则覆盖 |
| S5 | 用户点侧栏「模板配置」进入模板列表页，新建 / 编辑 / 删除某条模板，操作完即时生效，下次新建任务的下拉马上能看到 |

## 6. 功能需求

### 6.1 后端 — 提示词模板表

- 新表 `prompt_templates(id TEXT PK, name TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)`，建表 SQL 与现有 `tasks` 一同维护，启动时若不存在则自动创建。
- 现有 `tasks` 表新增 `title TEXT NULL`，使用 `ALTER TABLE … ADD COLUMN` 兼容已有库。
- `Storage.list_prompts() / get_prompt(id) / save_prompt(name, content, prompt_id=None) / delete_prompt(id)` 全部改为读写 `prompt_templates` 表。
  - `delete_prompt('sample')` 仍受保护，行为保持。
  - `save_prompt` 在 id 缺省时按现有 slug 规则生成、冲突时追加序号；仍要求 (name, content) 必填。

### 6.2 后端 — 独立初始化方法

- 新增 `Storage.init_db()`：补齐缺失数据库 schema 后扫描 `<project_root>/prompt/prompt_*.json`，对每条按 `id` 主键导入（已存在则跳过，不更新内容）；返回写入条数与跳过条数。
- 提供 CLI 入口：`python -m app.scripts.init_db`；命令打印 `schema.tasks=... schema.prompt_templates=... data.prompt_templates.imported=N data.prompt_templates.skipped=M`。
- 启动时（lifespan）**不再** 自动调用 `ensure_sample_prompt`；改为在 startup 日志里输出一行提示，引导用户手动跑初始化命令。
- README 新增「首次初始化提示词模板」一节，给出执行命令与作用说明。

### 6.3 后端 — 任务 title

- `TaskCreateRequest` 新增 `title: Optional[str]`（去前后空白后非空才算用户提供）。
- `TaskItem` 新增 `title: Optional[str]`，写库与所有响应路径（POST 返回、GET 列表、GET 单条、SSE、history）都带上该字段。
- `task_manager.submit()` 在创建 row 时计算 title：
  - 用户提供 title（非空）→ 直接用，并设内部标志「title 已锁定」。
  - 用户未提供 → 取 `prompt_text.strip()[:30]` 作为兜底；标志「未锁定」。
- 生成完成路径 (`generator.generate(...)` 返回值或回调里) 若发现 `revised_prompt` 等可用文本字段，且 title 未锁定，则把 title 更新为 `text[:30]`；找不到字段则保持兜底值。
  - 当前 generator 的真实响应字段以 `backend/app/core/generator.py` 现有实现为准；若不存在该字段，本步骤为 no-op（不视为 bug）。

### 6.4 后端 — 保存模板透传

- 现有 `POST /api/tasks` 已有 `save_as_template` / `template_name` 字段，逻辑保持，但底层 `storage.save_prompt` 现在写 DB 表。
- `template_name` 缺省时使用 `prompt[:40]`（与现有 tasks.py 行为一致）。

### 6.5 前端 — NewTaskDrawer 标题输入

- 在 prompt 文本域上方新增 `el-input v-model="title"`，placeholder：「留空将自动生成（取 prompt 前 30 字）」。
- 不强制必填；`maxlength="60"` 即可。
- 关闭抽屉 / 提交成功后清空 title。

### 6.6 前端 — 模板下拉与保存模板勾选

- 模板下拉继续调用 `listPrompts()`（路径不变，后端已改 DB，前端无感）。
- 「保存为模板」勾选项的可见行为保持，但提交时把 `save_as_template`、`template_name`、`title` 三个字段一并透传给后端。
- `submit()` 内：
  - 仅在 `title.value.trim()` 非空时把 title 加入 payload。
  - 仅在勾选 `saveAsTemplate` 时把 `save_as_template: true` 与 `template_name`（用户填了才传）加入 payload。

### 6.7 前端 — 类型定义

- `frontend/src/types/api.ts`：`CreateTaskRequest` 增加 `title?: string`；`Task`（或对应任务接口类型）增加 `title?: string`；新增 `UpdatePromptRequest { name?: string; content?: string }`。

### 6.8 后端 — 模板编辑接口

- 新增 `PUT /api/prompts/{id}`：请求体 `{name?: string, content?: string}`，二者都可选但至少要传一个；返回更新后的 `PromptItem`。
- `Storage.update_prompt(prompt_id, name=None, content=None)`：写库；id 不存在抛 404；保护 `sample` 不允许改 id（但允许改名/内容，若需要也可放开，本期允许改名/内容）。
- API client 增加 `updatePrompt(id, payload)`。

### 6.9 前端 — 模板配置页

- 新增路由：`/templates` → `frontend/src/views/PromptTemplatesView.vue`，路由 `name: "templates"`。
- 在 `AppSidebar.vue` 的 `navItems` 中追加一项 `{ key: 'templates', label: '模板配置', path: '/templates', icon: <一个 Element Plus 图标，如 Files 或 Document> }`，`activeKey` 计算逻辑相应扩展（按 path 匹配，避免硬编码二选一）。
- 模板配置页 UI（用 Element Plus 现有控件，与其它页面风格一致）：
  - 顶部按钮「新建模板」打开 `el-dialog` 含 `name`（必填，maxlength 60）+ `content`（必填，textarea，maxlength 2000）两个字段。
  - 主体 `el-table` 列：名称 / 内容预览（截断 60 字 + tooltip 看全）/ 创建时间 / 操作（编辑 / 删除）。
  - 编辑 = 复用同一个 dialog，预填后调 PUT；删除走 `el-popconfirm` 二次确认；`sample` 模板的删除按钮 disabled 并 tooltip「示例模板不可删除」。
  - 列表挂载时调 `listPrompts()`；增 / 改 / 删后刷新。
- 不需要分页 / 搜索（本期非目标）。

## 7. 非功能需求

| 维度 | 要求 |
|------|------|
| 兼容性 | 已有 SQLite DB 启动后能自动建新表 + 加新列；旧 task 行 title 为 NULL，前端容忍 |
| 持久化 | 模板只存 DB（一旦初始化导入）；JSON 文件保留作为种子，不再被读写 |
| 错误语义 | 与现有保持一致：`save_prompt` 名字/内容空返 400；`delete_prompt('sample')` 拒绝；初始化命令对单条失败的 JSON 跳过并打日志 |
| 性能 | 初始化方法是一次性命令，无性能要求；模板列表查询使用主键即可 |
| 安全 | 不引入新外部依赖；不向日志打印 prompt 全文（与现有日志策略一致） |

## 8. 配置 / Schema

```sql
-- 新表
CREATE TABLE IF NOT EXISTS prompt_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 已有表加列
ALTER TABLE tasks ADD COLUMN title TEXT NULL;
```

## 9. 错误语义（关键路径）

| 场景 | HTTP / 退出码 | 响应体 / 行为 |
|------|---------------|---------------|
| POST /api/prompts name/content 空 | 400 | `{detail: "name and content required"}`（保持现有） |
| DELETE /api/prompts/sample | 400 | `{detail: "sample prompt is protected"}`（保持现有） |
| init_db 找到非法 JSON | exit 0 | 控制台 warn 该文件并跳过；最后打印总结 |
| init_db 重复执行 | exit 0 | skip 已存在条目；输出 `data.prompt_templates.imported=0` / `data.prompt_templates.skipped=N` |
| POST /api/tasks 不传 title | 201 | DB 中 title = `prompt[:30]` |
| POST /api/tasks 传 title="  " | 201 | 视为空，走兜底 |
| PUT /api/prompts/{id} body 为空对象 | 400 | `{detail: "name or content required"}` |
| PUT /api/prompts/{id} id 不存在 | 404 | `{detail: "prompt not found"}` |
| 删除 sample（前端） | 按钮 disabled | 不发请求；tooltip 提示 |

## 10. 验收标准

- [ ] 关闭后端、启动后 SQLite 中可见 `prompt_templates` 表与 `tasks.title` 列
- [ ] 新建空数据库 → 启动 → 调用 `python -m app.scripts.init_db`，`prompt_templates` 出现 `prompt/*.json` 全部条目
- [ ] 重复执行初始化命令，写入 0 条、跳过 N 条
- [ ] `curl -X POST /api/tasks -d '{"prompt":"a cute cat in garden"}'` → 返回 JSON 含 `title: "a cute cat in garden"`，DB tasks.title 同
- [ ] `curl -X POST /api/tasks -d '{"prompt":"...","title":"my fav","save_as_template":true,"template_name":"猫"}'` → DB tasks.title="my fav"，prompt_templates 多一条 name="猫"
- [ ] 前端 dev：不填 title 提交 → 创建成功；填 title 提交 → 后端响应字段含原值
- [ ] 前端 dev：选模板 → prompt 自动填充；勾选保存模板提交 → 重新打开抽屉模板列表新增一条
- [ ] README 含「首次初始化提示词模板」段落，包含可复制的命令
- [ ] 侧栏出现「模板配置」入口，点击进入 `/templates`，列表能看到 DB 全部模板
- [ ] 模板配置页支持新建 / 编辑 / 删除三条路径（sample 删除按钮 disabled）
- [ ] 模板配置页改完后回到新建任务抽屉，模板下拉立即反映变化
- [ ] `cd backend && pytest` 全绿（含本期新增 / 修改的测试）
