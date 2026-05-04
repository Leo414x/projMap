# projmap/storage/ — 数据持久化

DuckDB 存储层 + 文件 hash 缓存。

## 文件

| 文件 | 职责 |
|---|---|
| `__init__.py` | 包初始化（空） |
| `duckdb_store.py` | DuckDB 存储层。表创建、节点/边/抽取记录的 CRUD、批量查询。所有 SQL 在此封装 |
| `cache.py` | 文件 hash 缓存。JSON 文件存储 file_path → hash 映射，用于增量扫描判断文件是否变更 |
