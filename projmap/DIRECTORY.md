# projmap/ — 核心源码

所有业务逻辑的顶层包。

## 文件

| 文件 | 行数 | 职责 |
|---|---:|---|
| `__init__.py` | 3 | 包初始化，暴露 `__version__` |
| `cli.py` | 627 | CLI 命令定义（Typer）。解析参数，调 api/pipeline/report 层，格式化输出 |
| `api.py` | 348 | 稳定内部 API 层。init / scan / rebuild / get_status / get_context + re-export extraction/skill 函数 |
| `config.py` | 167 | 配置加载。读写 `.projmap/config.toml` |
| `schemas.py` | 199 | Pydantic 数据模型。ChunkRecord / ExtractionResult / Node / Edge / ID 生成 |
| `util.py` | 23 | 共享工具函数。`_ok` / `_err` / `resolve_edge_node`（供 api / pipeline / skill 共用） |

## 子目录

| 目录 | 用途 |
|---|---|
| `ingestion/` | 数据摄入：文件扫描 → 文本分块 → LLM 抽取 |
| `pipeline/` | 管道编排：外部抽取、旧数据迁移、skill 安装 |
| `storage/` | 数据持久化：DuckDB + 文件 hash 缓存 |
| `display/` | 显示层：分类解析 + 格式化 + ViewModel |
| `report/` | Report Layer：LLM 驱动的项目简报和查询结果 |
| `templates/` | HTML 报告模板 |
