# projmap/pipeline/ — 管道编排

一次性运行的管道逻辑：外部抽取、旧数据迁移、skill 安装。

## 文件

| 文件 | 职责 |
|---|---|
| `__init__.py` | 包初始化 |
| `extraction.py` | 外部抽取管道。`prepare_extraction` 生成任务文件（含 prompt + 文档），`import_extraction` 读取 LLM 结果写入 DuckDB。包含 TASK_DIR / NODE_TYPES / EDGE_TYPES / EXTRACTION_RULES 常量 |
| `migrate.py` | 旧数据迁移。将旧 schema 节点升级到 v5（补充 project / version / module / status / visibility）。包含项目推断、版本匹配、模块推断逻辑 |
| `skill.py` | Skill 安装。生成 projMap Memory Skill markdown 文件，供 Codex / Claude Code 使用。包含完整 SKILL_MD 模板 |
