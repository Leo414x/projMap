# projmap/display/ — 显示层

分类解析 + 格式化 + ViewModel 构建。服务 context / doctor 命令和旧输出格式。

## 文件

| 文件 | 职责 |
|---|---|
| `__init__.py` | 包初始化 |
| `resolvers.py` | 确定性解析器。模块标准化（CANONICAL_MODULES / MODULE_ALIASES）、项目/版本推断、时间标签、可见性判断、显示优先级、badge 生成、分类组合 |
| `formatters.py` | 显示格式化。TYPE_LABELS / STATUS_LABELS / STATUS_SEVERITY 常量 + format_type_label / format_module_label / format_status_label / format_source_label 等函数 |
| `viewmodel.py` | ViewModel 构建器。将 DB 行转为 RowViewModel，供 context / doctor 命令的旧 markdown 表格输出使用 |
