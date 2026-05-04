# projmap/ — 核心源码

所有业务逻辑的顶层包。CLI 入口 + 稳定 API 层 + 各功能模块。

## 文件

| 文件 | 职责 |
|---|---|
| `__init__.py` | 包初始化（空） |
| `cli.py` | CLI 命令定义（Typer）。解析参数，调 api/report 层，格式化输出。包含 migrate 命令的内联逻辑 |
| `api.py` | 稳定内部 API。所有函数返回 dict，不依赖 Rich/Typer。包含 init/scan/rebuild/extraction/skill 五块逻辑 |
| `config.py` | 配置加载。读写 `.projmap/config.toml`，定义 Config dataclass |
| `schemas.py` | 数据模型定义。Pydantic models：ChunkRecord、ExtractionResult、Node/Edge。ID 生成、content 标准化 |
| `chunker.py` | 文本分块。按字符数切分文档，保留 heading 路径和语义锚点 |
| `scanner.py` | 文件扫描。发现项目文件，计算 hash，判断 new/changed/unchanged |
| `extractor.py` | LLM 抽取。Anthropic API 调用 + external 模式的 prompt 生成。从文档块抽取节点和边 |
| `resolvers.py` | 确定性解析器。分类推断（project/version/module）、时间标签、可见性判断、显示格式化 |
| `viewmodel.py` | ViewModel 构建器。将 DB 行转为可渲染的 RowViewModel，供 context/doctor 命令使用 |

## 子目录

| 目录 | 用途 |
|---|---|
| `storage/` | 数据持久化（DuckDB + 文件 hash 缓存） |
| `report/` | Report Layer — LLM 驱动的项目简报和查询结果生成 |
| `intelligence/` | 智能分析（预留） |
| `outputs/` | 输出格式（预留） |
| `templates/` | 模板文件（HTML 报告模板） |
