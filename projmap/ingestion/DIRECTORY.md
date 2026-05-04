# projmap/ingestion/ — 数据摄入

文件扫描 → 文本分块 → LLM 抽取。从项目文档中提取结构化节点。

## 文件

| 文件 | 职责 |
|---|---|
| `__init__.py` | 包初始化 |
| `scanner.py` | 文件扫描。发现项目文件，计算 hash，判断 new / changed / unchanged。支持 `.gitignore` 风格忽略规则 |
| `chunker.py` | 文本分块。按字符数切分文档，保留 heading 路径和语义锚点，生成 ChunkRecord |
| `extractor.py` | LLM 抽取。Anthropic API 调用 + prompt 模板。从文档块抽取节点和边。Edge 解析（from_title/to_title → node_id） |
