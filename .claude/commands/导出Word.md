---
description: 将文献综述和分析报告导出为 Word (DOCX) 格式
allowed-tools: mcp__cli-anything-wps__*, mcp__wps-editor__*, Read, Write, Bash, Glob
---

请将当前产出的分析报告和文献综述导出为 Word 文档。

## 前提检查

1. 确认 `workspace/literature_review.md` 存在
2. 确认 `workspace/analysis/` 下有分析报告

## 导出内容

### 方案 A：仅导出文献综述

使用 cli-anything-wps 创建 Writer 文档：
1. `mcp__cli-anything-wps__wps_document_new(doc_type="writer", name="文献综述")`
2. 读取 `workspace/literature_review.md` 内容
3. 按章节逐段添加到文档：
   - 标题 → `wps_writer_add_heading`
   - 正文 → `wps_writer_add_paragraph`
   - 表格 → `wps_writer_add_table`
4. `mcp__cli-anything-wps__wps_export_render(output_path="workspace/literature_review.docx", preset="docx")`

### 方案 B：导出完整分析报告包

除了文献综述，还包括：
- 11 个维度分析报告
- 实证方法论分析报告（如有）
- 论文写作方案（如有）

导出路径：`workspace/export/`

## 操作步骤

1. 列出 `workspace/analysis/` 中的所有 MD 文件
2. 对每个文件创建对应的 Word 文档
3. 使用 `wps_writer_add_heading` 添加章节标题
4. 使用 `wps_writer_add_paragraph` 添加正文
5. 使用 `wps_writer_add_list` 处理列表
6. 导出为 DOCX

## 报告结果

向用户展示：
- 导出的文件路径
- 文档页数/字数估算
