# tests/ — 测试套件

326 个测试，覆盖核心模块和 CLI。

## 文件

| 文件 | 测试对象 |
|---|---|
| `__init__.py` | 包初始化（空） |
| `test_api.py` | api.py — init/scan/rebuild/status/context 的 JSON 输出 |
| `test_cache.py` | cache.py — 文件 hash 缓存读写 |
| `test_chunk_identity.py` | chunker.py — heading 路径、语义锚点、slug 稳定性 |
| `test_cli_json.py` | CLI 子进程 — 各命令的 --format json 输出 |
| `test_config.py` | config.py — 默认配置、读写 |
| `test_duckdb.py` | duckdb_store.py — 建表、插入、查询 |
| `test_external_extraction.py` | external extraction — prepare-extraction + import-extraction 完整流程 |
| `test_hash.py` | chunker.py — 分块创建、大小限制、行号追踪 |
| `test_resolvers.py` | resolvers.py — 时间标签、可见性、module 标准化、badges、格式化 |
| `test_scanner.py` | scanner.py — 文件发现、ignore 规则、hash 检测 |
| `test_schemas.py` | schemas.py — Pydantic 校验、ID 生成 |
| `test_skill_and_config.py` | skill 安装、抽取配置、import 配置集成 |
| `test_viewmodel.py` | viewmodel.py — RowBuilder、TableViewModel、legacy 迁移 |

## 子目录

| 目录 | 用途 |
|---|---|
| `fixtures/` | 测试固件数据 |
| `fixtures/sample_project/` | 模拟项目目录（含 docs、README、CLAUDE.md） |
| `fixtures/v5/` | v5 schema 节点/边/来源的 JSON 样本 |
