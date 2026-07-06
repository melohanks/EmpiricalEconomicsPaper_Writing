"""
跨论文对比分析引擎。
在所有论文的 11 维度分析和实证分析完成后运行，对每个维度/实证方面逐一对比，
提取共性模式，构建结构化跨论文记忆（_cross_paper_summary.json），
为后续论文写作提供：理论推荐、模型推荐、变量推荐、引用映射。
"""
import os
import json
import re
from skills.base import BaseSkill
from skills.llm_client import LlmClient


class CrossPaperAnalyzer(BaseSkill):
    """
    跨论文对比分析技能。
    基于所有 _paper_summary.json，逐维度/实证方面进行对比，
    提取共性、差异、共识空缺，生成结构化记忆。

    actions:
      - compare_all          : 全部对比（11维度 + 实证6方面）
      - compare_dimension    : 单个维度对比
      - compare_empirical    : 实证全方面对比
      - build_synthesis      : 生成写作素材综合推荐
    """

    # 11 个文献维度
    DIMENSIONS = [
        ("01", "introduction",           "研究问题与动机"),
        ("02", "theoretical_framework",  "理论框架"),
        ("03", "identification",         "识别策略"),
        ("04", "data_variables",         "数据与变量"),
        ("05", "empirical_methodology",  "实证方法与模型设定"),
        ("06", "baseline_results",       "基准结果"),
        ("07", "robustness",             "稳健性检验"),
        ("08", "mechanism",              "机制分析"),
        ("09", "heterogeneity",          "异质性分析"),
        ("10", "endogeneity",            "内生性处理"),
        ("11", "conclusion",             "结论与政策含义"),
    ]

    # 实证对比子方面
    EMPIRICAL_ASPECTS = [
        ("model",         "模型选择与方法"),
        ("variables",     "变量体系"),
        ("mechanism",     "机制分析"),
        ("heterogeneity", "异质性分析"),
        ("robustness",    "稳健性检验"),
        ("endogeneity",   "内生性处理"),
    ]

    def __init__(self):
        super().__init__(
            name="CrossPaperAnalyzer",
            description="跨论文对比分析引擎——逐维度/实证方面对比 + 共性提取 + 写作素材综合推荐"
        )
        self.llm = LlmClient()
        self._analysis_root = os.path.abspath("workspace/analysis")
        self._cross_dir = os.path.join(self._analysis_root, "_cross_paper")

    # ─── 公共入口 ──────────────────────────────────────────────

    def execute(self, action: str, **kwargs):
        if action == "compare_all":
            return self._compare_all(**kwargs)
        elif action == "compare_dimension":
            return self._compare_dimension(**kwargs)
        elif action == "compare_empirical":
            return self._compare_empirical_all(**kwargs)
        elif action == "build_synthesis":
            return self._build_synthesis(**kwargs)
        else:
            raise NotImplementedError(f"未实现的动作: {action}")

    # ─── 全部对比 ──────────────────────────────────────────────

    def _compare_all(
        self,
        paper_summaries: list = None,
        backend: str = None,
        model: str = None,
        on_progress=None,
    ) -> dict:
        """
        运行全部对比分析：11 维度 + 实证 6 方面。
        必须提供 paper_summaries（从 _paper_summary.json 加载），至少需要 2 篇。
        """
        # 加载 paper_summaries
        if paper_summaries is None:
            paper_summaries = self._load_all_summaries()

        if len(paper_summaries) < 2:
            print(f"[{self.name}] 需要至少 2 篇论文才能进行对比分析，当前: {len(paper_summaries)}")
            return {"success": False, "reason": "need_at_least_2_papers"}

        os.makedirs(self._cross_dir, exist_ok=True)

        print(f"\n[{'='*60}]")
        print(f"[{self.name}] 启动跨论文对比分析: {len(paper_summaries)} 篇论文")
        print(f"[{'='*60}]")

        all_results = {
            "dimensions": {},
            "empirical": {},
            "papers_analyzed": [ps.get("paper_title", "") for ps in paper_summaries],
            "total_papers": len(paper_summaries),
        }

        # ── A. 11 个维度逐一对比 ──
        for num, slug, title in self.DIMENSIONS:
            print(f"\n[{self.name}] 维度对比 [{num}/11]: {title}")
            result = self._compare_dimension(
                dimension_key=f"{num}_{slug}",
                dimension_title=title,
                paper_summaries=paper_summaries,
                backend=backend,
                model=model,
            )
            all_results["dimensions"][f"{num}_{slug}"] = result
            if on_progress:
                on_progress("dimension", num, title, result)

        # ── B. 实证 6 方面逐一对比 ──
        for aspect_key, aspect_title in self.EMPIRICAL_ASPECTS:
            print(f"\n[{self.name}] 实证对比: {aspect_title}")
            result = self._compare_empirical_aspect(
                aspect_key=aspect_key,
                aspect_title=aspect_title,
                paper_summaries=paper_summaries,
                backend=backend,
                model=model,
            )
            all_results["empirical"][aspect_key] = result
            if on_progress:
                on_progress("empirical", aspect_key, aspect_title, result)

        # ── C. 构建跨论文综合记忆 ──
        cross_summary = self._build_cross_paper_summary(all_results, paper_summaries)
        summary_path = os.path.join(self._cross_dir, "_cross_paper_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(cross_summary, f, ensure_ascii=False, indent=2)
        print(f"\n[{self.name}] 跨论文综合记忆 → {summary_path}")

        # ── D. 写作素材综合推荐 ──
        synthesis = self._build_synthesis(cross_summary, backend, model)
        synthesis_path = os.path.join(self._cross_dir, "_writing_synthesis.json")
        with open(synthesis_path, "w", encoding="utf-8") as f:
            json.dump(synthesis, f, ensure_ascii=False, indent=2)
        print(f"[{self.name}] 写作综合推荐 → {synthesis_path}")

        # ── E. 更新对比索引 ──
        self._update_comparison_index(all_results)

        print(f"\n[{self.name}] ╔══════════════════════════════════════════╗")
        print(f"[{self.name}] ║  跨论文对比分析完成                        ║")
        print(f"[{self.name}] ║  维度对比: 11 个                           ║")
        print(f"[{self.name}] ║  实证对比: 6 个                           ║")
        print(f"[{self.name}] ║  综合记忆: _cross_paper_summary.json      ║")
        print(f"[{self.name}] ║  写作推荐: _writing_synthesis.json        ║")
        print(f"[{self.name}] ╚══════════════════════════════════════════╝")

        return {
            "success": True,
            "cross_summary_path": summary_path,
            "synthesis_path": synthesis_path,
            "all_results": all_results,
        }

    # ─── 单个维度对比 ──────────────────────────────────────────

    def _compare_dimension(
        self,
        dimension_key: str,
        dimension_title: str,
        paper_summaries: list,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        对单个维度进行跨论文对比分析。
        提取该维度下所有论文的共性模式、差异点和共识空缺。
        """
        # 从 paper_summaries 中提取该维度的数据
        dim_data = []
        for ps in paper_summaries:
            title = ps.get("paper_title", "未知")
            sections = ps.get("sections", {})
            sec = sections.get(dimension_key, {})
            if sec:
                dim_data.append({
                    "paper": title,
                    "key_findings": sec.get("key_findings", []),
                    "gaps": sec.get("gaps", []),
                    "info_sufficiency": sec.get("information_sufficiency", "未知"),
                    "raw": {k: v for k, v in sec.items()
                            if k not in ("key_findings", "gaps", "information_sufficiency")},
                })

        if not dim_data:
            return {"success": False, "reason": "no_data"}

        # 构建对比 Prompt
        dim_text_parts = []
        for dd in dim_data:
            raw_str = json.dumps(dd["raw"], ensure_ascii=False, indent=2)
            dim_text_parts.append(
                f"### {dd['paper']}\n"
                f"- 关键发现: {dd['key_findings'][:3]}\n"
                f"- 空缺: {dd['gaps'][:3]}\n"
                f"- 详细信息: {raw_str[:1500]}\n"
            )
        dim_text = "\n\n".join(dim_text_parts)

        compare_prompt = f"""你是一位计量经济学领域资深学者，正在对 {len(dim_data)} 篇论文的「{dimension_title}」维度进行跨论文对比分析。这些论文主题相关，你的任务是提取共性模式。

【各论文在该维度的分析数据】
{dim_text}

【输出格式要求】
请严格按以下结构输出，每个部分都必须包含：

### 1. 共性模式（Common Patterns）
列出这批论文在「{dimension_title}」维度上的共同特征。以表格呈现：
| 序号 | 共性特征 | 覆盖论文数 | 具体说明 |

### 2. 差异与分歧（Divergences）
列出各论文之间的显著差异。以表格呈现：
| 序号 | 差异点 | 论文A的做法 | 论文B的做法 | 差异原因分析 |

### 3. 共识性空缺（Consensus Gaps）
多篇论文共同指向但尚未被充分研究的问题。以列表呈现，每条标注：空缺描述 | 来源论文。

### 4. 方法论启示（Methodological Insights）
从这些论文的共性中提炼出的方法论规律。对你未来研究设计的启示。

【JSON结构化信息】
请在报告末尾输出一个 JSON 代码块（```json ... ```）：
```json
{{
  "dimension_key": "{dimension_key}",
  "common_patterns": [
    {{"id": 1, "pattern": "共性特征描述", "papers_count": 0, "details": "具体说明"}}
  ],
  "divergences": [
    {{"id": 1, "aspect": "差异点", "papers_practices": {{"论文1": "做法", "论文2": "做法"}}, "reason": "差异原因"}}
  ],
  "consensus_gaps": [
    {{"description": "空缺描述", "source_papers": ["论文1", "论文2"]}}
  ],
  "methodological_insights": ["启示1", "启示2"],
  "convergence_level": "high|moderate|low",
  "key_takeaway_for_writing": "该维度最重要的写作参考信息（一句话）"
}}
```

【约束】
- 只基于提供的数据进行分析，不编造
- 共性必须是真正跨多篇论文存在的，单篇独有的不算共性
- 如果某维度数据不足（如信息充分性为"不足"），诚实标注
"""

        try:
            raw_output = self.llm.execute(
                prompt=compare_prompt,
                system_prompt=f"你是一位计量经济学领域资深学者，正在对 {len(dim_data)} 篇论文的「{dimension_title}」维度进行跨论文对比，寻找共性模式。",
                backend=backend, model=model, max_tokens=4000,
            )
        except Exception as e:
            print(f"  [{dimension_key}] 对比失败: {e}")
            return {"success": False, "reason": str(e), "dimension_key": dimension_key}

        # 保存 .md
        md_path = os.path.join(self._cross_dir, f"{dimension_key}_comparison.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {dimension_key}. {dimension_title} — 跨论文对比分析\n\n")
            f.write(f"> {len(dim_data)} 篇论文参与对比\n\n")
            f.write(raw_output)

        # 提取 JSON
        structured = self._extract_json(raw_output, dimension_key)
        structured["paper_count"] = len(dim_data)
        structured["papers"] = [dd["paper"] for dd in dim_data]

        # 保存 .json
        json_path = os.path.join(self._cross_dir, f"{dimension_key}_comparison.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(structured, f, ensure_ascii=False, indent=2)

        print(f"  [{dimension_key}] ✓ → {md_path} | 共性: {len(structured.get('common_patterns', []))} 条")
        return {
            "success": True,
            "dimension_key": dimension_key,
            "dimension_title": dimension_title,
            "structured": structured,
            "md_path": md_path,
            "json_path": json_path,
            "paper_count": len(dim_data),
        }

    # ─── 实证全方面对比 ────────────────────────────────────────

    def _compare_empirical_all(
        self,
        paper_summaries: list = None,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """对所有实证方面逐一对比"""
        if paper_summaries is None:
            paper_summaries = self._load_all_summaries()

        results = {}
        for aspect_key, aspect_title in self.EMPIRICAL_ASPECTS:
            results[aspect_key] = self._compare_empirical_aspect(
                aspect_key, aspect_title, paper_summaries, backend, model
            )
        return results

    def _compare_empirical_aspect(
        self,
        aspect_key: str,
        aspect_title: str,
        paper_summaries: list,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        对单个实证方面进行跨论文对比。
        aspect_key: model|variables|mechanism|heterogeneity|robustness|endogeneity
        """
        # 从 paper_summaries 中提取实证数据
        emp_data = self._extract_empirical_data(aspect_key, paper_summaries)

        if len(emp_data) < 2:
            return {"success": False, "reason": f"only_{len(emp_data)}_papers_with_data"}

        # 构建各 aspect 专属的对比 Prompt
        prompt = self._build_empirical_compare_prompt(aspect_key, aspect_title, emp_data)

        try:
            raw_output = self.llm.execute(
                prompt=prompt,
                system_prompt=f"你是一位经济学实证研究方法论专家，正在对 {len(emp_data)} 篇论文的「{aspect_title}」进行跨论文对比，寻找共性模式。",
                backend=backend, model=model, max_tokens=5000,
            )
        except Exception as e:
            print(f"  [empirical:{aspect_key}] 对比失败: {e}")
            return {"success": False, "reason": str(e), "aspect_key": aspect_key}

        # 保存
        md_path = os.path.join(self._cross_dir, f"empirical_{aspect_key}_comparison.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# 实证对比: {aspect_title}\n\n")
            f.write(f"> {len(emp_data)} 篇论文参与对比\n\n")
            f.write(raw_output)

        structured = self._extract_json(raw_output, f"empirical_{aspect_key}")
        structured["paper_count"] = len(emp_data)
        structured["papers"] = [ed["paper"] for ed in emp_data]

        json_path = os.path.join(self._cross_dir, f"empirical_{aspect_key}_comparison.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(structured, f, ensure_ascii=False, indent=2)

        print(f"  [empirical:{aspect_key}] ✓ → {md_path}")
        return {
            "success": True,
            "aspect_key": aspect_key,
            "aspect_title": aspect_title,
            "structured": structured,
            "md_path": md_path,
            "json_path": json_path,
            "paper_count": len(emp_data),
        }

    # ─── 实证数据提取 ──────────────────────────────────────────

    def _extract_empirical_data(self, aspect_key: str, paper_summaries: list) -> list:
        """从 paper_summaries 中提取特定实证方面的数据"""
        data = []
        for ps in paper_summaries:
            title = ps.get("paper_title", "未知")
            sections = ps.get("sections", {})
            emp = sections.get("empirical", {})

            entry = {"paper": title}

            if aspect_key == "model":
                # 从 05_empirical_methodology + empirical 取
                meth = sections.get("05_empirical_methodology", {})
                entry["baseline_model_form"] = meth.get("baseline_model_form", "")
                entry["estimation_method"] = meth.get("estimation_method", "")
                entry["fixed_effects"] = meth.get("fixed_effects", [])
                entry["standard_error_type"] = meth.get("standard_error_type", "")
                entry["model_type"] = emp.get("model_type", "")
                entry["endogeneity_strategy"] = emp.get("endogeneity_strategy", "")

            elif aspect_key == "variables":
                dv = sections.get("04_data_variables", {})
                kv = dv.get("key_variables", {})
                entry["y_var"] = emp.get("y_var", "")
                entry["x_var"] = emp.get("x_var", "")
                if isinstance(kv.get("Y"), dict):
                    entry["y_definition"] = kv["Y"].get("definition", "")
                if isinstance(kv.get("X"), dict):
                    entry["x_definition"] = kv["X"].get("definition", "")
                entry["controls"] = kv.get("controls", []) if isinstance(kv, dict) else []
                entry["data_source"] = dv.get("data_source", "")
                entry["data_structure"] = dv.get("data_structure", "")
                entry["sample_period"] = dv.get("sample_period", "")

            elif aspect_key == "mechanism":
                mech = sections.get("08_mechanism", {})
                entry["mechanism_channels"] = mech.get("mechanism_channels", [])
                entry["mechanism_vars"] = emp.get("mechanism_vars", [])

            elif aspect_key == "heterogeneity":
                het = sections.get("09_heterogeneity", {})
                entry["heterogeneity_dimensions"] = het.get("heterogeneity_dimensions", [])
                entry["heterogeneity_dims"] = emp.get("heterogeneity_dims", [])

            elif aspect_key == "robustness":
                rob = sections.get("07_robustness", {})
                entry["robustness_checks"] = rob.get("robustness_checks", [])
                entry["overall_robustness_score"] = rob.get("overall_robustness_score", "")
                entry["emp_robustness_checks"] = emp.get("robustness_checks", [])

            elif aspect_key == "endogeneity":
                endo = sections.get("10_endogeneity", {})
                entry["endogeneity_types"] = endo.get("endogeneity_types", [])
                entry["treatment_method"] = endo.get("treatment_method", "")
                entry["iv_details"] = endo.get("iv_details", {})
                entry["did_details"] = endo.get("did_details", {})

            # 只有当有实际数据时才纳入
            has_data = any(
                v for k, v in entry.items()
                if k != "paper" and v and v != [] and v != {}
            )
            if has_data:
                data.append(entry)

        return data

    def _build_empirical_compare_prompt(
        self, aspect_key: str, aspect_title: str, emp_data: list
    ) -> str:
        """为每个实证方面构建专属的对比 Prompt"""
        data_text = json.dumps(emp_data, ensure_ascii=False, indent=2)

        # 各 aspect 的专属对比维度
        aspect_specifics = {
            "model": """
【重点关注】
- 基准模型类型的分布（固定效应/系统GMM/DID/RDD等）
- 固定效应的共同选择（个体FE/时间FE/行业FE）
- 标准误聚类的共同层级
- 内生性处理策略的分布
- 是否存在"最优实践"（多数论文采用的方法论组合）""",

            "variables": """
【重点关注】
- 被解释变量（Y）的共同测度方式
- 核心解释变量（X）的共同测度方式
- 控制变量的共同选择（按出现频率排序）
- 数据源的共同选择
- 变量构建是否存在行业共识""",

            "mechanism": """
【重点关注】
- 共同出现的机制渠道及频率
- 机制检验方法的分布（三步法/Bootstrap/因果中介分析等）
- 是否存在"必检机制"（多数论文都检验的因果渠道）
- 中介变量的共同选择
- 机制证据强度的整体水平""",

            "heterogeneity": """
【重点关注】
- 共同出现的异质性维度（企业规模/所有制/区域等）
- 异质性检验方法的分布（交互项/分组回归/分位数等）
- 是否存在一致的异质性模式（如"大规模企业效应更强"）
- 多重假设检验校正的使用频率
- 哪些异质性维度被普遍忽视""",

            "robustness": """
【重点关注】
- 稳健性检验类型的分布（替换变量/替换样本/替换模型/安慰剂等）
- 是否存在"标配检验"（几乎所有论文都做的）
- 整体稳健性水平
- 是否有论文的结论因稳健性不足而存疑
- 被普遍遗漏的稳健性检验""",

            "endogeneity": """
【重点关注】
- 内生性类型的分布（遗漏变量/反向因果/测量误差/样本选择）
- 处理方法的选择频率（IV/DID/RDD/Heckman等）
- 共同使用的工具变量类型
- 识别假设的可信度整体水平
- 内生性处理的整体质量评估""",
        }

        return f"""你是一位经济学实证研究方法论专家。请基于以下 {len(emp_data)} 篇论文在「{aspect_title}」方面的数据，进行跨论文对比分析。

【各论文数据】
{data_text}

{aspect_specifics.get(aspect_key, '')}

【输出格式要求】
请严格按以下结构输出：

### 1. 整体分布
以表格列出各论文在该方面的核心特征：
| 论文 | 核心特征1 | 核心特征2 | 核心特征3 |

### 2. 共性模式（Common Patterns）
以表格呈现跨论文的共同做法：
| 序号 | 共性特征 | 覆盖论文数 | 论文列表 | 是否行业共识 |

### 3. 差异分析（Divergences）
以表格呈现显著差异：
| 序号 | 差异点 | 做法A（论文） | 做法B（论文） | 哪种更优 |

### 4. 方法论规律与启示
从共性中提炼的对未来研究设计的方法论指导。

【JSON结构化信息】
请在报告末尾输出一个 JSON 代码块：
```json
{{
  "aspect": "{aspect_key}",
  "distribution_summary": "一句话概括整体分布",
  "common_patterns": [
    {{"id": 1, "pattern": "共性描述", "papers_count": 0, "papers": ["论文1"], "is_consensus": true/false}}
  ],
  "divergences": [
    {{"id": 1, "aspect": "差异点", "approaches": {{"论文1": "做法", "论文2": "做法"}}, "recommended": "推荐做法及理由"}}
  ],
  "methodological_rules": ["规律1", "规律2"],
  "frequency_table": {{"item_name": "frequency_count"}},
  "convergence_level": "high|moderate|low",
  "key_takeaway_for_writing": "该方面最重要的写作参考信息（一句话）"
}}
```
"""

    # ─── 跨论文综合记忆构建 ───────────────────────────────────

    def _build_cross_paper_summary(
        self, all_results: dict, paper_summaries: list
    ) -> dict:
        """
        从所有对比结果中构建 _cross_paper_summary.json。
        这是跨论文记忆的核心文件，后续写作步骤将以此为参考。
        """
        summary = {
            "meta": {
                "total_papers": len(paper_summaries),
                "papers": [ps.get("paper_title", "") for ps in paper_summaries],
                "generated_from": "CrossPaperAnalyzer",
            },
            "dimension_insights": {},
            "empirical_insights": {},
            "synthesis_for_writing": {},
        }

        # 汇总各维度对比的关键发现
        for dim_key, dim_result in all_results.get("dimensions", {}).items():
            if not dim_result.get("success"):
                continue
            st = dim_result.get("structured", {})
            summary["dimension_insights"][dim_key] = {
                "common_patterns": st.get("common_patterns", []),
                "consensus_gaps": st.get("consensus_gaps", []),
                "methodological_insights": st.get("methodological_insights", []),
                "convergence_level": st.get("convergence_level", ""),
                "key_takeaway": st.get("key_takeaway_for_writing", ""),
            }

        # 汇总实证对比的关键发现
        for emp_key, emp_result in all_results.get("empirical", {}).items():
            if not emp_result.get("success"):
                continue
            st = emp_result.get("structured", {})
            summary["empirical_insights"][emp_key] = {
                "common_patterns": st.get("common_patterns", []),
                "frequency_table": st.get("frequency_table", {}),
                "methodological_rules": st.get("methodological_rules", []),
                "convergence_level": st.get("convergence_level", ""),
                "key_takeaway": st.get("key_takeaway_for_writing", ""),
            }

        # 汇总所有共性 gaps（最重要的写作素材）
        all_gaps = []
        for dim_key, dim_data in summary["dimension_insights"].items():
            for gap in dim_data.get("consensus_gaps", []):
                if isinstance(gap, dict):
                    all_gaps.append({
                        "source_dimension": dim_key,
                        "description": gap.get("description", ""),
                        "source_papers": gap.get("source_papers", []),
                    })

        # 汇总频率统计
        frequency_summary = self._compute_frequencies(all_results)

        summary["synthesis_for_writing"] = {
            "top_gaps": sorted(all_gaps, key=lambda g: len(g.get("source_papers", [])), reverse=True)[:10],
            "frequency_summary": frequency_summary,
        }

        return summary

    def _compute_frequencies(self, all_results: dict) -> dict:
        """从所有对比结果中计算高频出现的元素"""
        freq = {}

        # 从 empirical insights 中收集频率表
        for emp_key, emp_result in all_results.get("empirical", {}).items():
            if emp_result.get("success"):
                ft = emp_result.get("structured", {}).get("frequency_table", {})
                if ft:
                    freq[emp_key] = ft

        return freq

    # ─── 写作素材综合推荐 ──────────────────────────────────────

    def _build_synthesis(
        self,
        cross_summary: dict = None,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        基于跨论文对比结果，生成写作素材综合推荐。
        这是 /论文写作 步骤的直接参考数据源。
        """
        if cross_summary is None:
            # 尝试从文件加载
            sp = os.path.join(self._cross_dir, "_cross_paper_summary.json")
            if os.path.exists(sp):
                with open(sp, "r", encoding="utf-8") as f:
                    cross_summary = json.load(f)
            else:
                return {"error": "no_cross_summary_available"}

        # 从对比结果中提取关键推荐
        dim_insights = cross_summary.get("dimension_insights", {})
        emp_insights = cross_summary.get("empirical_insights", {})

        # 汇总所有 methodological_insights
        all_method_insights = []
        for dim_data in dim_insights.values():
            all_method_insights.extend(dim_data.get("methodological_insights", []))
        for emp_data in emp_insights.values():
            all_method_insights.extend(emp_data.get("methodological_rules", []))

        # 汇总所有 common_patterns
        all_patterns = []
        for dim_key, dim_data in dim_insights.items():
            for pat in dim_data.get("common_patterns", []):
                if isinstance(pat, dict):
                    pat["source_dimension"] = dim_key
                    all_patterns.append(pat)

        # 构建引用映射（每个发现 → 支撑论文列表）
        citation_map = {}
        for pat in all_patterns:
            desc = pat.get("pattern", "")
            if desc:
                citation_map[desc] = pat.get("papers", pat.get("source_papers", []))

        # 从 gaps 构建引用映射
        for gap in cross_summary.get("synthesis_for_writing", {}).get("top_gaps", []):
            desc = gap.get("description", "")
            if desc:
                citation_map[desc] = gap.get("source_papers", [])

        synthesis = {
            "methodological_insights": all_method_insights[:15],
            "common_patterns_summary": [
                {
                    "pattern": pat.get("pattern", ""),
                    "papers_count": pat.get("papers_count", 0),
                    "source_dimension": pat.get("source_dimension", ""),
                }
                for pat in all_patterns[:20]
            ],
            "consensus_gaps": cross_summary.get("synthesis_for_writing", {}).get("top_gaps", []),
            "frequency_summary": cross_summary.get("synthesis_for_writing", {}).get("frequency_summary", {}),
            "citation_map": citation_map,
            "total_papers": cross_summary.get("meta", {}).get("total_papers", 0),
            "papers": cross_summary.get("meta", {}).get("papers", []),
        }

        # 如果只有 2 篇以上论文且有 LLM，生成综合推荐文本
        if len(synthesis.get("papers", [])) >= 2 and backend:
            try:
                synthesis_text = self._generate_synthesis_text(synthesis, backend, model)
                synthesis["narrative_synthesis"] = synthesis_text
            except Exception:
                synthesis["narrative_synthesis"] = ""

        return synthesis

    def _generate_synthesis_text(
        self, synthesis: dict, backend: str = None, model: str = None
    ) -> str:
        """调用 LLM 生成综合推荐叙述文本"""
        prompt = f"""你是一位经济学博士生导师。请基于以下跨论文对比分析的综合数据，撰写一段"写作综合推荐"。

【数据】
- 论文数量: {synthesis.get('total_papers', 0)}
- 论文列表: {', '.join(synthesis.get('papers', []))}
- 共识性空缺 (Top 5): {json.dumps(synthesis.get('consensus_gaps', [])[:5], ensure_ascii=False)}
- 共性模式 (Top 10): {json.dumps(synthesis.get('common_patterns_summary', [])[:10], ensure_ascii=False)}
- 方法论启示: {json.dumps(synthesis.get('methodological_insights', [])[:10], ensure_ascii=False)}

【输出要求】
请撰写一段结构化的综合推荐，包含：
1. **研究选题建议**（基于共识空缺，2-3个方向）
2. **理论框架建议**（基于高频出现的理论）
3. **模型与方法建议**（基于最高频使用的方法论组合）
4. **变量体系建议**（基于最高频的 Y/X/控制变量）
5. **机制与异质性建议**（基于最高频的机制渠道和异质性维度）
6. **可引用的关键文献**（每个建议标注支撑论文）

【约束】
- 每个建议必须明确标注其来源论文
- 不推荐任何未被至少 2 篇论文支持的做法
"""

        return self.llm.execute(
            prompt=prompt,
            system_prompt=f"你是一位经济学博士生导师，正在基于 {synthesis.get('total_papers', 0)} 篇论文的对比分析撰写写作综合推荐。",
            backend=backend, model=model, max_tokens=4000,
        )

    # ─── 辅助方法 ──────────────────────────────────────────────

    def _load_all_summaries(self) -> list:
        """加载所有 _paper_summary.json"""
        summaries = []
        if not os.path.exists(self._analysis_root):
            return summaries
        for dname in os.listdir(self._analysis_root):
            paper_dir = os.path.join(self._analysis_root, dname)
            if not os.path.isdir(paper_dir) or dname.startswith("_"):
                continue
            sp = os.path.join(paper_dir, "_paper_summary.json")
            if os.path.exists(sp):
                try:
                    with open(sp, "r", encoding="utf-8") as f:
                        summaries.append(json.load(f))
                except Exception:
                    pass
        return summaries

    @staticmethod
    def _extract_json(text: str, fallback_key: str = "") -> dict:
        """从 LLM 输出中提取 JSON 代码块"""
        json_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass
        return {"fallback_key": fallback_key, "raw_text": text[:500]}

    def _update_comparison_index(self, all_results: dict):
        """更新对比索引文件"""
        idx = {
            "total_papers": all_results.get("total_papers", 0),
            "papers": all_results.get("papers_analyzed", []),
            "dimensions": {},
            "empirical_aspects": {},
        }

        for dim_key, result in all_results.get("dimensions", {}).items():
            idx["dimensions"][dim_key] = {
                "success": result.get("success", False),
                "paper_count": result.get("paper_count", 0),
                "common_patterns_count": len(
                    result.get("structured", {}).get("common_patterns", [])
                ),
                "md_path": result.get("md_path", ""),
            }

        for emp_key, result in all_results.get("empirical", {}).items():
            idx["empirical_aspects"][emp_key] = {
                "success": result.get("success", False),
                "paper_count": result.get("paper_count", 0),
                "md_path": result.get("md_path", ""),
            }

        idx_path = os.path.join(self._cross_dir, "_comparison_index.json")
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
