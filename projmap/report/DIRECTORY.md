# projmap/report/ — Report Layer

LLM 驱动的项目简报和查询结果生成。所有标题、分组、状态、优先级均由 LLM 决定，无硬编码规则。

## 文件

| 文件 | 职责 |
|---|---|
| `__init__.py` | 包初始化（空） |
| `prompts.py` | LLM prompt 定义。三个场景：节点 enrichment、query enrichment、brief status 生成 |
| `llm_enricher.py` | LLM 调用核心。API 模式（Anthropic 直调）+ External 模式（prepare-brief / import-brief）。enrichment 缓存读写 |
| `brief_builder.py` | 将 LLM enrichment 结果组装成 ProjectBrief 结构。enrich_node() 负责单节点、build_brief() 负责整体 |
| `render_markdown.py` | Markdown 渲染。render_brief() 输出项目简报，render_query_results() 输出搜索结果页 |
| `grouping.py` | 按 LLM 输出的 group 字段分组。group_by_enrichment() 输出 {group_id: {label, nodes}} |
| `evidence_builder.py` | 证据格式化。提取 evidence_quote、source_file、source_heading，判断是否有有效证据 |
| `source_resolver.py` | 来源解析。判断 source_scope（agent_instruction vs project content） |

## 数据流

```
raw nodes → llm_enricher (API or cached)
         → brief_builder (组装结构)
         → render_markdown (输出)
```

## CLI 命令

| 命令 | 调用链 |
|---|---|
| `projmap brief` | llm_enricher.enrich_nodes → brief_builder.build_brief → render_markdown.render_brief |
| `projmap query X` | llm_enricher.enrich_nodes(query=X) → render_markdown.render_query_results |
| `projmap prepare-brief` | llm_enricher.prepare_brief_tasks → 写任务文件 |
| `projmap import-brief` | llm_enricher.import_brief_results → 写缓存 |
