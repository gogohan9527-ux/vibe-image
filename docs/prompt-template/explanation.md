# 提示词模板 DB 化 + 任务 title 字段 — 项目规章与说明

> 本文件定义 **怎么做**、**谁能改什么**、**怎么跑起来**。
> 所有贡献者（含 AI 子智能体）必须遵守。
> 由 orchestrator 在 Phase A 写成；Phase B 任何 lane 都不得修改。

## 1. 仓库结构（本期相关部分）

```
vibe-image/
├── backend/
│   ├── app/
│   │   ├── api/                # tasks.py / prompts.py 本期会改
│   │   ├── core/               # storage.py / task_manager.py / generator.py 本期会改
│   │   ├── scripts/            # 初始化脚本：init_db.py
│   │   ├── schemas.py          # 本期会改：TaskCreateRequest / TaskItem
│   │   └── main.py             # 本期会改：lifespan 移除 ensure_sample_prompt 自动调用
│   └── tests/                  # 本期新增 / 修改测试
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── AppSidebar.vue      # 本期会改：新增「模板配置」nav
│       │   └── NewTaskDrawer.vue   # 本期会改
│       ├── router/
│       │   └── index.ts            # 本期会改：新增 /templates 路由
│       ├── views/
│       │   └── PromptTemplatesView.vue   # 本期新增
│       ├── api/
│       │   └── client.ts           # 本期会改：新增 updatePrompt
│       └── types/
│           └── api.ts          # 本期会改
├── prompt/                     # 保留，不删
├── docs/
│   └── prompt-template/        # 本期专用文档目录
│       ├── prd.md
│       ├── explanation.md      # 本文件
│       ├── contract.md         # 由 Backend lane 在 B6 行写出，Frontend 必须读
│       └── todolist.md
└── README.md                   # 两个 lane 都需要追加段落
```

## 2. Lane 与所有权（防止两个 Agent 互踩）

> 列名 `可写路径` / `不可写路径` 是协议的一部分，subagent prompt 会原文复用。

| Lane | 可写路径 | 不可写路径 |
|------|---------|-----------|
| **Backend** | `backend/**`、`docs/prompt-template/contract.md`、`docs/prompt-template/todolist.md`（仅 B 行）、`README.md`（追加 Backend 段落） | `frontend/**`、`prompt/*.json`（保留，不删不改）、`docs/prompt-template/prd.md`、`docs/prompt-template/explanation.md`、原项目的 `docs/prd.md` / `docs/explanation.md` / `docs/interface.md` / `docs/todolist.md` |
| **Frontend** | `frontend/**`、`docs/prompt-template/todolist.md`（仅 F 行）、`README.md`（追加 Frontend 段落，与 Backend 段落明确分隔） | `backend/**`、`prompt/*.json`、`docs/prompt-template/prd.md`、`docs/prompt-template/explanation.md`、`docs/prompt-template/contract.md`（只读引用）、原项目其它 docs |

公共文件（PRD、explanation）**只读**。如需调整，先在最终回复反馈，由 orchestrator 决定。

## 3. 命名约定

| 实体 | 规则 | 示例 |
|------|------|------|
| 模板 id | 小写下划线 slug；冲突自动后缀 `_2`、`_3`（保持现有 `_make_unique_id` 行为） | `cute_cat_in_garden` |
| 模板文件名 | `prompt_<id>.json`（仅作为种子，不再读写） | `prompt_sample.json` |
| 任务 title | 字符串，前后空白会被 trim；空时由后端兜底；最大长度由前端 maxlength 控制（60） | `"a cat playing in a garden"` |
| 测试函数 | `test_<unit>_<scenario>` | `test_init_db_skips_existing` |

## 4. 编码规范

### 4.1 Backend (Python)

- 沿用现有项目风格：raw `sqlite3` + `RLock`，无 ORM，类型注解齐全。
- 新增的 SQL 与现有 schema 在 `Storage.__init__` 同一处建表；`ALTER TABLE` 用 try/except 兼容已存在列。
- 不引入新依赖。
- 错误处理沿用 `errors.py` 中的自定义异常；模板与初始化方法不要吞异常，用日志告警 + 跳过单条记录的方式。
- 不在日志中输出 prompt 全文，最多输出前 60 字符。

### 4.2 Frontend (Vue 3 + TypeScript)

- 沿用 Element Plus 控件，`<el-input>` / `<el-form-item>` 与现有抽屉风格一致。
- 不引入新依赖。
- payload 字段命名走后端 snake_case：`save_as_template`、`template_name`、`title`。
- TypeScript 严格模式下保持 `title?: string` 可选。

## 5. 配置与密钥

本期不涉及新增配置。

## 6. 错误处理与日志

- Backend：`init_prompt_templates_from_files` 每条失败 warn + 跳过，最后总结一次 info。
- Backend：title 兜底逻辑不打日志（高频路径）。
- Frontend：保留现有 ElMessage 错误提示风格；title 字段无前端校验弹窗。

## 7. 测试期望

| 范围 | 内容 |
|------|------|
| Backend 单元 | `prompt_templates` CRUD（含 sample 保护）、`init_prompt_templates_from_files` 幂等、`task_manager.submit` 的 title 兜底、POST /api/tasks 三种 title 路径（不传 / 传 / 仅空白）、save_as_template 落库 |
| Backend 集成 | 启动 → 调用 init script → 列模板 应返回种子条目 |
| Frontend | 手动 dev smoke：不填 title / 填 title / 勾选保存模板 三条路径 |

`cd backend && pytest` 全绿是 Backend lane 完工的硬门槛。

## 8. 本地运行

### 8.1 启动 Backend

```sh
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# 首次启动后单独跑一次：
python -m app.scripts.init_db
```

### 8.2 启动 Frontend

```sh
cd frontend
npm install
npm run dev
```

### 8.3 验证

浏览器开 `http://localhost:5173`，新建任务，验证标题输入 + 模板选择 + 保存为模板三条路径。

## 9. Git 与提交

- 一个 lane = 一个或多个独立提交，提交信息形如：`backend: 新增 prompt_templates 表`。
- 不允许跨 lane 提交。
- 不允许 `--no-verify`。
- **本 skill 不自动提交**，由用户最终决定何时 commit。

## 10. 恢复执行约定

`docs/prompt-template/todolist.md` 是断点续跑的唯一真相源。每个 Agent 的工作流：

1. 读 `docs/prompt-template/todolist.md`，定位本 lane 第一个未勾选项。
2. 完成后立即勾选并写一行备注。
3. 全部完成后在文件末尾追加 `<Lane> lane completed at <ISO 时间>`。

如果一个 Agent 中途崩溃，重启它只需要再传同一个 prompt——它会从未勾选项继续。

## 11. AI 助手限制

- 不要修改本文件、`docs/prompt-template/prd.md`、`docs/prompt-template/contract.md`（除拥有 lane 外）。
- 不要新建二进制资源。
- 不要假设其他 lane 的实现细节，只信任 `docs/prompt-template/contract.md` 与 `docs/prompt-template/prd.md`。
- 不要删除 `prompt/*.json` 文件（即使初始化已完成）。
- 不要在 lifespan 自动调用 init 方法（这是用户明确要求的「手动调用」语义）。
