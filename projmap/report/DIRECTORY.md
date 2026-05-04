# projmap/report/ — Report Layer

LLM 驱动的项目简报和查询结果生成。所有标题、分组、状态、优先级均由 LLM 决定，无硬编码规则。

## 文件

| 文件 | 职责 |
|---|---|
| `__init__.py` | 包初始化 |
| `prompts.py` | LLM prompt 定义。三个场景：节点 enrichment、query enrichment、brief status |
| `llm_enricher.py` | LLM 调用核心。API 模式（Anthropic 直调）+ External 模式（prepare-brief / import-brief）。enrichment 缓存读写 |
| `brief_builder.py` | 将 LLM enrichment 结果组装成 ProjectBrief 结构 |
| `render_markdown.py` | Markdown 渲染。render_brief 输出项目简报，render_query_results 输出搜索结果页 |
| `grouping.py` | 按 LLM 输出的 group 字段分组 |
| `evidence_builder.py` | 证据格式化。提取 evidence_quote / source_file / source_heading |
| `source_resolver.py` | 来源解析。判断 source_scope |

## 数据流

```
raw nodes → llm_enricher (API or cached)
         → brief_builder (组装结构)
         → render_markdown (输出)
```

## CLI 命令

| 命令 | 调用链 |
|---|---|
| `projmap brief` | llm_enricher → brief_builder → render_brief |
| `projmap query X` | llm_enricher(query=X) → render_query_results |
| `projmap prepare-brief` | llm_enricher.prepare_brief_tasks → 写任务文件 |
| `projmap import-brief` | llm_enricher.import_brief_results → 写缓存 |
