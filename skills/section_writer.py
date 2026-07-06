"""
分节写作引擎 — 蓝图驱动的逐节论文写作。

核心设计：
1. 每节写作前注入完整的 PaperBlueprint 上下文
2. 每节能看到前面已完成的章节（避免内容断裂）
3. 每节遵循 section_contract 的"写作合同"约束
4. 每节写作后自动质量自检

流程：
  SectionWriter.generate_blueprint()   → paper_blueprint.json
  SectionWriter.write_all_sections()   → 逐节生成 6 个 section .md 文件
  SectionWriter.assemble_full_paper()  → 拼接为完整论文
"""

from __future__ import annotations
import os
import json
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import asdict

from skills.base import BaseSkill
from skills.llm_client import LlmClient, dataclass_to_json_schema
from skills.schemas import (
    PaperBlueprint, SectionContract, HypothesisBlueprint,
    VariableMapEntry, CitationContract, CrossSectionDependency,
    dataclass_to_dict, dict_to_dataclass, compute_quality_score,
    build_blueprint_from_summaries,
)
from skills.quality_gate import QualityGate


class SectionWriter(BaseSkill):
    """
    蓝图驱动的分节写作引擎。

    使用方式：
      sw = SectionWriter()
      blueprint = sw.generate_blueprint(...)              # Step 5
      sections = sw.write_all_sections(blueprint, ...)    # Step 6a-6e
      full_paper = sw.assemble_full_paper(sections)       # 拼接
    """

    # 节定义：(section_id, prompt_template, 依赖的维度分析)
    SECTIONS = [
        ("section_1_intro",      "01_introduction.txt",          ["01"]),
        ("section_2_theory",     "02_theory_hypothesis.txt",     ["02"]),
        ("section_3_design",     "03_research_design.txt",       ["03", "04", "05"]),
        ("section_5_results",    "05_empirical_results.txt",     ["06", "07", "08", "09", "10"]),
        ("section_6_conclusion", "06_conclusion.txt",            ["11"]),
    ]

    # 人类可读的节标题
    SECTION_TITLES = {
        "section_1_intro": "引言",
        "section_2_theory": "理论分析与研究假设",
        "section_3_design": "研究设计",
        "section_5_results": "实证结果与分析",
        "section_6_conclusion": "结论与政策建议",
    }

    def __init__(self):
        super().__init__(name="SectionWriter", description="蓝图驱动的分节论文写作引擎")
        self.llm = LlmClient()
        self._prompts_dir = os.path.join(
            os.path.abspath("references/prompts"), "section_writing"
        )
        self._output_dir = os.path.abspath("workspace/writing")

    def execute(self, action: str, **kwargs):
        if action == "generate_blueprint":
            return self.generate_blueprint(**kwargs)
        elif action == "write_all_sections":
            return self.write_all_sections(**kwargs)
        elif action == "write_single_section":
            return self.write_single_section(**kwargs)
        else:
            raise NotImplementedError(f"未实现: {action}")

    # ═══════════════════════════════════════════════════════════
    # Step 5: 生成论文蓝图
    # ═══════════════════════════════════════════════════════════

    def generate_blueprint(
        self,
        paper_summaries: List[Dict] = None,
        cross_synthesis: Dict = None,
        empirical_results: List[Dict] = None,
        regression_results: str = "",
        topic_info: str = "",
        hypothesis_info: str = "",
        model_info: str = "",
        variable_info: str = "",
        backend: str = None,
        model: str = None,
    ) -> Dict:
        """
        汇总全部分析数据，生成 PaperBlueprint JSON。

        这是从"分析阶段"到"写作阶段"的桥梁：
        将所有论文的散装分析结果转化为一篇新论文的精确写作约束。
        """
        print(f"\n[{self.name}] ╔══════════════════════════════════════╗")
        print(f"[{self.name}] ║  Step 5: 生成论文写作蓝图              ║")
        print(f"[{self.name}] ╚══════════════════════════════════════╝")

        # 加载蓝图 prompt 模板
        blueprint_prompt_path = os.path.join(self._prompts_dir, "00_blueprint.txt")
        if not os.path.exists(blueprint_prompt_path):
            # 回退：使用内联 prompt
            blueprint_prompt = self._build_inline_blueprint_prompt(
                paper_summaries, cross_synthesis, empirical_results,
                topic_info, hypothesis_info, model_info, variable_info,
                regression_results,
            )
        else:
            with open(blueprint_prompt_path, "r", encoding="utf-8") as f:
                template = f.read()

            # 构建 prompt 数据
            prompt_data = build_blueprint_from_summaries(
                paper_summaries, cross_synthesis, empirical_results,
                topic_info, hypothesis_info, model_info, variable_info,
            )

            user_selections = (
                f"【选题】{topic_info[:2000]}\n\n"
                f"【假设】{hypothesis_info[:2000]}\n\n"
                f"【模型】{model_info[:2000]}\n\n"
                f"【变量】{variable_info[:2000]}"
            )

            all_summaries_text = json.dumps(
                [self._summarize_paper(ps) for ps in (paper_summaries or [])],
                ensure_ascii=False, indent=2,
            )

            cross_text = json.dumps(cross_synthesis or {}, ensure_ascii=False, indent=2)[:5000]
            emp_text = json.dumps(
                [{"title": er.get("title", ""), "json": er.get("json", {})}
                 for er in (empirical_results or [])],
                ensure_ascii=False, indent=2,
            )[:5000]

            blueprint_prompt = (template
                .replace("{user_selections}", user_selections)
                .replace("{all_paper_summaries}", all_summaries_text[:8000])
                .replace("{cross_synthesis_data}", cross_text)
                .replace("{empirical_summary}", emp_text)
                .replace("{regression_results}", regression_results[:3000] or "（尚无实际回归结果）"))

        print(f"[{self.name}] 蓝图 Prompt: {len(blueprint_prompt)} 字符")

        # 用 structured_output 强制生成合规 JSON
        output_schema = dataclass_to_json_schema(PaperBlueprint)
        gate = QualityGate(threshold=0.35)

        try:
            blueprint_dict = self.llm.structured_output(
                prompt=blueprint_prompt,
                output_schema=output_schema,
                system_prompt="你是一位经济学博士生导师。请基于所有分析材料，生成精确的论文写作蓝图JSON。每个字段必须填写，假设必须可追溯到来源论文。",
                backend=backend,
                model=model,
                max_tokens=8000,
                max_retries=3,
                quality_validator=gate.make_validator("blueprint"),
            )
        except Exception as e:
            print(f"[{self.name}] 蓝图生成失败: {e}")
            return {"success": False, "error": str(e)}

        # 保存蓝图
        os.makedirs(self._output_dir, exist_ok=True)
        blueprint_path = os.path.join(self._output_dir, "paper_blueprint.json")
        with open(blueprint_path, "w", encoding="utf-8") as f:
            json.dump(blueprint_dict, f, ensure_ascii=False, indent=2)

        # 计算质量分
        score = compute_quality_score(blueprint_dict)
        blueprint_dict["quality_score"] = score

        print(f"[{self.name}] 蓝图生成完成 → {blueprint_path}")
        print(f"[{self.name}]   假设: {len(blueprint_dict.get('hypotheses', []))} 条")
        print(f"[{self.name}]   变量: {len(blueprint_dict.get('variable_map', []))} 个")
        print(f"[{self.name}]   跨节依赖: {len(blueprint_dict.get('cross_section_dependencies', []))} 条")
        print(f"[{self.name}]   质量分: {score:.2f}")

        return {
            "success": True,
            "blueprint": blueprint_dict,
            "path": blueprint_path,
            "quality_score": score,
        }

    # ═══════════════════════════════════════════════════════════
    # Step 6a-6e: 逐节撰写
    # ═══════════════════════════════════════════════════════════

    def write_all_sections(
        self,
        blueprint: Dict,
        paper_summaries: List[Dict] = None,
        cross_synthesis: Dict = None,
        section_analyses: Dict[str, Dict] = None,
        regression_results: str = "",
        backend: str = None,
        model: str = None,
    ) -> Dict:
        """
        按 Blueprint 逐节撰写完论文。

        :param blueprint: PaperBlueprint dict
        :param paper_summaries: 全部论文的 _paper_summary.json 列表
        :param cross_synthesis: 跨论文对比数据
        :param section_analyses: {paper_title: {section_key: analysis_json}}
        :param regression_results: 实际回归结果文本
        :return: {"sections": {section_id: {"md": ..., "path": ...}}, "success": True}
        """
        print(f"\n[{self.name}] ╔══════════════════════════════════════╗")
        print(f"[{self.name}] ║  Step 6: 逐节撰写论文                  ║")
        print(f"[{self.name}] ╚══════════════════════════════════════╝")

        completed_sections = {}  # section_id → full_text
        section_results = {}

        for section_id, prompt_file, _dimension_keys in self.SECTIONS:
            section_title = self.SECTION_TITLES.get(section_id, section_id)
            print(f"\n[{self.name}] 撰写: {section_title} ...")

            result = self.write_single_section(
                section_id=section_id,
                blueprint=blueprint,
                completed_sections=completed_sections,
                paper_summaries=paper_summaries,
                cross_synthesis=cross_synthesis,
                section_analyses=section_analyses,
                regression_results=regression_results,
                backend=backend,
                model=model,
            )

            if result.get("success"):
                completed_sections[section_id] = result["markdown"]
                section_results[section_id] = result
                print(f"  [{section_id}] ✓ → {result['path']} ({len(result['markdown'])} 字符)")
            else:
                print(f"  [{section_id}] ✗ 失败: {result.get('error', '')}")

        # 保存所有节
        all_sections_path = os.path.join(self._output_dir, "sections")
        os.makedirs(all_sections_path, exist_ok=True)

        for section_id, text in completed_sections.items():
            section_path = os.path.join(all_sections_path, f"{section_id}.md")
            with open(section_path, "w", encoding="utf-8") as f:
                f.write(text)

        success_count = sum(1 for r in section_results.values() if r.get("success"))
        print(f"\n[{self.name}] 逐节写作完成: {success_count}/{len(self.SECTIONS)} 节成功")

        return {
            "success": success_count > 0,
            "sections": section_results,
            "completed": list(completed_sections.keys()),
            "all_sections_dir": all_sections_path,
        }

    def write_single_section(
        self,
        section_id: str,
        blueprint: Dict,
        completed_sections: Dict[str, str] = None,
        paper_summaries: List[Dict] = None,
        cross_synthesis: Dict = None,
        section_analyses: Dict[str, Dict] = None,
        regression_results: str = "",
        backend: str = None,
        model: str = None,
    ) -> Dict:
        """
        撰写单个章节。核心方法。

        :param section_id: "section_1_intro" / "section_2_theory" / ...
        :param blueprint: PaperBlueprint dict
        :param completed_sections: 已完成的章节 {section_id: markdown_text}
        :param paper_summaries: 全部论文摘要
        :param cross_synthesis: 跨论文对比数据
        :param section_analyses: 各维度分析 JSON
        :param regression_results: 实际回归结果
        """
        completed_sections = completed_sections or {}

        # 1. 加载对应的 prompt 模板
        _, prompt_file, dimension_keys = next(
            (s for s in self.SECTIONS if s[0] == section_id),
            (section_id, "01_introduction.txt", []),
        )
        prompt_path = os.path.join(self._prompts_dir, prompt_file)

        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
        else:
            # 回退到内联 prompt
            template = self._build_inline_section_prompt(section_id, blueprint)

        # 2. 构建 prompt 变量
        prompt_vars = self._build_section_prompt_vars(
            section_id=section_id,
            blueprint=blueprint,
            completed_sections=completed_sections,
            paper_summaries=paper_summaries,
            cross_synthesis=cross_synthesis,
            section_analyses=section_analyses,
            regression_results=regression_results,
        )

        # 3. 填充模板
        full_prompt = template
        for key, value in prompt_vars.items():
            full_prompt = full_prompt.replace("{" + key + "}", str(value)[:8000])

        print(f"    Prompt: {len(full_prompt)} 字符")

        # 4. 调用 LLM
        try:
            section_text = self.llm.execute(
                prompt=full_prompt,
                system_prompt=f"你是一位经济学教授，正在撰写论文的「{self.SECTION_TITLES.get(section_id, section_id)}」部分。严格遵循写作合同，确保与前后文逻辑一致。",
                backend=backend,
                model=model,
                max_tokens=5000,
            )
        except Exception as e:
            return {"success": False, "error": str(e), "section_id": section_id}

        # 5. 保存
        section_path = os.path.join(self._output_dir, f"{section_id}.md")
        with open(section_path, "w", encoding="utf-8") as f:
            f.write(f"# {self.SECTION_TITLES.get(section_id, section_id)}\n\n")
            f.write(section_text)

        return {
            "success": True,
            "section_id": section_id,
            "markdown": section_text,
            "path": section_path,
        }

    # ═══════════════════════════════════════════════════════════
    # 完整论文拼接
    # ═══════════════════════════════════════════════════════════

    def assemble_full_paper(
        self,
        sections: Dict[str, Dict],
        blueprint: Dict = None,
        title: str = "",
        abstract: str = "",
    ) -> Dict:
        """
        将分散的章节文件拼接为完整论文。

        :param sections: {section_id: {"markdown": ..., "path": ...}}
        :param blueprint: PaperBlueprint（用于生成摘要和参考文献列表）
        :param title: 论文标题
        :param abstract: 摘要（如为空则从引言自动提取）
        """
        print(f"\n[{self.name}] 拼接完整论文...")

        title = title or (blueprint or {}).get("thesis_title", "未命名论文")

        # 自动生成摘要（如果未提供）
        if not abstract and sections.get("section_1_intro"):
            intro_text = sections["section_1_intro"].get("markdown", "")
            abstract = self._generate_abstract(intro_text, blueprint)

        # 构建参考文献列表
        references = self._build_reference_list(blueprint)

        # 拼接
        parts = [f"# {title}\n\n"]

        if abstract:
            parts.append("## 摘要\n\n")
            parts.append(abstract)
            parts.append("\n\n---\n\n")

        section_order = [
            ("section_1_intro", "一、引言"),
            ("section_2_theory", "二、理论分析与研究假设"),
            ("section_3_design", "三、研究设计"),
            ("section_5_results", "四、实证结果与分析"),
            ("section_6_conclusion", "五、结论与政策建议"),
        ]

        for section_id, section_title in section_order:
            if section_id in sections:
                sec = sections[section_id]
                text = sec.get("markdown", "")
                parts.append(f"## {section_title}\n\n")
                parts.append(text)
                parts.append("\n\n")

        if references:
            parts.append("## 参考文献\n\n")
            parts.append(references)
            parts.append("\n")

        full_text = "".join(parts)

        # 保存
        full_path = os.path.join(self._output_dir, "full_paper.md")
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(full_text)

        print(f"[{self.name}] 完整论文 → {full_path} ({len(full_text)} 字符)")
        return {"success": True, "markdown": full_text, "path": full_path}

    # ═══════════════════════════════════════════════════════════
    # Prompt 变量构建
    # ═══════════════════════════════════════════════════════════

    def _build_section_prompt_vars(
        self,
        section_id: str,
        blueprint: Dict,
        completed_sections: Dict[str, str],
        paper_summaries: List[Dict] = None,
        cross_synthesis: Dict = None,
        section_analyses: Dict[str, Dict] = None,
        regression_results: str = "",
    ) -> Dict[str, str]:
        """为特定节构建所有 Prompt 变量"""

        vars_dict = {}

        # 核心论点（所有节共用）
        vars_dict["thesis_statement"] = blueprint.get("thesis_statement", "")
        vars_dict["research_question"] = blueprint.get("research_question", "")

        # 贡献声明
        contribs = blueprint.get("contribution_claims", [])
        vars_dict["contribution_claims"] = "\n".join(f"{i+1}. {c}" for i, c in enumerate(contribs))

        # 假设蓝图
        hyps = blueprint.get("hypotheses", [])
        if hyps:
            hyp_lines = []
            for h in hyps:
                if isinstance(h, dict):
                    hyp_lines.append(
                        f"**{h.get('id', '')}**: {h.get('claim', '')}\n"
                        f"  - 方向: {h.get('direction', '')} | Y: {h.get('y_var', '')} | X: {h.get('x_var', '')}\n"
                        f"  - 理论基础: {', '.join(h.get('theory_basis', []))}\n"
                        f"  - 来源论文: {', '.join(h.get('theory_source_papers', []))}\n"
                        f"  - 检验方法: {h.get('test_method', '')}\n"
                        f"  - 文献证据: {', '.join(h.get('evidence_from_literature', []))}\n"
                    )
            vars_dict["hypotheses_blueprint"] = "\n".join(hyp_lines)

            # 简版（引言用）
            vars_dict["hypotheses_summary"] = "\n".join(
                f"- {h.get('id', '')}: {h.get('claim', '')}" for h in hyps if isinstance(h, dict)
            )
        else:
            vars_dict["hypotheses_blueprint"] = "（尚未定义假设）"
            vars_dict["hypotheses_summary"] = "（尚未定义假设）"

        # 变量映射表
        var_map = blueprint.get("variable_map", [])
        if var_map:
            var_lines = ["| 符号 | 中文名 | 角色 | 定义 | 数据来源 |",
                         "|------|--------|------|------|---------|"]
            for v in var_map:
                if isinstance(v, dict):
                    var_lines.append(
                        f"| {v.get('symbol', '')} | {v.get('name_cn', '')} | {v.get('role', '')} | "
                        f"{v.get('definition', '')} | {v.get('data_source', '')} |"
                    )
            vars_dict["variable_map"] = "\n".join(var_lines)
        else:
            vars_dict["variable_map"] = "（尚未定义变量表）"

        # 模型蓝图
        vars_dict["model_blueprint"] = (
            f"基准模型: {blueprint.get('baseline_model_form', '')}\n"
            f"估计方法: {blueprint.get('estimation_method', '')}\n"
            f"固定效应: {', '.join(blueprint.get('fixed_effects', []))}\n"
            f"标准误: {blueprint.get('standard_error_type', '')}\n"
            f"识别策略: {blueprint.get('identification_strategy', '')}\n"
            f"内生性处理: {blueprint.get('endogeneity_handling', '')}"
        )

        # 节合同
        contracts = blueprint.get("section_contracts", {})
        section_contract = contracts.get(section_id, {})
        if isinstance(section_contract, dict):
            vars_dict["must_derive"] = "\n".join(f"- {x}" for x in section_contract.get("must_derive", []))
            vars_dict["must_define"] = "\n".join(f"- {x}" for x in section_contract.get("must_define", []))
            vars_dict["must_specify"] = json.dumps(section_contract.get("must_specify", {}), ensure_ascii=False)
            vars_dict["must_report"] = "\n".join(f"- {x}" for x in section_contract.get("must_report", []))
            vars_dict["must_cite"] = "\n".join(f"- {x}" for x in section_contract.get("must_cite", []))
            vars_dict["must_compare"] = "\n".join(f"- {x}" for x in section_contract.get("must_compare", []))
            vars_dict["must_discuss"] = "\n".join(f"- {x}" for x in section_contract.get("must_discuss", []))
            vars_dict["must_echo"] = "\n".join(f"- {x}" for x in section_contract.get("must_echo", []))
            vars_dict["forbidden"] = "\n".join(f"- {x}" for x in section_contract.get("forbidden", []))
        else:
            for key in ["must_derive", "must_define", "must_report", "must_cite",
                       "must_compare", "must_discuss", "must_echo"]:
                vars_dict[key] = ""
            vars_dict["must_specify"] = "{}"
            vars_dict["forbidden"] = ""

        # 前文上下文
        if completed_sections:
            previous_parts = []
            for sec_id, sec_text in completed_sections.items():
                sec_title = self.SECTION_TITLES.get(sec_id, sec_id)
                previous_parts.append(f"### {sec_title}\n\n{sec_text[:3000]}")
            vars_dict["previous_section_text"] = "\n\n---\n\n".join(previous_parts)
            vars_dict["previous_sections_summary"] = self._summarize_sections(completed_sections)
        else:
            vars_dict["previous_section_text"] = "（本文第一节，无前文）"
            vars_dict["previous_sections_summary"] = "（本文第一节）"

        # 全文摘要（结论节用）
        if section_id == "section_6_conclusion":
            vars_dict["full_paper_summary"] = self._summarize_sections(completed_sections, detailed=True)

        # 引用清单
        citation_contracts = blueprint.get("citation_contracts", [])
        if citation_contracts:
            cite_lines = []
            for i, cc in enumerate(citation_contracts):
                if isinstance(cc, dict):
                    cite_lines.append(
                        f"{i+1}. {cc.get('authors_short', '')}. {cc.get('paper_title', '')}. "
                        f"[{cc.get('citation_format_gbt7714', '')}]"
                    )
            vars_dict["citation_list"] = "\n".join(cite_lines)
        else:
            vars_dict["citation_list"] = self._build_citation_list_from_summaries(paper_summaries)

        # 跨论文共性数据
        vars_dict["cross_paper_context"] = self._format_cross_synthesis(cross_synthesis)

        # 维度分析摘要
        _, _, dimension_keys = next(
            (s for s in self.SECTIONS if s[0] == section_id),
            (section_id, "", []),
        )
        vars_dict.update(self._build_dimension_analysis_vars(dimension_keys, paper_summaries, section_analyses))

        # ★ 注入本节要素溯源（Provenance）
        vars_dict["provenance_context"] = self._build_provenance_context(section_id, blueprint)

        # 实际回归结果
        vars_dict["actual_regression_results"] = regression_results or "（尚无实际回归结果）"

        return vars_dict

    # ═══════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _summarize_paper(ps: Dict) -> Dict:
        """提取论文的最小摘要"""
        return {
            "title": ps.get("paper_title", ""),
            "authors": ps.get("authors", ""),
            "source": ps.get("source", ""),
            "keywords": ps.get("keywords", []),
            "abstract_first_200": (ps.get("abstract", "") or "")[:200],
            "sections_completed": ps.get("sections_completed", []),
        }

    @staticmethod
    def _summarize_sections(completed: Dict[str, str], detailed: bool = False) -> str:
        """生成已完成章节的摘要"""
        parts = []
        for sec_id, text in completed.items():
            title = SectionWriter.SECTION_TITLES.get(sec_id, sec_id)
            if detailed:
                parts.append(f"### {title}\n{text[:2000]}")
            else:
                # 提取首段作为摘要
                first_para = text.split("\n\n")[0] if text else ""
                parts.append(f"**{title}**: {first_para[:300]}")
        return "\n\n".join(parts)

    @staticmethod
    def _build_citation_list_from_summaries(paper_summaries: List[Dict] = None) -> str:
        """从论文摘要构建引用清单"""
        if not paper_summaries:
            return "（无可引用论文清单）"
        parts = ["以下论文可以被引用到正文和参考文献中：", ""]
        for i, ps in enumerate(paper_summaries or []):
            title = ps.get("paper_title", "未知")
            authors = ps.get("authors", "未知")
            source = ps.get("source", "未知")
            pub_date = ps.get("pub_date", "未知")
            parts.append(f"{i+1}. {authors}. {title}[J]. {source}, {pub_date}.")
        return "\n".join(parts)

    @staticmethod
    def _format_cross_synthesis(cross_synthesis: Dict = None) -> str:
        """格式化跨论文共性数据为简短文本"""
        if not cross_synthesis:
            return "（无跨论文共性数据）"
        parts = []
        dim_insights = cross_synthesis.get("dimension_insights", {})
        for dim_key, dim_data in list(dim_insights.items())[:5]:
            takeaway = dim_data.get("key_takeaway", "")
            if takeaway:
                parts.append(f"- {dim_key}: {takeaway}")
        emp_insights = cross_synthesis.get("empirical_insights", {})
        for emp_key, emp_data in list(emp_insights.items())[:5]:
            freq = emp_data.get("frequency_table", {})
            if freq:
                top = sorted(freq.items(), key=lambda x: -x[1])[:3]
                parts.append(f"- {emp_key} 频率: {', '.join(f'{k}({v})' for k, v in top)}")
        return "\n".join(parts) if parts else "（无跨论文共性数据）"

    @staticmethod
    def _build_provenance_context(section_id: str, blueprint: Dict) -> str:
        """
        从蓝图的 provenance_map 中提取本节需要的溯源信息，
        格式化为 Prompt 可用的文本块。
        """
        provenance = blueprint.get("provenance_map")
        if not provenance or not isinstance(provenance, dict):
            return "（本蓝图无溯源信息——写作时请参照通用分析材料）"

        elements = provenance.get("elements", {})
        if not elements:
            return "（溯源信息为空）"

        # 使用 ProvenanceMap 的格式化方法
        from skills.schemas import ProvenanceMap
        try:
            pm = ProvenanceMap(
                blueprint_title=blueprint.get("thesis_title", ""),
                elements=elements,
            )
            return pm.format_for_section_prompt(section_id)
        except Exception:
            # 回退：手动格式化
            section_elements = {
                "section_1_intro": ["claim"],
                "section_2_theory": ["hypothesis", "mechanism"],
                "section_3_design": ["variable", "method", "model_spec"],
                "section_5_results": ["hypothesis", "mechanism", "method"],
                "section_6_conclusion": ["claim", "hypothesis"],
            }
            target_types = section_elements.get(section_id, [])
            parts = ["## ★ 本节要素溯源\n"]
            for elem_id, elem in elements.items():
                if isinstance(elem, dict) and elem.get("element_type") in target_types:
                    parts.append(f"### {elem.get('element_label', elem_id)}")
                    for i, src in enumerate(elem.get("sources", [])):
                        if isinstance(src, dict):
                            type_icon = {"bridge": "🔗 跨集群桥梁", "single_paper": "📄 单篇分析",
                                        "cross_paper": "📊 跨论文共性", "empirical": "🔬 实证分析",
                                        "user_input": "✏️ 用户输入"}
                            icon = type_icon.get(src.get("source_type", ""), "❓")
                            parts.append(f"**来源{i+1}** [{icon}] 置信度: {src.get('confidence', '?')}")
                            parts.append(f"  {src.get('source_detail', '')}")
                            if src.get("paper_title"):
                                parts.append(f"  → 论文: {src['paper_title'][:60]}")
                            if src.get("section_key"):
                                parts.append(f"  → 维度: {src['section_key']} ({src.get('section_title', '')})")
                            if src.get("finding_excerpt"):
                                parts.append(f"  → 具体发现: {src['finding_excerpt'][:200]}")
                            if src.get("bridge_theory"):
                                parts.append(f"  → 桥梁理论: {src['bridge_theory']}")
                            if src.get("graft_logic"):
                                parts.append(f"  → 嫁接逻辑: {src['graft_logic'][:200]}")
                            if src.get("cross_frequency"):
                                parts.append(f"  → 频率: {src['cross_frequency']}")
                            if src.get("cross_consensus_level"):
                                parts.append(f"  → 共识度: {src['cross_consensus_level']}")
                        parts.append("")
                    parts.append("")
            return "\n".join(parts) if len(parts) > 1 else "（本节的溯源信息不完整）"

    @staticmethod
    def _build_dimension_analysis_vars(
        dimension_keys: List[str],
        paper_summaries: List[Dict] = None,
        section_analyses: Dict[str, Dict] = None,
    ) -> Dict[str, str]:
        """构建各维度分析的 prompt 变量"""
        result = {}
        for dk in dimension_keys:
            parts = []
            for ps in (paper_summaries or []):
                sections = ps.get("sections", {})
                for sec_key, sec_data in sections.items():
                    if sec_key.startswith(dk):
                        title = ps.get("paper_title", "?")
                        findings = sec_data.get("key_findings", [])
                        gaps = sec_data.get("gaps", [])
                        if findings or gaps:
                            parts.append(f"### {title}\n")
                            if findings:
                                parts.append("关键发现: " + "; ".join(
                                    str(f)[:200] for f in findings[:3]))
                            if gaps:
                                parts.append("空缺: " + "; ".join(
                                    str(g)[:200] for g in gaps[:3]))
            result[f"section_{dk}_analysis"] = "\n".join(parts) if parts else "（无该维度分析数据）"

        # 合并多维度（如 section_03_04_05_analysis）
        if len(dimension_keys) > 1:
            merged = []
            for dk in dimension_keys:
                content = result.get(f"section_{dk}_analysis", "")
                if content and content != "（无该维度分析数据）":
                    merged.append(f"## 维度 {dk}\n{content}")
            merged_key = "section_" + "_".join(dimension_keys) + "_analysis"
            result[merged_key] = "\n\n".join(merged) if merged else "（无该维度分析数据）"

        return result

    def _generate_abstract(self, intro_text: str, blueprint: Dict = None) -> str:
        """从引言自动生成摘要"""
        prompt = (
            f"请基于以下论文引言，撰写一段200-300字的摘要。"
            f"必须包含：研究问题、方法、核心发现、政策含义。\n\n"
            f"【引言】\n{intro_text[:3000]}"
        )
        try:
            return self.llm.execute(
                prompt=prompt,
                system_prompt="你是一位经济学论文编辑，请撰写简洁准确的摘要。",
                max_tokens=500,
            )
        except Exception:
            return ""

    def _build_reference_list(self, blueprint: Dict = None) -> str:
        """构建参考文献列表"""
        if not blueprint:
            return ""
        contracts = blueprint.get("citation_contracts", [])
        if not contracts:
            return ""
        parts = []
        for i, cc in enumerate(contracts):
            if isinstance(cc, dict):
                parts.append(f"[{i+1}] {cc.get('citation_format_gbt7714', cc.get('paper_title', ''))}")
        return "\n".join(parts)

    def _build_inline_blueprint_prompt(
        self,
        paper_summaries, cross_synthesis, empirical_results,
        topic_info, hypothesis_info, model_info, variable_info,
        regression_results,
    ) -> str:
        """回退：当 00_blueprint.txt 不存在时使用的内联 prompt"""
        return f"""你是一位经济学博士生导师。请基于以下全部分析材料，生成一个精确的论文写作蓝图JSON。

【用户选择】
选题: {topic_info[:2000]}
假设: {hypothesis_info[:2000]}
模型: {model_info[:2000]}
变量: {variable_info[:2000]}

【论文分析摘要】
{json.dumps([self._summarize_paper(ps) for ps in (paper_summaries or [])], ensure_ascii=False)[:6000]}

【跨论文共性】
{json.dumps(cross_synthesis or {}, ensure_ascii=False)[:3000]}

【实证结果】
{regression_results[:2000] or '（尚无）'}

【输出要求】
生成 PaperBlueprint JSON，包含 thesis_title, thesis_statement, hypotheses, variable_map,
section_contracts, citation_contracts, cross_section_dependencies。
每条假设必须可追溯到来源论文，每个变量必须有统一定义。"""

    def _build_inline_section_prompt(self, section_id: str, blueprint: Dict) -> str:
        """回退：当节 prompt 模板不存在时"""
        return """你是一位经济学教授。请基于以下约束撰写本节内容。

{thesis_statement}
{previous_section_text}
合同要求: {must_derive} {must_cite}
引用清单: {citation_list}"""
