"""
一致性审查器 — Pass 3 的自动化交叉校验。

设计原则：
1. 结构化规则（确定性检查）→ 无需 LLM，秒级完成
2. LLM 语义检查（语义一致性）→ 聚焦、小 Prompt、可并行
3. 输出问题清单（不自动修改）→ 由修正步骤定点处理

使用方式：
  auditor = ConsistencyAuditor()
  report = auditor.audit(sections, blueprint)
  if report.errors > 0:
      # 调用 auditor.suggest_fixes() 生成修正建议
"""

from __future__ import annotations
import os
import json
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from skills.base import BaseSkill
from skills.llm_client import LlmClient
from skills.schemas import (
    ConsistencyFinding, ConsistencyReport,
    CrossSectionDependency,
)


class ConsistencyAuditor(BaseSkill):
    """
    论文一致性审查器。

    三级审查：
    Level 1 - 结构规则（确定性，无需 LLM）
    Level 2 - 引用完整性（确定性 + 简单文本匹配）
    Level 3 - 语义一致性（需 LLM，但每个检查聚焦到 2 个小节）

    使用方式：
      auditor = ConsistencyAuditor()
      report = auditor.audit(sections, blueprint)
    """

    # ═══════════════════════════════════════════════════════════
    # Level 1: 结构化规则（零 LLM 调用）
    # ═══════════════════════════════════════════════════════════

    LEVEL1_RULES = [
        {
            "id": "L1_all_variables_defined",
            "description": "变量映射表中的所有变量符号都出现在正文中",
            "severity": "error",
        },
        {
            "id": "L1_all_citations_used",
            "description": "引用合同中的每篇论文都在正文中至少被引用1次",
            "severity": "error",
        },
        {
            "id": "L1_hypothesis_coverage",
            "description": "每条假设在实证结果节有对应的检验",
            "severity": "error",
        },
        {
            "id": "L1_section_contract_fulfilled",
            "description": "每节的 must_cite 论文都在该节正文中出现",
            "severity": "warning",
        },
        {
            "id": "L1_variable_symbol_consistency",
            "description": "变量符号在全文中保持一致（如 Livability 不应在某处变为 Liva）",
            "severity": "warning",
        },
        {
            "id": "L1_hypothesis_id_consistency",
            "description": "假设编号在全文中一致（H1/H2/H3 不重号、不漏号）",
            "severity": "error",
        },
        {
            "id": "L1_forbidden_content",
            "description": "各节没有出现 section_contract 中 forbidden 的内容",
            "severity": "warning",
        },
    ]

    # ═══════════════════════════════════════════════════════════
    # Level 3: 语义一致性（需要 LLM，每检查聚焦 2 个小节）
    # ═══════════════════════════════════════════════════════════

    LEVEL3_CHECKS = [
        {
            "id": "L3_contribution_echo",
            "description": "结论中的贡献声明是否与引言一致",
            "sections": ["section_1_intro", "section_6_conclusion"],
            "prompt": """你是一位学术审查者。请对比以下两段文本：

【引言中的贡献声明】
{section_a}

【结论中的贡献总结】
{section_b}

请逐条检查：
1. 引言中声明的每条贡献是否在结论中被回扣？
2. 结论中是否有引言未声明的"意外贡献"？
3. 两者的措辞是否有矛盾？

输出格式（JSON）：
```json
{{
  "matched": 0,
  "unmatched_intro_contributions": ["引言有但结论未回扣的"],
  "unexpected_conclusion_claims": ["结论有但引言未声明的"],
  "contradictions": [{{"intro": "引言中的表述", "conclusion": "结论中的表述", "contradiction": "矛盾所在"}}],
  "is_consistent": true/false
}}
```""",
        },
        {
            "id": "L3_hypothesis_result_match",
            "description": "实证结果中的检验是否与理论部分的假设一一对应",
            "sections": ["section_2_theory", "section_5_results"],
            "prompt": """你是一位学术审查者。请对比以下两段文本：

【理论部分提出的假设】
{section_a}

【实证结果中的检验】
{section_b}

请逐条检查：
1. 理论部分提出的每条假设（H1, H2, H3...）是否在实证结果中有对应的检验？
2. 实证结果中检验的假设是否都在理论部分被提出过？
3. 假设的方向性预测与实际结果方向是否一致？
4. 如有不一致，论文是否进行了解释？

输出格式（JSON）：
```json
{{
  "hypotheses_tested": ["H1", "H2"],
  "hypotheses_not_tested": ["H3"],
  "direction_mismatches": [{{"hypothesis": "H2", "expected": "正向", "actual": "负向", "explained": true/false}}],
  "untested_results": ["实证中有但理论未提出的检验"],
  "is_consistent": true/false
}}
```""",
        },
        {
            "id": "L3_mechanism_logic_chain",
            "description": "机制检验是否能追溯到理论推导",
            "sections": ["section_2_theory", "section_5_results"],
            "prompt": """你是一位学术审查者。请追踪论文的机制逻辑链条。

【理论推导中的机制】
{section_a}

【实证结果中的机制检验】
{section_b}

请检查：
1. 实证检验的每条机制渠道是否有对应的理论推导？
2. 理论推导的每条机制是否都有实证检验？未检验的是否说明了原因？
3. 机制变量的定义在理论和实证部分是否一致？
4. 中介效应检验方法的选用是否与理论推导的因果结构匹配？

输出格式（JSON）：
```json
{{
  "mechanisms_tested": ["机制1"],
  "mechanisms_not_tested": ["机制2"],
  "logic_gaps": [{{"description": "逻辑断裂点描述", "location": "section_2_theory|section_5_results"}}],
  "variable_definition_mismatches": [],
  "is_consistent": true/false
}}
```""",
        },
        {
            "id": "L3_model_variable_alignment",
            "description": "研究设计中定义的变量是否与变量映射表一致",
            "sections": ["section_3_design", "_variable_map"],
            "special": True,  # 特殊：section_b 来自蓝图而非已写作的节
            "prompt": """你是一位学术审查者。请检查变量定义的一致性。

【研究设计中的变量定义】
{section_a}

【变量映射表（蓝图中的统一定义）】
{section_b}

请检查：
1. 研究设计中使用的每个变量是否在变量映射表中有定义？
2. 变量的符号、定义、测度方式是否与映射表一致？
3. 是否有使用映射表之外的变量？这些变量是否被正确引入？

输出格式（JSON）：
```json
{{
  "variables_matched": 0,
  "variables_undefined": ["设计中使用但未在映射表中的变量"],
  "definition_mismatches": [{{"variable": "X", "design_definition": "...", "map_definition": "..."}}],
  "is_consistent": true/false
}}
```""",
        },
    ]

    def __init__(self):
        super().__init__(name="ConsistencyAuditor", description="论文一致性交叉审查器")
        self.llm = LlmClient()

    def execute(self, action: str, **kwargs):
        if action == "audit":
            return self.audit(**kwargs)
        elif action == "suggest_fixes":
            return self.suggest_fixes(**kwargs)
        else:
            raise NotImplementedError(f"未实现: {action}")

    # ═══════════════════════════════════════════════════════════
    # 主审查流程
    # ═══════════════════════════════════════════════════════════

    def audit(
        self,
        sections: Dict[str, Dict],
        blueprint: Dict,
        backend: str = None,
        model: str = None,
    ) -> Dict:
        """
        运行全部一致性审查。

        :param sections: {section_id: {"markdown": str, "path": str}}
        :param blueprint: PaperBlueprint dict
        :return: ConsistencyReport dict
        """
        print(f"\n[{self.name}] ╔══════════════════════════════════════╗")
        print(f"[{self.name}] ║  Pass 3: 一致性交叉审查                ║")
        print(f"[{self.name}] ╚══════════════════════════════════════╝")

        all_findings = []

        # ── Level 0: 溯源完整性 ──
        print(f"\n[{self.name}] Level 0: 溯源链完整性检查...")
        l0_findings = self._run_level0(blueprint)
        all_findings.extend(l0_findings)
        print(f"[{self.name}]   Level 0: {len(l0_findings)} 个发现")

        # ── Level 1: 结构化规则 ──
        print(f"\n[{self.name}] Level 1: 结构化规则检查...")
        l1_findings = self._run_level1(sections, blueprint)
        all_findings.extend(l1_findings)
        print(f"[{self.name}]   Level 1: {len(l1_findings)} 个发现")

        # ── Level 2: 引用完整性 ──
        print(f"[{self.name}] Level 2: 引用完整性检查...")
        l2_findings = self._run_level2(sections, blueprint)
        all_findings.extend(l2_findings)
        print(f"[{self.name}]   Level 2: {len(l2_findings)} 个发现")

        # ── Level 3: 语义一致性（LLM）──
        print(f"[{self.name}] Level 3: 语义一致性检查（LLM）...")
        l3_findings = self._run_level3(sections, blueprint, backend, model)
        all_findings.extend(l3_findings)
        print(f"[{self.name}]   Level 3: {len(l3_findings)} 个发现")

        # 组装报告
        errors = [f for f in all_findings if f.get("severity") == "error"]
        warnings = [f for f in all_findings if f.get("severity") == "warning"]
        infos = [f for f in all_findings if f.get("severity") == "info"]

        report = {
            "paper_title": (blueprint or {}).get("thesis_title", ""),
            "generated_at": datetime.now().isoformat(),
            "total_checks": len(self.LEVEL1_RULES) + 1 + len(self.LEVEL3_CHECKS),
            "passed": len([f for f in all_findings if f.get("fixed")]),
            "warnings": len(warnings),
            "errors": len(errors),
            "findings": all_findings,
            "overall_verdict": "通过" if len(errors) == 0 else ("有警告" if len(warnings) > 0 and len(errors) == 0 else "不通过"),
            "sections_reviewed": list(sections.keys()),
            "sections_needing_revision": list(set(
                f.get("source_section", "") for f in errors + warnings if f.get("source_section")
            )),
        }

        # 保存报告
        report_path = os.path.join(
            os.path.abspath("workspace/writing"), "consistency_audit.json"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n[{self.name}] ╔══════════════════════════════════════════╗")
        print(f"[{self.name}] ║  审查完成: {report['overall_verdict']}                          ║")
        print(f"[{self.name}] ║  Errors: {len(errors)} | Warnings: {len(warnings)} | Info: {len(infos)}     ║")
        print(f"[{self.name}] ║  需修订节: {report['sections_needing_revision']}")
        print(f"[{self.name}] ╚══════════════════════════════════════════╝")

        return report

    # ═══════════════════════════════════════════════════════════
    # Level 0: 溯源链完整性检查
    # ═══════════════════════════════════════════════════════════

    def _run_level0(self, blueprint: Dict) -> List[Dict]:
        """
        检查蓝图中每个关键要素的溯源链是否完整。

        每个假设/变量/方法/机制/贡献声明必须有 ≥1 个来源。
        关键要素（假设、核心变量、识别策略）应有 ≥2 个来源。
        """
        findings = []
        provenance = blueprint.get("provenance_map")

        if not provenance:
            findings.append(self._make_finding(
                "L0_no_provenance", "warning",
                "蓝图缺少 provenance_map——全链路溯源追踪未启用。"
                "分段撰写时 LLM 无法知道每个要素的来源，可能产生无据论断。",
                source_section="（蓝图）",
                suggested_fix="在生成蓝图时启用溯源追踪（修改 00_blueprint.txt prompt）",
            ))
            return findings

        elements = provenance.get("elements", {})
        if not elements:
            findings.append(self._make_finding(
                "L0_empty_provenance", "warning",
                "provenance_map 存在但为空——所有要素都没有来源标注。",
                source_section="（蓝图）",
                suggested_fix="重新生成蓝图，确保 LLM 为每个关键要素标注来源",
            ))
            return findings

        # 检查每个要素
        critical_types = {"hypothesis", "variable", "method"}
        for elem_id, elem in elements.items():
            if not isinstance(elem, dict):
                continue

            elem_type = elem.get("element_type", "")
            sources = elem.get("sources", [])

            if not sources:
                severity = "error" if elem_type in critical_types else "warning"
                findings.append(self._make_finding(
                    "L0_missing_sources", severity,
                    f"要素「{elem.get('element_label', elem_id)}」({elem_type}) 无任何溯源来源",
                    source_section="（蓝图）",
                    suggested_fix=f"为该要素标注至少1个来源（来自哪篇论文的哪个分析维度）",
                ))
                continue

            # 关键要素至少2个来源
            if elem_type in critical_types and len(sources) < 2:
                findings.append(self._make_finding(
                    "L0_insufficient_sources", "info",
                    f"关键要素「{elem.get('element_label', elem_id)}」({elem_type}) 仅有 {len(sources)} 个来源（建议≥2）",
                    source_section="（蓝图）",
                    suggested_fix="考虑从跨论文共性或实证分析中补充额外来源",
                ))

            # 检查来源质量
            for src in sources:
                if isinstance(src, dict) and src.get("confidence") == "低":
                    findings.append(self._make_finding(
                        "L0_low_confidence_source", "warning",
                        f"要素「{elem.get('element_label', elem_id)}」的1个来源置信度为「低」: {src.get('source_detail', '')[:80]}",
                        source_section="（蓝图）",
                        suggested_fix="寻找更高置信度的替代来源，或标注此要素的不确定性",
                    ))

        # 统计
        total = len(elements)
        with_sources = sum(1 for e in elements.values()
                          if isinstance(e, dict) and e.get("sources"))
        completeness = round(with_sources / max(total, 1), 2)

        if completeness < 0.8:
            findings.append(self._make_finding(
                "L0_low_completeness", "warning",
                f"溯源完整度仅 {completeness:.0%} ({with_sources}/{total} 个要素有来源)",
                source_section="（蓝图）",
                suggested_fix="为缺失来源的要素补充溯源信息",
            ))

        return findings

    # ═══════════════════════════════════════════════════════════
    # Level 1: 结构化规则
    # ═══════════════════════════════════════════════════════════

    def _run_level1(self, sections: Dict[str, Dict], blueprint: Dict) -> List[Dict]:
        """运行所有 Level 1 确定性规则"""
        findings = []

        # 合并所有正文文本
        full_text = "\n\n".join(
            sec.get("markdown", "") for sec in sections.values()
        )

        # L1_all_variables_defined
        var_map = blueprint.get("variable_map", [])
        for var in var_map:
            if isinstance(var, dict):
                symbol = var.get("symbol", "")
                if symbol and symbol not in full_text:
                    findings.append(self._make_finding(
                        "L1_all_variables_defined", "error",
                        f"变量符号「{symbol}」未在正文中出现",
                        source_section="section_3_design",
                        suggested_fix=f"在研究设计中定义变量「{symbol}」，或在全文统一使用该符号",
                    ))

        # L1_all_citations_used
        citation_contracts = blueprint.get("citation_contracts", [])
        for cc in citation_contracts:
            if isinstance(cc, dict):
                title = cc.get("paper_title", "")
                authors = cc.get("authors_short", "")
                if title and title[:20] not in full_text and authors not in full_text:
                    findings.append(self._make_finding(
                        "L1_all_citations_used", "error",
                        f"引用合同中的论文「{authors}」未在正文中出现",
                        source_section="（全文）",
                        suggested_fix=f"在适当位置引用 {authors}，或从引用合同中移除",
                    ))

        # L1_hypothesis_coverage
        hyps = blueprint.get("hypotheses", [])
        results_section = sections.get("section_5_results", {}).get("markdown", "")
        for h in hyps:
            if isinstance(h, dict):
                hid = h.get("id", "")
                if hid and hid not in results_section:
                    findings.append(self._make_finding(
                        "L1_hypothesis_coverage", "error",
                        f"假设 {hid} 在实证结果节中未被检验或提及",
                        source_section="section_5_results",
                        suggested_fix=f"在实证结果中添加对 {hid} 的检验结果，或在理论部分说明该假设为何未被检验",
                    ))

        # L1_variable_symbol_consistency
        symbols = [v.get("symbol", "") for v in var_map if isinstance(v, dict) and v.get("symbol")]
        for sym in symbols:
            if len(sym) > 2:
                # 检查是否有近似但不完全一致的变体（仅 ASCII 字母数字下划线）
                variants = re.findall(rf'\b{re.escape(sym)}[a-zA-Z0-9_]*\b', full_text)
                unique_variants = set(v for v in variants if v != sym)
                if unique_variants:
                    findings.append(self._make_finding(
                        "L1_variable_symbol_consistency", "warning",
                        f"变量符号「{sym}」在文中有变体: {unique_variants}",
                        source_section="section_3_design",
                        suggested_fix=f"统一使用「{sym}」，替换变体 {unique_variants}",
                    ))

        # L1_hypothesis_id_consistency
        hyp_ids = [h.get("id", "") for h in hyps if isinstance(h, dict)]
        if hyp_ids:
            expected = [f"H{i+1}" for i in range(len(hyp_ids))]
            if sorted(hyp_ids) != sorted(expected):
                findings.append(self._make_finding(
                    "L1_hypothesis_id_consistency", "error",
                    f"假设编号不一致: 实际={hyp_ids}, 期望={expected}",
                    source_section="section_2_theory",
                    suggested_fix=f"将假设编号规范化为 {expected}",
                ))

        # L1_section_contract_fulfilled
        contracts = blueprint.get("section_contracts", {})
        for sec_id, contract in contracts.items():
            if isinstance(contract, dict):
                must_cite = contract.get("must_cite", [])
                sec_text = sections.get(sec_id, {}).get("markdown", "")
                for cite in must_cite:
                    if cite and cite[:10] not in sec_text:
                        findings.append(self._make_finding(
                            "L1_section_contract_fulfilled", "warning",
                            f"合同要求 {sec_id} 引用「{cite}」，但未在该节找到",
                            source_section=sec_id,
                            suggested_fix=f"在 {sec_id} 中引用 {cite}，或更新合同",
                        ))

        # L1_forbidden_content
        for sec_id, contract in contracts.items():
            if isinstance(contract, dict):
                forbidden = contract.get("forbidden", [])
                sec_text = sections.get(sec_id, {}).get("markdown", "")
                for fb in forbidden:
                    if fb and fb in sec_text:
                        findings.append(self._make_finding(
                            "L1_forbidden_content", "warning",
                            f"合同禁止的内容「{fb}」出现在 {sec_id} 中",
                            source_section=sec_id,
                            suggested_fix=f"从 {sec_id} 中删除或改写涉及「{fb}」的内容",
                        ))

        return findings

    # ═══════════════════════════════════════════════════════════
    # Level 2: 引用完整性
    # ═══════════════════════════════════════════════════════════

    def _run_level2(self, sections: Dict[str, Dict], blueprint: Dict) -> List[Dict]:
        """检查引用格式和完整性"""
        findings = []

        full_text = "\n".join(sec.get("markdown", "") for sec in sections.values())

        # 提取文中所有括号引用
        # 中文: （张三, 2023） / （张三和李四, 2023）
        # 英文: (Smith, 2020) / (Smith & Jones, 2020)
        cn_citations = re.findall(r'[（(]([^）)]{2,20}?\d{4})[）)]', full_text)
        en_citations = re.findall(r'\(([A-Z][a-z]+(?:\s*&\s*[A-Z][a-z]+)?,\s*\d{4})\)', full_text)

        all_cites = set(cn_citations + en_citations)

        # 检查每个引用是否在引用合同中有对应
        citation_contracts = blueprint.get("citation_contracts", [])
        for cite in all_cites:
            found = False
            for cc in citation_contracts:
                if isinstance(cc, dict):
                    authors = cc.get("authors_short", "")
                    if cite in authors or authors in cite:
                        found = True
                        break
            if not found:
                findings.append(self._make_finding(
                    "L2_unregistered_citation", "warning",
                    f"文中引用「{cite}」未在引用合同中注册",
                    source_section="（全文）",
                    suggested_fix=f"在引用合同中添加「{cite}」的条目，或确认该引用是否真实存在",
                ))

        # 检查引用合同中的论文是否都有文中引用
        for cc in citation_contracts:
            if isinstance(cc, dict):
                authors = cc.get("authors_short", "")
                if authors and not any(authors in c for c in all_cites):
                    findings.append(self._make_finding(
                        "L2_unused_contract_citation", "info",
                        f"引用合同中的「{authors}」在正文中无引用",
                        source_section="（全文）",
                        suggested_fix=f"在正文中引用 {authors}，或从引用合同中移除",
                    ))

        return findings

    # ═══════════════════════════════════════════════════════════
    # Level 3: 语义一致性（LLM）
    # ═══════════════════════════════════════════════════════════

    def _run_level3(
        self,
        sections: Dict[str, Dict],
        blueprint: Dict,
        backend: str = None,
        model: str = None,
    ) -> List[Dict]:
        """运行语义一致性 LLM 检查"""
        findings = []

        for check in self.LEVEL3_CHECKS:
            check_id = check["id"]
            section_a_key = check["sections"][0]
            section_b_key = check["sections"][1]

            print(f"    [{check_id}] ...")

            # 获取 section A 文本
            if check.get("special") and section_b_key == "_variable_map":
                section_a_text = sections.get(section_a_key, {}).get("markdown", "")[:3000]
                section_b_text = json.dumps(blueprint.get("variable_map", []), ensure_ascii=False, indent=2)[:3000]
            else:
                section_a_text = sections.get(section_a_key, {}).get("markdown", "")[:3000]
                section_b_text = sections.get(section_b_key, {}).get("markdown", "")[:3000]

            if not section_a_text.strip():
                findings.append(self._make_finding(
                    check_id, "info", f"节 {section_a_key} 为空，跳过检查",
                    source_section=section_a_key,
                ))
                continue
            if not section_b_text.strip():
                findings.append(self._make_finding(
                    check_id, "info", f"节 {section_b_key} 为空，跳过检查",
                    source_section=section_b_key,
                ))
                continue

            # 构建 prompt
            prompt = check["prompt"].replace("{section_a}", section_a_text)\
                                    .replace("{section_b}", section_b_text)

            # 调用 LLM 做语义检查
            try:
                result = self.llm.structured_output(
                    prompt=prompt,
                    output_schema={
                        "type": "object",
                        "properties": {
                            "is_consistent": {"type": "boolean"},
                            "findings": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string"},
                                        "description": {"type": "string"},
                                        "severity": {"type": "string", "enum": ["error", "warning", "info"]},
                                    },
                                },
                            },
                        },
                    },
                    system_prompt="你是一位学术论文审查专家。请精确检查两段文本的逻辑一致性。",
                    backend=backend,
                    model=model,
                    max_tokens=2000,
                    max_retries=1,
                )
            except Exception as e:
                findings.append(self._make_finding(
                    check_id, "warning", f"LLM 检查失败: {e}",
                    source_section=section_a_key,
                ))
                continue

            if not result.get("is_consistent", True):
                for f in result.get("findings", []):
                    findings.append(self._make_finding(
                        check_id,
                        f.get("severity", "warning"),
                        f.get("description", ""),
                        source_section=section_a_key,
                        target_section=section_b_key,
                    ))
            else:
                # 记录通过的检查
                pass  # 只记录问题

        return findings

    # ═══════════════════════════════════════════════════════════
    # 修正建议
    # ═══════════════════════════════════════════════════════════

    def suggest_fixes(
        self,
        audit_report: Dict,
        sections: Dict[str, Dict],
        blueprint: Dict,
        backend: str = None,
        model: str = None,
    ) -> Dict:
        """
        为审查发现的问题生成具体修正方案。

        返回 {section_id: [{"finding_id": ..., "fix_prompt": ..., "original_text": ...}]}
        """
        print(f"\n[{self.name}] 生成修正方案...")

        findings = audit_report.get("findings", [])
        errors_and_warnings = [f for f in findings if f.get("severity") in ("error", "warning")]

        if not errors_and_warnings:
            print(f"[{self.name}] 无需要修正的问题")
            return {"fixes_by_section": {}}

        fixes_by_section = {}
        for finding in errors_and_warnings:
            sec_id = finding.get("source_section", "")
            if sec_id not in fixes_by_section:
                fixes_by_section[sec_id] = []
            fixes_by_section[sec_id].append({
                "finding_id": finding.get("id", ""),
                "description": finding.get("description", ""),
                "suggested_fix": finding.get("suggested_fix", ""),
                "original_text_excerpt": finding.get("source_excerpt", ""),
                "target_section": finding.get("target_section", ""),
            })

        # 保存修正方案
        fixes_path = os.path.join(
            os.path.abspath("workspace/writing"), "consistency_fixes.json"
        )
        with open(fixes_path, "w", encoding="utf-8") as f:
            json.dump(fixes_by_section, f, ensure_ascii=False, indent=2)

        print(f"[{self.name}] 修正方案 → {fixes_path}")
        print(f"[{self.name}]   涉及 {len(fixes_by_section)} 个节, {len(errors_and_warnings)} 个问题")

        return {"fixes_by_section": fixes_by_section, "path": fixes_path}

    # ═══════════════════════════════════════════════════════════
    # 辅助
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _make_finding(
        rule_id: str,
        severity: str,
        description: str,
        source_section: str = "",
        target_section: str = "",
        source_excerpt: str = "",
        target_excerpt: str = "",
        suggested_fix: str = "",
    ) -> Dict:
        return {
            "id": f"{rule_id}_{datetime.now().strftime('%H%M%S')}",
            "severity": severity,
            "rule": rule_id,
            "description": description,
            "source_section": source_section,
            "target_section": target_section or source_section,
            "source_excerpt": source_excerpt,
            "target_excerpt": target_excerpt,
            "suggested_fix": suggested_fix,
            "fixed": False,
        }
