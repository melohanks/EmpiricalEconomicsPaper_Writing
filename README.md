# 全流程科研论文写作系统

> 从论文获取到最终定稿的完整经济学实证论文写作流水线。**不是 AI 代写——是 AI 辅助的结构化研究工具。**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 这是什么？

一个为经济学实证研究者设计的**全流程写作助手**。输入一批相关论文（通过 Zotero 或手动），系统自动完成：

```
论文获取 → 11维深度分析 → 跨论文对比 → 实证方法论提取
    ↓
跨集群桥梁发现 → 创新选题 → 假设推导 → 模型推荐 → 变量选取
    ↓
结构化蓝图 → 逐节撰写 → 一致性审查 → 修正定稿 → Word/LaTeX/PDF 导出
```

**核心理念**：把论文拆成结构化零件（11维度分析），在零件之间发现连接（跨集群桥梁），再基于有溯源标注的蓝图重新组装成逻辑自洽的新论文。

## 为什么不是"AI 代写"？

| 传统 AI 写作 | 本系统 |
|-------------|--------|
| 一次 Prompt → 一篇论文 | 9 步流水线，每步有质量门控 |
| 不知道结论从哪来 | 全链路溯源追踪（ProvenanceMap） |
| 只能做增量创新（换 Y） | 跨集群桥梁发现（理论迁移式创新） |
| 单次 LLM 调用 | 分节撰写 + 一致性交叉审查 |
| "看起来很对"但引用虚构 | 引用合同 + Level 1-3 自动审查 |

## 快速开始

### 1. 环境准备

```bash
# 克隆仓库
git clone https://github.com/yourusername/research-paper-workflow.git
cd research-paper-workflow

# 安装依赖
pip install -r requirements.txt

# 配置 LLM API（3 种方式任选）
python scripts/config_wizard.py           # 交互式配置向导
python scripts/config_wizard.py --quick   # 快速配置（DeepSeek）
cp .env.example .env && vim .env         # 手动配置
```

### 2. 获取论文

```bash
# 方式A：从 Zotero 提取（在 Claude Code 中）
/论文获取 智慧城市 试点 准自然实验

# 方式B：手动放入
# 将论文元数据 JSON 放入 workspace/papers/metadata.json
```

### 3. 运行分析流水线

```bash
# 在 Claude Code 中，按顺序运行：

/文献综述          # 11维度逐结构分析 + 跨论文对比 + 文献综述
/实证分析          # 四维实证方法论分析
/论文写作          # 创新选题 → 蓝图 → 逐节撰写 → 审查定稿
/组会汇报幻灯片    # 生成学术 PPTX
/导出Word          # 导出 DOCX
```

详细命令说明见[命令参考](#命令参考)。

## 架构

```
skills/                          # 核心技能引擎
├── schemas.py                   # ★ 全系统统一数据契约（30+ Schema）
├── llm_client.py                # LLM 统一调用 + structured_output
├── literature_analyzer.py       # 11维度单篇深度分析
├── cross_paper_analyzer.py      # 跨论文对比矩阵
├── empirical_analyzer.py        # 实证方法论四维分析
├── cross_cluster_bridge.py      # ★ 跨集群桥梁发现（理论迁移式创新）
├── paper_writer.py              # 论文写作（蓝图 + 分节撰写）
├── section_writer.py            # ★ 蓝图驱动的逐节写作引擎
├── consistency_auditor.py       # ★ 三级一致性交叉审查
├── quality_gate.py              # 质量门控 + 自动重试
├── knowledge_index.py           # SQLite + 倒排索引 + 向量存储
├── workspace_dal.py             # 统一数据访问层（缓存 + 增量扫描）
└── ...

agent/core.py                    # 主编排引擎
references/prompts/              # 20+ Prompt 模板（含分节写作）

workspace/                       # 产出目录（已 gitignore）
├── analysis/<论文>/             # 每篇论文的 11 维度分析
├── analysis/_cross_paper/       # 跨论文对比矩阵
├── writing/                     # 论文写作产出
├── projects/<项目>/             # 已完成项目的归档
└── knowledge_index.db           # 知识索引
```

## 核心创新

### 1. 11 维度结构化分析

每篇论文被拆解为 11 个计量经济学维度，每个维度有独立的分析 Prompt 和强类型的 JSON Schema：

| 维度 | 内容 | Schema |
|------|------|--------|
| 01 | 研究问题与动机 | `Section01Introduction` |
| 02 | 理论框架 | `Section02TheoreticalFramework` |
| 03 | 识别策略 | `Section03Identification` |
| 04 | 数据与变量 | `Section04DataVariables` |
| 05 | 实证方法与模型设定 | `Section05EmpiricalMethodology` |
| 06 | 基准结果 | `Section06BaselineResults` |
| 07 | 稳健性检验 | `Section07Robustness` |
| 08 | 机制分析 | `Section08Mechanism` |
| 09 | 异质性分析 | `Section09Heterogeneity` |
| 10 | 内生性处理 | `Section10Endogeneity` |
| 11 | 结论与政策含义 | `Section11Conclusion` |

### 2. 跨集群桥梁发现

在看似无关的文献集群之间发现深层理论连接，产出理论迁移式创新题目：

```
集群A: 智慧城市 (21篇) → 核心机制: 信息基建→降低信息不对称
集群B: 企业金融化 (4篇)  → 核心机制: 不确定性→预防性储蓄→金融化

桥梁理论: 信息不对称理论
新题目: 智慧城市建设的信息不对称缓解效应
        ——基于企业金融化抑制视角
```

### 3. 全链路溯源追踪

蓝图中每个要素（假设/变量/方法/机制）都记录完整来源链：

```json
{
  "H1": {
    "sources": [
      {"source_type": "bridge", "bridge_theory": "信息不对称理论"},
      {"source_type": "single_paper", "paper_title": "...", "section_key": "02"},
      {"source_type": "cross_paper", "cross_frequency": "17/21 篇"}
    ]
  }
}
```

分段撰写时 LLM 能精确知道"这个假设从哪来"、"为什么选这个方法"。

### 4. 三级一致性审查

| 级别 | 内容 | 方式 |
|------|------|------|
| L0 | 溯源链完整性 | 确定性规则 |
| L1 | 变量/引用/假设一致性 | 确定性规则 |
| L2 | 引用格式与完整性 | 文本匹配 |
| L3 | 节间语义一致性 | LLM 语义检查 |

## 命令参考

### 快捷命令（Claude Code）

| 命令 | 功能 |
|------|------|
| `/论文获取` | 从 Zotero 搜索/导入论文 |
| `/文献综述` | 11维度分析 + 跨论文对比 + 综述 |
| `/实证分析` | 四维实证方法论分析 |
| `/论文写作` | 创新选题 → 假设 → 模型 → 变量 → 蓝图 → 逐节撰写 → 审查 |
| `/实证回归` | Stata 回归代码生成与执行 |
| `/组会汇报幻灯片` | 生成学术 PPTX |
| `/导出Word` | 导出 DOCX 文件 |
| `/初始化新论文` | 归档当前工作、重置工作区 |
| `/配置LLM` | 配置 LLM API Key |

### Python CLI

```bash
# 论文获取
python scripts/zotero_extract.py --search "关键词" --output workspace/papers/metadata.json

# 文献综述
python scripts/run_pipeline.py --backend anthropic
python scripts/run_review.py --backend anthropic --sections 1,6,11

# 实证分析
python scripts/run_empirical.py --backend anthropic

# 论文写作
python scripts/run_write.py --backend anthropic --step topic
python scripts/run_write.py --backend anthropic --step full

# 配置
python scripts/config_wizard.py
python scripts/config_wizard.py --check
```

## 配置

### LLM API

系统支持两种 API 后端：

| 后端 | 推荐用途 |
|------|---------|
| DeepSeek (Anthropic 格式) | 推荐——性价比高，中文能力强 |
| Anthropic 官方 | Claude 模型 |
| OpenAI 兼容 | GPT-4o / DeepSeek / 通义千问 / 等 |

配置方式：
```bash
# 方式一：交互式向导
python scripts/config_wizard.py

# 方式二：手动 .env
cp .env.example .env
# 编辑 .env 填入 Key
```

### Zotero（可选）

系统可与本地 Zotero 库集成，自动提取论文元数据和 PDF 全文。

## 项目结构

```
├── agent/              # 编排引擎
├── skills/             # 核心技能（分析/写作/审查/索引）
├── scripts/            # CLI 入口 + 计量代码库
├── references/prompts/ # Prompt 模板库
│   ├── sections_single/      # 11 维度分析 Prompt
│   └── section_writing/      # 分节写作 Prompt
├── workspace/          # 产出目录（gitignored）
├── .env.example        # 环境变量模板
├── .gitignore
└── requirements.txt
```

## 依赖

```
pandas>=2.0.0
anthropic>=0.30.0
openai>=1.0.0
```

可选依赖：
- `chromadb` — 向量语义搜索
- `pytest` — 运行测试
- `statsmodels` / `linearmodels` — 计量回归

## License

MIT

## 致谢

本项目的 Prompt 设计参考了经济学实证研究的标准范式：
- 因果推断的识别策略分类（DID/RDD/IV/SCM）
- 中介效应与机制检验的三步法框架
- GB/T 7714 参考文献格式规范
