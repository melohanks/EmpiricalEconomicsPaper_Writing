# 全流程经济学实证论文写作系统

> 从论文获取到最终定稿的完整经济学实证论文 AI 辅助写作流水线。
> **不是 AI 代写——是 AI 辅助的结构化研究工具。**
> 每条结论都可追溯到来源论文的具体分析维度。

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

---

## 目录

- [核心能力](#核心能力)
- [完整工作流](#完整工作流)
- [外部工具与插件](#外部工具与插件)
- [安装](#安装)
- [快速开始](#快速开始)
- [命令参考](#命令参考)
- [项目架构](#项目架构)
- [配置](#配置)
- [FAQ](#faq)

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **11 维度结构化分析** | 每篇论文被拆解为 11 个计量经济学专用维度（理论框架/识别策略/模型设定/机制分析...），每个维度有独立 Prompt 和强类型 Schema |
| **跨论文对比矩阵** | 自动生成逐维度对比表，提取共性模式、差异分歧、共识空缺 |
| **跨集群桥梁发现** | 在看似无关的文献集群之间发现深层理论连接，产出理论迁移式创新题目 |
| **全链路溯源追踪** | 蓝图中每个要素（假设/变量/方法/机制）记录完整来源链——来自哪篇论文的哪个分析维度 |
| **三段式结构化写作** | 蓝图约束 → 逐节撰写（5 节独立 Prompt）→ 三级一致性交叉审查 → 修正定稿 |
| **多格式导出** | Markdown → LaTeX → PDF / DOCX / PPTX（组会汇报） |

## 完整工作流

```
                           外部工具集成
                               │
┌─ 阶段〇：论文获取 ───────────┼─────────────────────────────┐
│  Zotero MCP 搜索/导入       │  Zotero 本地库              │
│  提取元数据+PDF全文          │  zotero_extract.py          │
│  → workspace/papers/        │                             │
└─────────────────────────────┼─────────────────────────────┘
                              │
┌─ 阶段一+二：文献综述分析 ────┼─────────────────────────────┐
│  Step A: 每篇论文11維度分析  │  Anthropic/OpenAI LLM       │
│  Step B: 跨论文对比矩阵      │  humanizer-zh (去AI味)      │
│  Step C: 完整文献综述        │                             │
│  → workspace/analysis/      │                             │
└─────────────────────────────┼─────────────────────────────┘
                              │
┌─ 阶段三：实证方法论分析 ─────┼─────────────────────────────┐
│  四维度: 假设/方法/变量/结果 │  Anthropic/OpenAI LLM       │
│  → workspace/analysis/<论文>/empirical.*  │               │
└─────────────────────────────┼─────────────────────────────┘
                              │
┌─ Step 0: 跨集群桥梁发现 ────┼─────────────────────────────┐
│  理论统合/机制迁移/方法互鉴  │  LLM 5维分析框架            │
│  → 创新题目候选（排序）      │                             │
└─────────────────────────────┼─────────────────────────────┘
                              │
┌─ 阶段四：论文写作 ──────────┼─────────────────────────────┐
│  Step 1: 创新选题           │  Anthropic/OpenAI LLM       │
│  Step 2: 假设推导           │                             │
│  Step 3: 模型推荐           │                             │
│  Step 4: 变量选取           │                             │
│  Step 5: 结构化蓝图         │                             │
│  Step 6a-6e: 逐节撰写       │                             │
│  Step 7: 三级一致性审查     │                             │
│  Step 8: 修正定稿           │                             │
│  → workspace/writing/       │                             │
└─────────────────────────────┼─────────────────────────────┘
                              │
┌─ 阶段五：实证回归 ──────────┼─────────────────────────────┐
│  数据检查 → .do文件 → 执行  │  Stata MCP                  │
│  → 结果回收 + 解读          │  regression_lib (Python)    │
└─────────────────────────────┼─────────────────────────────┘
                              │
┌─ 阶段六：导出与演示 ────────┼─────────────────────────────┐
│  Word 导出 (DOCX)           │  cli-anything-wps MCP       │
│  LaTeX 编译 (PDF)           │  xelatex                    │
│  组会 PPT 生成              │  ppt-master                 │
└─────────────────────────────┴─────────────────────────────┘
```

---

## 外部工具与插件

系统依赖以下外部工具。按工作流阶段说明每个工具的**作用**、**安装方式**和**使用场景**。

### 1. LLM 后端（必需）

**作用**：驱动所有分析、写作、审查步骤的 AI 推理。

| 后端 | 推荐场景 | 月费 |
|------|---------|------|
| **DeepSeek API** | 推荐——性价比高，中文能力强，兼容 Anthropic 格式 | ~¥10-50 |
| **Anthropic 官方** | Claude 模型，推理能力最强 | ~$20-200 |
| **OpenAI / 兼容** | GPT-4o / 通义千问 / 等 | 按用量 |

**安装**：

```bash
# Python SDK
pip install anthropic>=0.30.0 openai>=1.0.0

# 配置 API Key（三选一）
python scripts/config_wizard.py           # 交互式向导
python scripts/config_wizard.py --quick   # DeepSeek 快速配置
cp .env.example .env && vim .env         # 手动编辑
```

**认证方式**：API Key 保存在本地 `.env` 文件中（已在 `.gitignore` 中排除）。

---

### 2. Zotero + zotero-mcp（论文获取，推荐）

**作用**：
- 从 Zotero 本地/云端库搜索论文
- 通过 DOI 自动导入论文元数据
- 提取 PDF 全文文本（用于 LLM 分析）
- 提取论文的附件、标签、笔记

**安装**：

```bash
# 1. 安装 Zotero（桌面端）
# 下载: https://www.zotero.org/download/

# 2. 安装 Better BibTeX 插件（可选，用于引用键管理）
# https://retorque.re/zotero-better-bibtex/

# 3. 获取 Zotero API Key（云端模式需要）
# https://www.zotero.org/settings/keys → "Create new private key"

# 4. 安装 zotero-mcp
pip install zotero-mcp-server
# 或: pip install zotero-mcp-server[pdf]   (含 PDF 全文提取依赖)
# 或: pip install zotero-mcp-server[semantic] (含语义搜索)
```

**配置**：

编辑 `.mcp.json`（从 `.mcp.json.example` 复制）：

```json
{
  "mcpServers": {
    "zotero": {
      "command": "zotero-mcp",
      "env": {
        "ZOTERO_LOCAL": "false",
        "ZOTERO_API_KEY": "你的Zotero_API_Key",
        "ZOTERO_LIBRARY_ID": "你的Library_ID"
      }
    }
  }
}
```

**使用**：在 Claude Code 中运行 `/论文获取 智慧城市 试点`。

**备选方案**（不使用 Zotero）：直接将论文元数据 JSON 放入 `workspace/papers/metadata.json`。

---

### 3. Stata MCP（实证回归）

**作用**：
- 在 Stata 中执行 `.do` 文件
- 返回回归结果和日志
- 支持多 session 并行执行（同时跑多个模型）

**安装**：

```bash
# 1. 安装 Stata 17+（需正版授权）
# https://www.stata.com/

# 2. 安装 Stata MCP 插件（VSCode 扩展）
# 在 VSCode 中搜索 "stata-mcp" 并安装
# 或手动安装: pip install stata-mcp-server
```

**配置**：

编辑 `.mcp.json`（从 `.mcp.json.example` 复制）：

```json
{
  "mcpServers": {
    "stata-mcp": {
      "command": "python",
      "args": ["<STATA_MCP_PATH>/.venv/Lib/site-packages/stata_mcp_server.py"]
    }
  }
}
```

**使用**：在 Claude Code 中运行 `/实证回归`，系统自动生成 `.do` 文件 → 执行 → 回收结果。

**备选方案**（不使用 Stata）：使用 `scripts/regression_lib/` 中的 Python 回归模块（statsmodels/linearmodels）。

---

### 4. WPS Office MCP（文档导出）

**作用**：
- 创建/编辑/导出 Word 文档 (DOCX)
- 创建/编辑 Excel 表格 (XLSX)
- 创建/导出 PDF
- 格式化文档（字体、表格、页码）

系统集成了两个互补的 WPS MCP：

| MCP | 用途 | 安装 |
|-----|------|------|
| **cli-anything-wps** | Writer/Calc 文档创建、导出 DOCX/PDF | `pip install cli-anything-wps` |
| **wps-editor** | 更细粒度的文档编辑（样式、表格、图片） | 独立安装包 |

**安装**：

```bash
# cli-anything-wps: 文档级操作（创建、导出、预设应用）
pip install cli-anything-wps

# wps-editor: 段落/单元格级操作（读、写、样式设置）
# 从 https://github.com/... 克隆并安装
git clone <wps-editor-repo-url>
pip install -e wps-editor-mcp/
```

**配置**：

编辑 `.mcp.json`（从 `.mcp.json.example` 复制）：

```json
{
  "mcpServers": {
    "cli-anything-wps": {
      "command": "python",
      "args": ["<CLI_ANYTHING_WPS_INSTALL_PATH>/mcp_server.py"]
    },
    "wps-editor": {
      "command": "python",
      "args": ["<WPS_EDITOR_INSTALL_PATH>/server.py"]
    }
  }
}
```

**使用**：在 Claude Code 中运行 `/导出Word`。

**备选方案**（不使用 WPS）：系统也可通过 `scripts/md_to_docx.py` 使用 python-docx 直接生成 DOCX。

---

### 5. ppt-master（组会汇报 PPT）

**作用**：
- 将文献综述/分析数据转化为专业学术 PPT
- 支持多种模板（学术答辩/商务/现代等）
- 自动生成 SVG 图表和 PPTX 动画
- 生成演讲稿

**已内置于** `.claude/skills/ppt-master/`，无需额外安装。

**配置**（可选——使用云端图像生成）：

```bash
# 复制环境配置
cp .claude/skills/ppt-master/.env.example .claude/skills/ppt-master/.env
# 编辑 .env，填入图像生成 API Key (OpenAI/Stability/BFL 等)
```

**使用**：在 Claude Code 中运行 `/组会汇报幻灯片`。

---

### 6. humanizer-zh（去 AI 味，可选）

**作用**：
- 检测并修复 AI 写作痕迹（夸大象征、宣传性语言、过度连接词等）
- 使分析报告读起来更像人类学术写作

**已内置于 Claude Code skill 系统**，无独立安装步骤。

**使用**：在 Claude Code 中运行 `/humanizer-zh`，或在 `/文献综述` 后自动执行。

---

### 7. ChromaDB（语义搜索，可选）

**作用**：
- 为所有分析文件构建向量索引
- 支持语义搜索（"DID 方法的标准误聚类层级"）

**安装**：

```bash
pip install chromadb
```

**使用**：安装后，系统在构建知识索引时自动启用向量存储。可通过 `KnowledgeIndex.semantic_search()` 查询。

---

### 工具依赖总览

```
必需:
  ├── Python 3.10+
  ├── anthropic + openai SDK
  └── .env 配置 (LLM API Key)

推荐:
  ├── Zotero 桌面端 + zotero-mcp        → 论文获取与全文提取
  ├── Stata 17+ + stata-mcp             → 回归执行
  └── cli-anything-wps + WPS Office     → 文档导出

可选:
  ├── wps-editor MCP                    → 精细化文档编辑
  ├── humanizer-zh                      → 去 AI 写作痕迹
  ├── ChromaDB                          → 语义搜索
  └── ppt-master 图像生成 API           → PPT 中的 AI 图表
```

---

## 安装

### 最小安装（仅分析+写作，不含外部工具）

```bash
git clone https://github.com/melohanks/EmpiricalEconomicsPaper_Writing.git
cd EmpiricalEconomicsPaper_Writing

pip install -r requirements.txt

# 配置 LLM
python scripts/config_wizard.py
```

此时即可运行文献分析和论文写作。

### 完整安装（含全部外部工具）

```bash
# 1. 基础依赖
git clone https://github.com/melohanks/EmpiricalEconomicsPaper_Writing.git
cd EmpiricalEconomicsPaper_Writing
pip install -r requirements.txt

# 2. LLM 配置
python scripts/config_wizard.py

# 3. Zotero（论文获取）
# 安装 Zotero 桌面端: https://www.zotero.org/download/
pip install zotero-mcp-server[pdf]
cp .mcp.json.example .mcp.json
# 编辑 .mcp.json 填入 Zotero API Key

# 4. WPS（文档导出）
pip install cli-anything-wps
# 编辑 .mcp.json 填入 wps-editor 和 cli-anything-wps 路径

# 5. Stata（实证回归）
# 安装 Stata 17+
# 在 VSCode 中安装 stata-mcp 扩展
# 编辑 .mcp.json 填入 stata-mcp 路径

# 6. 可选
pip install chromadb          # 语义搜索
```

---

## 快速开始

```bash
# 在 Claude Code 中运行：

# 1. 配置 LLM API（仅首次）
/配置LLM

# 2. 获取论文
/论文获取 智慧城市 试点 准自然实验

# 3. 运行分析
/文献综述          # 11维度分析 + 跨论文对比 + 文献综述
/实证分析          # 四维实证方法论分析

# 4. 论文写作（创新选题 → 蓝图 → 逐节撰写 → 审查）
/论文写作

# 5. 导出
/导出Word          # 导出 DOCX
/组会汇报幻灯片    # 生成学术 PPTX

# 6. 下一篇论文
/初始化新论文      # 归档 + 重置工作区
```

完整 Python CLI 用法见[命令参考](#命令参考)。

---

## 命令参考

### Claude Code 快捷命令

| 命令 | 阶段 | 功能 | 依赖的外部工具 |
|------|------|------|--------------|
| `/配置LLM` | — | 配置 LLM API Key | — |
| `/论文获取` | 〇 | Zotero 搜索/导入论文 | Zotero MCP |
| `/文献综述` | 一+二 | 11维度分析 + 跨论文对比 + 综述 | LLM + humanizer-zh |
| `/实证分析` | 三 | 四维实证方法论分析 | LLM |
| `/论文写作` | 四 | 选题→假设→模型→变量→蓝图→逐节撰写→审查 | LLM |
| `/实证回归` | 五 | 数据检查 → Stata .do → 执行 → 结果回收 | Stata MCP / regression_lib |
| `/组会汇报幻灯片` | 六 | 生成学术 PPTX + 演讲稿 | ppt-master |
| `/导出Word` | 六 | 文献综述/论文导出为 DOCX | cli-anything-wps MCP |
| `/初始化新论文` | — | 归档当前产出 + 重置工作区 | — |

### Python CLI

```bash
# 论文获取
python scripts/zotero_extract.py --search "关键词" --output workspace/papers/metadata.json

# 文献综述（完整流水线）
python scripts/run_pipeline.py --backend anthropic

# 文献综述（指定维度）
python scripts/run_review.py --backend anthropic --sections 1,6,11

# 实证分析
python scripts/run_empirical.py --backend anthropic

# 论文写作（分步）
python scripts/run_write.py --backend anthropic --step topic
python scripts/run_write.py --backend anthropic --step hypothesis --input "题目信息"
python scripts/run_write.py --backend anthropic --step model --input "题目+假设"
python scripts/run_write.py --backend anthropic --step variables --input "题目+模型"
python scripts/run_write.py --backend anthropic --step full --input "全部材料"

# 计量回归
python scripts/run_regression.py --model panel_fe --data data.csv --y Y --x X
python scripts/run_regression.py --blueprint paper_blueprint.md --data data.csv

# 知识索引
python skills/knowledge_index.py --build   # 从 workspace 构建索引
python skills/knowledge_index.py --stats   # 查看索引统计

# 配置
python scripts/config_wizard.py            # 交互式配置
python scripts/config_wizard.py --check    # 检查当前配置
```

---

## 项目架构

```
agent/core.py                       # 主编排引擎
skills/                             # ★ 核心技能引擎
├── schemas.py                      # 30+ 统一数据Schema
├── llm_client.py                   # LLM 调用 + structured_output + 自动重试
├── literature_analyzer.py          # 11维度单篇深度分析
├── cross_paper_analyzer.py         # 跨论文对比矩阵
├── empirical_analyzer.py           # 实证方法论四维分析
├── cross_cluster_bridge.py         # ★ 跨集群桥梁发现
├── paper_writer.py                 # 论文写作编排
├── section_writer.py               # ★ 蓝图驱动逐节写作引擎
├── consistency_auditor.py          # ★ 三级一致性交叉审查(L0-L3)
├── quality_gate.py                 # 质量门控 + 自动重试
├── knowledge_index.py              # SQLite + 倒排索引 + ChromaDB
└── workspace_dal.py                # 统一数据访问层
scripts/                            # CLI 入口 + 工具
├── run_pipeline.py                 # 一键流水线
├── run_review.py                   # 文献综述
├── run_empirical.py                # 实证分析
├── run_write.py                    # 论文写作
├── run_regression.py               # 计量回归
├── config_wizard.py                # ★ API 配置向导
├── zotero_extract.py               # Zotero 本地库提取
├── regression_lib/                 # 标准化计量代码库(8个模型)
└── stata_lib/                      # Stata .do 模板
references/prompts/                 # 20+ Prompt 模板
├── sections_single/                # 11 维度分析 Prompt
├── section_writing/                # 5 节分节写作 Prompt + 蓝图 Prompt
├── bridge_detection.txt            # 5 维跨集群桥梁分析框架
├── topic_selection.txt             # 双路径创新选题 Prompt
├── hypothesis.txt                  # 假设推导 Prompt
├── empirical_analysis.txt          # 实证分析 Prompt
└── ...
```

---

## 配置

### LLM API（必需）

```bash
python scripts/config_wizard.py       # 交互式向导
python scripts/config_wizard.py --quick  # DeepSeek 快速配置
```

支持的 API 后端：

| 后端 | 环境变量 | 说明 |
|------|---------|------|
| DeepSeek (Anthropic 格式) | `ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` | 推荐 |
| Anthropic 官方 | `ANTHROPIC_API_KEY` | Claude 模型 |
| OpenAI 兼容 | `OPENAI_API_KEY` + `OPENAI_BASE_URL` | GPT/DeepSeek/通义千问 |

### MCP 服务（可选）

```bash
cp .mcp.json.example .mcp.json
# 编辑 .mcp.json，填入各 MCP 的安装路径和 API Key
```

### Zotero（可选）

获取 Zotero API Key：https://www.zotero.org/settings/keys → "Create new private key"

### 环境变量参考

| 变量 | 必需 | 说明 |
|------|------|------|
| `LLM_BACKEND` | 是 | `anthropic` 或 `openai` |
| `ANTHROPIC_API_KEY` | 是* | DeepSeek 或 Anthropic API Key |
| `ANTHROPIC_BASE_URL` | 否 | 默认 `https://api.deepseek.com/anthropic` |
| `ANTHROPIC_MODEL` | 否 | 默认 `deepseek-v4-pro` |
| `OPENAI_API_KEY` | 是* | OpenAI 兼容 API Key |
| `ZOTERO_API_KEY` | 否 | Zotero Web API Key |
| `ZOTERO_LIBRARY_ID` | 否 | Zotero 库 ID |

> *取决于 `LLM_BACKEND` 的选择

---

## FAQ

### Q: 不使用 Zotero 可以用吗？

可以。将论文元数据手动放入 `workspace/papers/metadata.json`（格式：`[{"title": "...", "authors": "...", "abstract": "..."}]`），然后直接运行 `/文献综述`。

### Q: 不使用 Stata 可以跑回归吗？

可以。系统内置 Python 回归库 `scripts/regression_lib/`，支持双向固定效应、DID、IV-2SLS、RDD、中介效应等 8 个模型（基于 statsmodels/linearmodels）。

### Q: 不用 WPS 可以导出 Word 吗？

可以。运行 `python scripts/md_to_docx.py` 使用 python-docx 生成 DOCX。

### Q: 最小安装只需要什么？

```bash
pip install anthropic openai pandas
python scripts/config_wizard.py
```

然后就可以用 `/文献综述` 和 `/论文写作`。

### Q: API Key 安全吗？

- `.env` 文件在 `.gitignore` 中，不会被提交
- `.mcp.json` 在 `.gitignore` 中，不会被提交
- `.claude/settings.local.json` 在 `.gitignore` 中，不会被提交
- 系统只通过环境变量读取 Key，不会硬编码在代码中

### Q: 系统产出保存在哪里？

全部在 `workspace/` 目录中（已在 `.gitignore` 中排除）：
- `workspace/analysis/<论文>/` — 每篇论文的 11 维分析
- `workspace/writing/` — 论文写作产出
- `workspace/regression/` — 回归结果
- `workspace/projects/<项目>/` — 已完成项目的归档

---

## License

MIT
