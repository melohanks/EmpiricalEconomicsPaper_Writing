# 全流程科研学术论文写作 Agent

## 外部工具链

```
阶段                     工具                         作用
──────────────────────────────────────────────────────────────────
论文获取    →  Zotero 本地库 (scripts/zotero_extract.py)  直接读取 SQLite 提取全部元数据+PDF
文本去AI味  →  humanizer-zh skill (/humanizer-zh)     去除分析报告中的AI写作痕迹
Word 导出   →  cli-anything-wps MCP (/wps-*)         创建/编辑/导出 DOCX
PPT 生成    →  ppt-master skill (/ppt-master)         学术报告 PPTX 生成
```

## 架构

```
agent/
├── core.py              # Agent 状态编排引擎（主入口）
└── state.py             # 工作区状态管理 (workspace/state.json)

skills/
├── base.py              # 技能基类 (BaseSkill)
├── file_handler.py      # 论文元数据导入/导出 (JSON/CSV)
├── llm_client.py        # LLM 统一调用接口 (Anthropic/OpenAI)
├── literature_analyzer.py  # 单篇论文 11 维度深度分析引擎
├── cross_paper_analyzer.py # ★ 跨论文对比分析引擎（共性提取+写作推荐+引用映射）
├── empirical_analyzer.py   # 经济学实证方法论四维度分析引擎
├── paper_writer.py         # 论文写作技能（选题→假设→模型→结论→全文）
├── data_handler.py         # 数据获取与下载脚本生成
├── regression_runner.py    # 计量回归代码生成、运行与结果解读
└── presentation_generator.py # 演讲稿生成（HTML 演示已废弃，ppt-master 替代）

references/prompts/
├── sections/            # 11 个跨论文对比 Prompt（旧版，保留兼容）
├── sections_single/     # 11 个单篇深度分析 Prompt（新版，主力）
│   ├── 01_introduction.txt
│   ├── 02_theoretical_framework.txt
│   ├── 03_identification.txt
│   ├── 04_data_variables.txt
│   ├── 05_empirical_methodology.txt
│   ├── 06_baseline_results.txt
│   ├── 07_robustness.txt
│   ├── 08_mechanism.txt
│   ├── 09_heterogeneity.txt
│   ├── 10_endogeneity.txt
│   └── 11_conclusion.txt
├── synthesis.txt        # 汇总单篇分析为完整文献综述
├── empirical_analysis.txt   # 实证方法论四维分析 Prompt
├── topic_selection.txt      # 选题Prompt
├── hypothesis.txt           # 假设提出Prompt
├── model_selection.txt      # 模型选择Prompt
├── conclusion_writing.txt   # 结论与政策建议Prompt
├── full_paper_writing.txt   # 完整论文写作Prompt
└── presentation_seminar.txt  # 学术报告风格幻灯片生成 Prompt

scripts/
├── zotero_extract.py    # 阶段〇：Zotero 本地库论文提取
├── run_collect.py       # 阶段一：论文导入
├── run_review.py        # 阶段二：逐结构分析 + 综述合成
├── run_empirical.py     # 阶段三：实证方法论四维分析
├── run_write.py         # 阶段四：分步论文写作 (topic/hypothesis/model/variables/conclusion/full)
├── run_regression.py    # 阶段五：标准化计量模型代码库 CLI 入口
├── run_pipeline.py      # 一键流水线（阶段一→二）
└── run_init.py          # 归档当前产出 + 重置工作区

scripts/regression_lib/   # 标准化计量模型代码库（8个模型）
├── __init__.py          # 模型注册表 + run_model() 统一入口
├── base.py              # 数据加载、结果保存
├── panel_fe.py          # 面板双向固定效应 (statsmodels)
├── sharp_rdd.py         # Sharp RDD (rdrobust / OLS回退)
├── staggered_did.py     # Staggered DID + Event Study
├── iv_2sls.py           # IV-2SLS (linearmodels / 手动回退)
├── mediation.py         # 中介效应 (三步法+Sobel+Bootstrap)
├── heterogeneity.py     # 异质性分析 (分组回归+交互项)
├── robustness.py        # 稳健性检验套件
├── diagnostics.py       # McCrary/平行趋势/安慰剂/VIF/协变量平衡
└── utils.py             # 聚类标准误、VIF、缩尾

workspace/
├── state.json           # 断点状态（含二维网格 analysis_state）
├── papers/              # 论文元数据 (metadata.json / *.csv)
├── analysis/            # 单篇论文独立分析（per-paper 目录结构）
│   ├── _analysis_index.json          # 总索引：论文→维度→状态
│   ├── _cross_paper/                 # 跨论文横向对比矩阵
│   │   ├── 01_introduction_comparison.md
│   │   ├── ...
│   │   ├── empirical_comparison_matrix.md
│   │   └── _comparison_index.json
│   ├── <论文标题1>/                   # 单篇论文独立分析目录
│   │   ├── 01_introduction.md        # 研究问题与动机（单篇深度）
│   │   ├── 01_introduction.json      # 结构化数据
│   │   ├── 02_theoretical_framework.md
│   │   ├── 02_theoretical_framework.json
│   │   ├── ... (03-11 同理)
│   │   ├── empirical.md              # 四维实证分析
│   │   ├── empirical.json
│   │   └── _paper_summary.json       # ★ 综合记忆文件（关键）
│   └── <论文标题2>/
│       └── ...
├── writing/             # 论文写作产出
│   ├── topic_proposals.md         # 候选选题
│   ├── hypotheses.md              # 研究假设
│   ├── model_recommendation.md    # 模型推荐
│   ├── variable_selection.md      # 变量体系
│   ├── paper_blueprint.md         # 完整写作蓝图
│   └── full_paper.md              # 完整论文初稿
├── regression/          # 回归结果 (JSON + TXT + .do + .log)
├── data/                # 数据文件 (CSV)
├── literature_review.md      # 完整文献综述
├── literature_review.docx    # 文献综述 Word版
├── review_analysis_report.json
├── presentation.pptx         # 组会 PPT (ppt-master)
├── presentation.html         # 组会 HTML 演示 (备用)
└── speech_script.md          # 组会演讲稿
```

## 快捷命令

| 命令 | 功能 | 关键工具 |
|------|------|---------|
| `/论文获取` | Zotero 搜索/DOI导入 → 提取元数据和全文 → 写入 workspace/papers/ | Zotero MCP |
| `/文献综述` | 论文导入 → 每篇独立11维深度分析 → _paper_summary.json → 跨论文合成综述 | Zotero + humanizer-zh |
| `/实证分析` | 四维实证分析 → workspace/analysis/<论文>/empirical.md|json → 更新_summary | humanizer-zh |
| `/论文写作` | 分步交互式写作（选题→假设→模型→变量→全文），聚合所有已归档论文分析 | — |
| `/实证回归` | 数据检查 → Stata 描述统计 → 基准回归 → 机制 → 异质性 → 稳健性 → 结果回收 | Stata MCP |
| `/组会汇报幻灯片` | 基于综述+分析数据 → ppt-master 生成 PPTX | ppt-master |
| `/导出Word` | 将文献综述/分析报告导出为 DOCX | cli-anything-wps |
| `/初始化新论文` | 归档当前全部产出 → 重置工作区 | — |

### 典型工作流（含新工具）

```
论文 A:
  ① /论文获取 "论文DOI或关键词"
  ② /文献综述         → humanizer-zh 去AI味
  ③ /实证分析          → humanizer-zh 去AI味
  ④ /论文写作          → 聚合全部分析
  ⑤ /实证回归          → Stata MCP 逐模型跑回归 → 结果回收
  ⑥ /组会汇报幻灯片     → ppt-master 生成 PPTX
  ⑥ /导出Word          → cli-anything-wps 导出 DOCX
  ⑦ /LaTeX编译         → md→LaTeX→xelatex→PDF (workspace/writing/paper.pdf)
  ⑧ /参考文献审查       → WebSearch 逐条验证引用真实性 → 剔除虚构文献
  ⑨ /初始化新论文

论文 B: ①→②→③...（/论文写作 会自动聚合论文A+B的全部分析）
```

每篇论文的完整产出归档在 `workspace/projects/<论文标题>/` 下，互不混淆。

### /论文写作 完整流程

```
Step 1: 选题     → workspace/writing/topic_proposals.md
Step 2: 提出假设 → workspace/writing/hypotheses.md
Step 3: 模型选择 → workspace/writing/model_recommendation.md
Step 4: 变量选取 → workspace/writing/variable_selection.md
Step 5: 蓝图汇总 → workspace/writing/paper_blueprint.md
Step 6: 撰写全文 → workspace/writing/full_paper.md
```

### humanizer-zh 去AI味 — 在所有文本生成后执行

每个阶段的分析报告生成后，调用 `/humanizer-zh` 对以下文件去AI味：
- `workspace/analysis/<论文>/*.md`（每篇论文11个维度分析报告）
- `workspace/analysis/<论文>/empirical.md`（实证分析报告）
- `workspace/literature_review.md`（文献综述）
- `workspace/analysis/_cross_paper/*.md`（跨论文对比矩阵）
- `workspace/writing/full_paper.md`（完整论文）

## 使用方式

### 方式一：快捷命令

直接在对话框输入 `/论文获取`、`/文献综述`、`/组会汇报幻灯片` 等。

### 方式二：命令行

```bash
# 完整流水线（导入+综述）
python scripts/run_pipeline.py --backend anthropic --model deepseek-v4-pro

# 仅文献综述（跳过幻灯片）
python scripts/run_review.py --backend anthropic --skip-presentation

# 仅特定维度
python scripts/run_review.py --backend anthropic --sections 1,6,11

# 实证分析
python scripts/run_empirical.py --backend anthropic

# 论文写作分步
python scripts/run_write.py --backend anthropic --step topic
python scripts/run_write.py --backend anthropic --step hypothesis --input "题目信息"
python scripts/run_write.py --backend anthropic --step model --input "题目+假设"
python scripts/run_write.py --backend anthropic --step variables --input "题目+模型"
python scripts/run_write.py --backend anthropic --step full --input "全部材料"

# 计量回归
python scripts/run_regression.py --list                          # 列出模型
python scripts/run_regression.py --model panel_fe --data ...     # 运行指定模型
python scripts/run_regression.py --blueprint paper_blueprint.md  # 蓝图自动路由
```

### 论文获取方式

**方式一：Zotero DOI 导入**
直接在对话框输入 `/论文获取 10.19626/j.cnki.cn31-1163/f.2026.04.007`

**方式二：Zotero 关键词搜索**
`/论文获取 耐心资本 供应链韧性`

**方式三：手动放入（备用）**
将论文元数据放入 `workspace/papers/metadata.json`。

### 配置 LLM

```bash
export ANTHROPIC_API_KEY="your-key"
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_MODEL="deepseek-v4-pro"
export LLM_BACKEND="anthropic"
```

## 参考文献生成与审查规范

### 核心原则
1. **只引用文中实际出现的文献**：不因"我们分析了N篇论文"而将所有分析论文列入参考文献
2. **每条引用必须可验证**：通过 WebSearch 确认论文真实存在（作者、标题、期刊、年份均匹配）
3. **中文引用优先 Zotero 库**：优先使用 `workspace/papers/metadata.json` 中已有论文
4. **英文经典可保留**：教科书级方法文献（Dixit & Pindyck, Myers & Majluf 等）可直接使用
5. **禁止 LLM 编造**：全文生成后必须执行审查步骤

### 审查流程
```
Step 1: 提取文中所有括号引用 → 得到引用列表
Step 2: 对每条引用执行 WebSearch 验证：
  - 英文：搜索 "Author Author Title Journal Year"
  - 中文：搜索 "作者 标题 期刊 年份"
Step 3: 分类标注：✅真实 / ❌虚构 / ⚠️真实但主题错用
Step 4: 虚构文献 → 从 Zotero 库找最匹配的真论文替换
Step 5: 错用文献 → 替换为主题正确的真实文献或删除
Step 6: 同步更新 .md 和 .tex 参考文献列表
```

### LaTeX 编译
```
md→LaTeX→xelatex→PDF 流程：
1. 生成 paper.tex（ctexart 文档类，GB/T 7714 参考文献格式）
2. xelatex -interaction=nonstopmode paper.tex （运行两次以解析交叉引用）
3. 输出 workspace/writing/paper.pdf
4. 编译警告（fancyhdr headheight, 字体回退）可忽略
```

### .do 文件可移植性规范
```
1. 路径用全局宏：文件顶部定义 global PROJECT_ROOT 和 global DATA_PATH
2. 数据放项目内：分析样本存 workspace/data/
3. 换电脑只需改两行：PROJECT_ROOT 和 DATA_PATH
4. 归档后仍可运行：所有依赖在项目目录内
5. 原始数据可放外部：DATA_PATH 可指向 Downloads 等任意位置
6. regression/do/ 目录只保留一个 01_portable_master.do
```

## 流水线步骤

```
阶段〇：论文获取（新）
  ├→ Zotero MCP 搜索/DOI导入论文
  ├→ 提取标题/作者/摘要/关键词/DOI
  └→ 写入 workspace/papers/metadata.json

阶段一：论文导入
  └→ FileHandler 读取 workspace/papers/ 中的 JSON/CSV

阶段二：文献综述分析（新架构：每篇论文独立分析 + 跨论文共性提取）
  ├→ Step A: 逐论文逐维度分析 → workspace/analysis/<论文>/0x_slug.md|json
  ├→ Step A': humanizer-zh 对每篇论文每个维度分析去AI味
  ├→ Step B: CrossPaperAnalyzer 跨论文对比分析：
  │     ├→ 11 个文献维度逐一对比 → _cross_paper/0x_slug_comparison.md|json
  │     ├→ 6 个实证方面逐一对比 → _cross_paper/empirical_*_comparison.md|json
  │     ├→ 共性提取 + 引用映射 → _cross_paper/_cross_paper_summary.json
  │     └→ 写作综合推荐 → _cross_paper/_writing_synthesis.json
  └→ Step C: LiteratureAnalyzer 生成完整文献综述 → literature_review.md

阶段三：实证方法论分析
  ├→ Step A: EmpiricalAnalyzer 四维实证分析 → workspace/analysis/<论文>/empirical.md|json
  │     └→ 自动更新该论文的 _paper_summary.json 的 empirical 字段
  └→ Step A': humanizer-zh 对实证报告去AI味

阶段四：论文写作
  ├→ Step 1-6: PaperWriter 分步写作
  └→ Step 6': humanizer-zh 对全文去AI味

阶段五：演示与导出
  ├→ **ppt-master 生成 PPTX**（/组会汇报幻灯片 唯一路径，不允许使用 HTML 回退）
  ├→ cli-anything-wps / python-docx 导出 Word
  ├→ md→LaTeX 转换 (scripts/md_to_latex.py)
  └→ xelatex 编译 PDF (workspace/writing/paper.pdf)
```

系统支持断点恢复：断点状态存储为二维网格 `{"<论文标题>": ["01","02",...]}`，中断后自动跳过已完成的论文+维度。

## 计量模型代码库

`scripts/regression_lib/` 提供 8 个标准化计量模型模块，统一接口 `run(data_path, y_var, x_vars, **kwargs) → dict`。

### 可用模型

| 模型名 | 方法 | 依赖 |
|--------|------|------|
| `panel_fe` | 面板双向固定效应 + 聚类标准误 | statsmodels |
| `sharp_rdd` | Sharp RDD（rdrobust 首选 / OLS 回退） | rdrobust |
| `staggered_did` | TWFE + Event Study 动态效应 | statsmodels |
| `iv_2sls` | IV-2SLS（linearmodels 首选 / 手动回退） | linearmodels |
| `mediation` | 三步法 + Sobel + Bootstrap CI | statsmodels |
| `heterogeneity` | 分组回归 + 交互项 | statsmodels |
| `robustness` | 缩尾/替换Y/替换X/排除样本 | statsmodels |
| `diagnostics` | McCrary/平行趋势/安慰剂/VIF/协变量平衡 | statsmodels |

### 使用方式

```bash
# CLI 单模型
python scripts/run_regression.py --model panel_fe \
    --data workspace/data/sample.csv --y Chain --x PCapital \
    --controls Age,ROA --entity firm_id --time year

# CLI 蓝图自动路由（读取 paper_blueprint.md → 批量运行）
python scripts/run_regression.py --blueprint workspace/writing/paper_blueprint.md \
    --data workspace/data/sample.csv

# 代码调用
from regression_lib import run_model
result = run_model("sharp_rdd", "data.csv", y_var="Chain",
                   running_var="firm_age", cutoff=5.0)
```

### 蓝图→模型自动映射

| 蓝图中出现 | 自动运行模型 |
|-----------|-------------|
| "RDD" / "断点" | `sharp_rdd` |
| "DID" / "双重差分" | `staggered_did` |
| "IV" / "工具变量" | `iv_2sls` |
| 默认 | `panel_fe` → `mediation` → `heterogeneity` → `robustness` → `diagnostics`
