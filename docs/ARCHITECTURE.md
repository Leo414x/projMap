# projMap 功能说明

## 项目定位

projMap 是一个项目记忆图谱工具。它从项目文档（MD、代码注释等）中自动抽取决策、约束、风险、配置等结构化节点，存入知识图谱数据库，然后通过 LLM 驱动的报告层生成可读的项目简报和搜索结果。

解决的核心问题：项目文档中的关键决策和约束散落在各处，随着项目演进逐渐丢失上下文。projMap 把这些信息抽取出来，让任何人（或 AI）能快速了解项目当前状态、不可触碰的约束、关键决策和活跃风险。

---

## 功能清单

### 1. 初始化 `projmap init`

在项目目录下创建 `.projmap/` 配置目录和 DuckDB 数据库。

### 2. 文件扫描 `projmap scan`

扫描项目目录，发现新增、变更、未变更的文件。支持 `.gitignore` 风格的忽略规则。

### 3. 增量重建 `projmap rebuild`

扫描变更文件 → 分块 → LLM 抽取 → 写入 DuckDB。只处理 new/changed 文件，跳过未变更文件。

### 4. 外部抽取 `projmap prepare-extraction` / `projmap import-extraction`

不需要 API Key 的抽取方式：
- `prepare-extraction` 生成任务文件（含 prompt + 文档内容）
- 用户将任务文件交给任意 LLM 处理
- `import-extraction` 导入 LLM 结果并写入数据库

### 5. 项目简报 `projmap brief`

LLM 驱动的项目状态总览。输出结构：

```
1. Current Status      — 当前项目状态
2. Do-not-cross Constraints — 不可违反的约束
3. Key Decisions       — 关键决策
4. Active Risks        — 活跃风险
5. Evidence Sources    — 证据来源文件
6. Related Groups      — LLM 自动分组
7. Detailed Items      — 完整节点列表
```

### 6. 搜索查询 `projmap query <关键词>`

LLM 驱动的搜索结果页。输出结构：

```
1. Best Matches    — 最匹配的结果（含 match_reason）
2. Related Groups  — 相关分组
3. Detailed Matches — 完整匹配列表
```

### 7. Brief 外部模式 `projmap prepare-brief` / `projmap import-brief`

不需要 API Key 的报告方式：
- `prepare-brief` 生成 enrichment 任务文件
- 用户将任务文件交给任意 LLM 处理
- `import-brief` 导入结果并缓存

### 8. AI 上下文 `projmap context`

输出编码代理可用的上下文摘要（约束表、决策表等）。

### 9. 覆盖诊断 `projmap doctor`

检查节点覆盖率：有源文件的比率、有证据的比率、时间置信度分布等。

### 10. 旧数据迁移 `projmap migrate`

将旧 schema 节点迁移到 v5 schema（补充 project/version/module 等字段）。

---

## 实现方式

### 数据流

```
项目文档
  ↓ projmap scan（文件发现 + hash 比对）
  ↓ projmap rebuild（增量：只处理变更文件）
变更文件
  ↓ chunker.py（按字符数分块，保留 heading 路径）
文档块
  ↓ extractor.py（LLM 抽取 / 外部抽取）
JSON 节点 + 边
  ↓ duckdb_store.py（去重、写入）
DuckDB 知识图谱
  ↓ llm_enricher.py（LLL 批量 enrichment）
Enriched 节点（display_title, group, status, priority, summary）
  ↓ brief_builder.py（组装 ProjectBrief）
  ↓ render_markdown.py（Markdown 输出）
终端 / AI 代理
```

### LLM 使用方式

系统中有两个 LLM 调用点，每个都支持 API 模式和 External 模式：

| 阶段 | API 模式 | External 模式 |
|---|---|---|
| 抽取（extraction） | `rebuild` 时直接调 Anthropic API | `prepare-extraction` → 用户跑 LLM → `import-extraction` |
| 报告（report） | `brief`/`query` 时直接调 API | `prepare-brief` → 用户跑 LLM → `import-brief` |

### 节点类型

| 类型 | 含义 |
|---|---|
| decision | 具体选择、已批准方案、冻结方向、"不允许"边界 |
| constraint | 规则、限制、不可协商的要求 |
| risk | 已知风险、阻塞项、失败模式 |
| config | 参数、阈值、设置 |
| assumption | 项目依赖的信念或条件 |
| version | 命名版本、里程碑、冻结基线 |
| evaluation_result | 指标结果、回测结果 |
| implementation_fact | 当前实现细节 |
| process_rule | 工作流规则、步骤顺序 |
| open_question | 未解决的问题 |

### 边关系类型

depends-on, conflicts-with, supersedes, traces-back-to, mitigates, implements, affects, supports, limits

### 存储层

- **DuckDB**（嵌入式分析数据库）：存储节点、边、抽取记录、文件追踪
- **JSON 文件缓存**：文件 hash 比对，用于增量扫描
- **enrichment_cache.json**：LLM enrichment 结果缓存

### Report Layer 设计原则

1. **LLM 驱动，无硬编码规则**：所有 display_title、group、status、priority 由 LLM 从内容推断
2. **两种模式**：API 直调（有 Key 时）和 External（无 Key 时）
3. **结果缓存**：API 调用结果自动缓存，避免重复调用
4. **结构化输出**：Brief（项目总览）和 Query Results（搜索结果页）两种视图

---

## 目录结构

```
projmap/
├── cli.py              # CLI 命令（Typer）
├── api.py              # 稳定内部 API 层
├── config.py           # 配置读写
├── schemas.py          # Pydantic 数据模型
├── scanner.py          # 文件扫描
├── chunker.py          # 文本分块
├── extractor.py        # LLM 抽取
├── resolvers.py        # 分类解析 + 格式化
├── viewmodel.py        # ViewModel 构建
│
├── storage/            # 数据持久化
│   ├── duckdb_store.py # DuckDB CRUD
│   └── cache.py        # 文件 hash 缓存
│
├── report/             # Report Layer（LLM 驱动）
│   ├── prompts.py      # LLM prompt 定义
│   ├── llm_enricher.py # LLM 调用 + external 模式
│   ├── brief_builder.py # Brief 结构组装
│   ├── render_markdown.py # Markdown 渲染
│   ├── grouping.py     # 节点分组
│   ├── evidence_builder.py # 证据格式化
│   └── source_resolver.py  # 来源解析
│
├── templates/          # 模板文件
│   └── report.html.j2  # HTML 报告模板
│
└── intelligence/       # 智能分析（预留）
```
