# vibe-image

本地浏览器 UI + Python 后端，提示词生图服务：提示词资产化、并发可调、队列限流、历史记录与图片绑定。

参考文档：
- 产品需求：`docs/prd.md`
- 工程规章：`docs/explanation.md`
- 接口契约：`docs/interface.md`
- 进度看板：`docs/todolist.md`

## Backend

### 准备配置

复制配置模板并填入真实 api_key：

Windows PowerShell 环境：

```powershell
Copy-Item config/config.example.yaml config/config.yaml
# 编辑 config/config.yaml，把 api.api_key 改成真实 key
```

macOS / Linux shell 环境：

```sh
cp config/config.example.yaml config/config.yaml
# 编辑 config/config.yaml，把 api.api_key 改成真实 key
```

`config/config.yaml` 已被 `.gitignore` 排除，绝不会被提交。

### 启动后端

#### 首次启动

```sh
cd backend
python -m app.scripts.init_db
```

Windows PowerShell 环境：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

macOS / Linux shell 环境：

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动成功后：
- OpenAPI 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

### 运行测试

```sh
cd backend
pytest -q
```

测试不会发起任何真实网络请求（HTTP 调用全部被 mock）。

### 关键路径

- 任务持久化在 `data/vibe.db`（SQLite，由 `.gitignore` 排除）。
- 生成的图片落到 `images/generated_<task_id>.<ext>`。
- 提示词模板种子文件在 `prompt/prompt_*.json`，通过 `init_db` 脚本导入 SQLite。

## Frontend

Vue 3 + Vite + TypeScript + Element Plus + Pinia + Vue Router 应用。

### 前置

- Node.js 18+ 和 npm。
- 后端必须先运行在 `http://127.0.0.1:8000`（见上文）。Vite dev server 通过代理把 `/api` 与 `/images` 转发到后端。

### 启动开发模式

```sh
cd frontend
npm install
npm run dev
```

默认打开 <http://localhost:5173>。三个页面：
- `/` — 任务列表（实时 SSE 推送进度）
- `/history` — 历史记录（搜索 / 筛选 / 分页 / 重新生成）
- 侧边栏右下角的"设置"按钮 — 调整并发数与队列上限

### 构建生产包

```sh
cd frontend
npm run build
```

---

## Frontend：新建任务的标题与模板

### 任务标题（可选）

在「新建任务」抽屉顶部新增了**标题**输入框（最多 60 字）：

- **留空**：后端自动取 prompt 前 30 个字符作为标题兜底；若生成完成后响应中包含可用文本则自动回填。
- **填写**：后端直接使用该标题，不再兜底替换。

### 模板下拉

打开「新建任务」抽屉时，模板下拉会自动从后端加载 `prompt_templates` 表的全部数据。选中模板后，提示词文本框自动填入该模板内容。

### 保存为模板

勾选「将本次提示词保存为模板」时：

- 可选填「模板名称」（留空将取 prompt 前 40 字自动命名）。
- 提交任务时，后端同步把该提示词写入 `prompt_templates` 表。
- 下次打开新建任务抽屉，新模板即出现在下拉列表中。

### 模板配置页

侧边栏新增「模板配置」入口，点击进入 `/templates` 页面，支持：

- **新建模板**：填写名称 + 内容，提交后立即生效。
- **编辑模板**：修改已有模板的名称或内容。
- **删除模板**：`el-popconfirm` 二次确认；内置示例模板（`sample`）删除按钮禁用。
