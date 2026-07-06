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
┌─ 阶段〇：论文获取 ─────────────┼───────────────────────────┐
│  Zotero MCP 搜索/导入         │  Zotero 本地库            │
│  提取元数据+PDF全文            │  zotero_extract.py        │
│  → workspace/papers/          │                           │
└───────────────────────────────┼───────────────────────────┘
                                │
┌─ 阶段一+二：文献综述分析 ──────┼───────────────────────────┐
│  Step A: 每篇论文11维度分析    │  Anthropic/OpenAI LLM     │
│  Step B: 跨论文对比矩阵        │  humanizer-zh (去AI味)    │
│  Step C: 完整文献综述          │                           │
│  → workspace/analysis/        │                           │
└───────────────────────────────┼───────────────────────────┘
                                │
┌─ 阶段三：实证方法论分析 ───────┼───────────────────────────┐
│  四维度: 假设/方法/变量/结果   │  Anthropic/OpenAI LLM     │
│  → workspace/analysis/<论文>/empirical.* │                │
└───────────────────────────────┼───────────────────────────┘
                                │
┌─ Step 0: 跨集群桥梁发现 ──────┼───────────────────────────┐
│  理论统合/机制迁移/方法互鉴    │  LLM 5维分析框架          │
│  → 创新题目候选（排序）        │                           │
└───────────────────────────────┼───────────────────────────┘
                                │
┌─ 论文写作 ────────────────────┼───────────────────────────┐
│  Step 1: 创新选题             │  Anthropic/OpenAI LLM     │
│  Step 2: 假设推导             │                           │
│  Step 3: 模型推荐             │                           │
│  Step 4: 变量选取             │                           │
│                               │                           │
│  Step 4.5: ★ 数据获取         │  数据源 API / CSMAR / 手动 │
│                               │                           │
│  Step 5: ★ 实证回归 (插入)    │  Stata MCP / regression_lib│
│  → 回归结果                   │                           │
│                               │                           │
│  Step 4.6: ★ 回归诊断与决策   │  RegressionDiagnosisEngine│
│  ┌────────────────────────┐   │                           │
│  │ 全部支撑 → Step 6 蓝图  │   │                           │
│  │ 部分支撑 → Step 2'修正 │   │                           │
│  │ 符号相反 → Step 2'重推 │   │                           │
│  │ 不支撑   → 诊断原因回退 │   │                           │
│  │ 完全不支撑 → Step 0 重选│   │                           │
│  └────────────────────────┘   │                           │
│                               │                           │
│  Step 6: 结构化蓝图 (基于结果) │  Anthropic/OpenAI LLM     │
│  Step 7a-7e: 逐节撰写         │                           │
│  Step 8: 三级一致性审查       │                           │
│  Step 9: 修正定稿             │                           │
│  → workspace/writing/         │                           │
└───────────────────────────────┼───────────────────────────┘
                                │
┌─ 导出与演示 ──────────────────┼───────────────────────────┐
│  Word 导出 (DOCX)             │  cli-anything-wps MCP     │
│  LaTeX 编译 (PDF)             │  xelatex                  │
│  组会 PPT 生成                │  ppt-master               │
└───────────────────────────────┴───────────────────────────┘
```

### 回归诊断决策树（Step 4.6 的核心逻辑）

这是系统最关键的设计：**在蓝图生成之前，先让数据告诉你真相。**

```
回归结果
    │
    ├── ✅ 全部假设支撑
    │   └── → PROCEED: 直接生成蓝图，进入逐节撰写
    │       writable_findings: 全部显著发现 + 强证据
    │
    ├── ⚠️ 大部分支撑 (核心假设成立，部分机制不显著)
    │   └── → PROCEED: 保留已支撑的，不显著机制作为"局限性"写入
    │       writable_findings: 核心发现(强) + 不显著机制(弱, 写入5.4)
    │
    ├── ⚠️ 符号相反 (主效应显著但方向与预期相反)
    │   └── → REVISE_HYPOTHESES: 回退 Step 2，重新理论推导
    │       "发现反向效应"往往比"证实预期"更有学术价值
    │       writable_findings: 反向结果(强) + 新理论解释
    │
    ├── ❌ 大部分不支撑 (主效应不显著)
    │   ├── 数据问题 (样本量/异常值/测度)
    │   │   └── → ACQUIRE_DATA: 回退 Step 4.5，增加/清洗数据
    │   ├── 模型误设 (遗漏变量/FE/函数形式)
    │   │   └── → REVISE_MODEL: 回退 Step 3，调整模型
    │   └── 假设错误 (理论不适用)
    │       └── → REVISE_HYPOTHESES: 回退 Step 2
    │
    └── ❌ 完全不支撑 (全部不显著 + 诊断无解)
        └── → RECONSIDER_TOPIC: 回退 Step 0
            可考虑将"不存在因果"本身作为贡献
```

**核心原则**：

1. **不显著也是发现** — "未发现证据支持 H2"是有价值的科学信息
2. **符号相反是更大发现** — 如果你的数据说 X 抑制了 Y，而文献都说 X 促进了 Y，你可能发现了一个新的调节机制
3. **数据驱动写作方向** — 论文写的是你发现了什么，不是你期望发现什么
4. **可写作内容总是存在** — 即使全部不显著，也可以讨论"为什么这个看似合理的假设不成立"

---

## 外部工具与插件

系统依赖以下外部工具。按工作流阶段说明每个工具的**作用**、**安装方式**和**使用场景**。

### 1. LLM 后端（必需）

**作用**：驱动所有分析、写作、审查步骤的 AI 推理。

| 后端 | 推荐场景 | 月费 | 获取 |
|------|---------|------|------|
| **DeepSeek API** | 推荐——性价比高，中文能力强 | ~¥10-50 | [platform.deepseek.com](https://platform.deepseek.com/) |
| **Anthropic 官方** | Claude 模型，推理能力最强 | ~$20-200 | [console.anthropic.com](https://console.anthropic.com/) |
| **OpenAI / 兼容** | GPT-4o / 通义千问 | 按用量 | [platform.openai.com](https://platform.openai.com/) |

**安装**：

```bash
pip install anthropic>=0.30.0 openai>=1.0.0
python scripts/config_wizard.py           # 交互式配置
```

**认证方式**：API Key 保存在本地 `.env` 文件中（已在 `.gitignore` 中排除）。

---

### 2. Zotero + zotero-mcp（论文获取，推荐）

> **GitHub**: [54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp) — 全功能 Zotero MCP Server（语义搜索 / PDF 全文 / SciTe / 标注）

**作用**：
- 从 Zotero 本地/云端库搜索论文
- 通过 DOI 自动导入论文元数据
- 提取 PDF 全文文本（用于 LLM 分析）
- 语义搜索（ChromaDB + embeddings）
- PDF 页面布局分析 / 标注管理

**安装**：

```bash
# 1. 安装 Zotero 桌面端
# 下载: https://www.zotero.org/download/

# 2. 获取 Zotero API Key（云端模式）
# https://www.zotero.org/settings/keys → "Create new private key"

# 3. 安装 zotero-mcp
pip install zotero-mcp-server
# 完整安装（含 PDF + 语义搜索）:
pip install zotero-mcp-server[pdf,semantic]
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

**使用**：在 Claude Code 中运行 `/论文获取 论文名称关键词`。

**备选方案**（不使用 Zotero）：直接将论文元数据 JSON 放入 `workspace/papers/metadata.json`。

---

### 3. Stata MCP（实证回归）

> **VSCode 扩展**: [deepecon.stata-mcp](https://marketplace.visualstudio.com/items?itemName=deepecon.stata-mcp) — Stata 与 MCP 的桥接扩展

**作用**：
- 在 Stata 中执行 `.do` 文件，返回结果和日志
- 支持多 session 并行执行

**安装**：

```bash
# 1. 安装 Stata 17+（需正版授权）
# https://www.stata.com/

# 2. 在 VSCode 扩展市场搜索 "stata-mcp" 并安装
# 或: pip install stata-mcp-server
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

> **GitHub**: [yb2460/harness-anything](https://github.com/yb2460/harness-anything) — 47 CLI 命令操控 WPS/Microsoft Office
> **跨平台版**: [yb2460/harness-anything-mac](https://github.com/yb2460/harness-anything-mac) — macOS/Linux 回退到 LibreOffice

**作用**：
- 创建/编辑/导出 Word 文档 (DOCX)、Excel (XLSX)、PDF
- 学术预设模板（academic/consultant/business/tech）
- 5 维度文档质量审查

**安装**：

```bash
pip install git+https://github.com/yb2460/cli-anything-wps.git
```

**备选方案**：`python scripts/md_to_docx.py`（纯 python-docx，无需 WPS）

---

### 5. ppt-master（组会汇报 PPT）

> **GitHub**: [yb2460/harness-anything](https://github.com/yb2460/harness-anything) — 内置 ppt-master 技能（SVG → PPTX 转换 / 学术模板 / AI 图表生成）

**已内置于** `.claude/skills/ppt-master/`。在 Claude Code 中运行 `/组会汇报幻灯片`。

**配置**（可选——使用云端图像生成）：

```bash
# 复制环境配置
cp .claude/skills/ppt-master/.env.example .claude/skills/ppt-master/.env
# 编辑 .env，填入图像生成 API Key (OpenAI/Stability/BFL 等)
```

**使用**：在 Claude Code 中运行 `/组会汇报幻灯片`。

---

### 6. humanizer-zh（去 AI 味，可选）

**已内置于 Claude Code skill 系统**。在 `/文献综述` 后自动执行。

### 7. ChromaDB（语义搜索，可选）

> **GitHub**: [chroma-core/chroma](https://github.com/chroma-core/chroma) — AI-native 开源向量数据库

```bash
pip install chromadb
```

---

### 工具依赖与 GitHub 链接总览

| 工具 | 作用 | 安装 | 仓库 |
|------|------|------|------|
| **DeepSeek API** | LLM 推理（推荐） | `pip install anthropic` | [platform.deepseek.com](https://platform.deepseek.com/) |
| **Anthropic API** | LLM 推理 | — | [console.anthropic.com](https://console.anthropic.com/) |
| **zotero-mcp** | 论文获取/全文提取 | `pip install zotero-mcp-server` | [54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp) |
| **Zotero 桌面端** | 文献管理 | [下载](https://www.zotero.org/download/) | [zotero/zotero](https://github.com/zotero/zotero) |
| **stata-mcp** | Stata 回归执行 | VSCode 扩展 | [deepecon.stata-mcp](https://marketplace.visualstudio.com/items?itemName=deepecon.stata-mcp) |
| **cli-anything-wps** | Word/PDF 导出 | `pip install git+https://github.com/yb2460/cli-anything-wps.git` | [yb2460/harness-anything](https://github.com/yb2460/harness-anything) |
| **ppt-master** | 组会 PPT 生成 | 内置 | [yb2460/harness-anything](https://github.com/yb2460/harness-anything) |
| **ChromaDB** | 语义搜索 | `pip install chromadb` | [chroma-core/chroma](https://github.com/chroma-core/chroma) |

```
必需:   Python 3.10+ + anthropic SDK + .env
推荐:   Zotero + zotero-mcp + Stata + cli-anything-wps
可选:   ChromaDB
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
/论文获取 论文名称 关键字 X Y

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
| `/论文写作` | 四 | 选题→假设→模型→变量→数据→回归→诊断→蓝图→逐节撰写→审查 | LLM + Stata/Python + 诊断引擎 |
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


### Q: 不用 WPS 可以导出 Word 吗？

可以。运行 `python scripts/md_to_docx.py` 使用 python-docx 生成 DOCX。

### Q: 最小安装只需要什么？

```bash
pip install anthropic openai pandas
python scripts/config_wizard.py
```

然后就可以用 `/文献综述` 和 `/论文写作`。


### Q: 系统产出保存在哪里？

全部在 `workspace/` 目录中（执行完命令会自动生成）：
- `workspace/analysis/<论文>/` — 每篇论文的 11 维分析
- `workspace/writing/` — 论文写作产出
- `workspace/regression/` — 回归结果
- `workspace/projects/<项目>/` — 已完成项目的归档

### Q: 数据是系统自动获取的吗？

**不是**。系统**不会**自动替你从数据库下载数据，但它会在变量选取完成后，帮你做好三件事：

**1. 告诉你需要哪些数据**

Step 4（变量选取）完成后，系统会生成一份变量清单：

```
被解释变量 Y: <你的被解释变量>
  → 测度: <系统根据已有文献推荐测度方式>
  → 数据来源建议: <系统根据变量类型匹配数据库>

核心解释变量 X: <你的核心解释变量>
  → 测度: <系统根据已有文献推荐测度方式>
  → 数据来源: <系统根据政策来源推荐>

控制变量: <系统根据文献频率统计推荐>
  → 数据来源: <匹配的数据库>
```

**2. 告诉你从哪个数据库获取**

系统内置了变量→数据源的映射表（`skills/data_handler.py`），会为每个变量推荐可用的数据库：

| 数据库 | 类型 | 典型变量 |
|--------|------|---------|
| **中国城市统计年鉴** | 公开 | GDP、人口、财政、教育、道路面积 |
| **CSMAR**（国泰安） | 付费订阅 | 上市公司财务、员工结构、研发投入 |
| **CNRDS** | 付费订阅 | 专利 IPC、绿色专利、数字化转型 |
| **EPS 数据平台** | 付费订阅 | 分行业就业/工资、城市面板全量指标 |
| **Wind**（万得） | 付费订阅 | 城市面板全部宏观指标、上市公司全部财务 |
| **AKShare** | 免费开源 | 城市面板宏观数据（GDP、财政、人口） |

**3. 帮你生成数据下载脚本**

系统会生成 `workspace/data/download_data.py`，包含各数据库的 API 调用框架：

```python
# 系统生成的数据获取脚本（示例）
import akshare as ak
# 城市GDP: ak.macro_china_city_gdp()
# 财政数据: ak.macro_china_city_fiscal()

# 填入你的 CSMAR API Key:
# CONFIG["csmar_api_key"] = "your-key"
```

**你需要做的**：

1. 有订阅的数据库 → 填入 API Key，运行脚本获取
2. 公开数据 → 直接运行脚本（AKShare 免费）
3. 手动整理的数据 → 放入 `workspace/data/panel_data.csv`

**数据格式要求**：最终需要一个面板 CSV 文件，包含 Y、X、控制变量、中介变量、分组变量、时间变量、个体 ID。系统在 Step 4.5 检查数据后进入 Step 5（回归）。

**常见场景**：

| 场景 | 数据来源 | 获取方式 |
|------|---------|---------|
| 城市面板（地级市） | 中国城市统计年鉴 + EPS | 手动整理或 EPS API |
| 上市公司面板 | CSMAR | CSMAR API 或本地数据库导出 |
| 专利数据 | CNRDS | CNRDS API |
| 微观调查（CFPS/CHARLS） | 公开申请 | 官网申请后下载 |
| 试点城市名单 | 政府公开 | 手动整理 CSV |

> **一句话总结**：系统告诉你"需要什么、从哪找、怎么下载"，但**数据本身需要你获取**。这是因为经济学实证数据大多来自付费数据库（CSMAR/CNRDS/EPS），系统无法绕过订阅墙。

---

## License

MIT
