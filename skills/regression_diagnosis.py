"""
回归诊断与决策引擎 — 在蓝图之前运行，确保写作方向由数据驱动。

核心流程：
1. 接收回归结果（Stata MCP 或 Python regression_lib 产出）
2. 逐条假设诊断：支撑/部分支撑/不支撑/反向显著
3. 如果不支撑，推断原因（数据/模型/识别/假设/选题）
4. 自动推荐回退路径（proceed / revise / reconsider）
5. 无论如何，提取可写作的内容

原则：不显著也是发现。符号反向往往是最有价值的发现。
"""

from __future__ import annotations
import os
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import asdict

from skills.base import BaseSkill
from skills.llm_client import LlmClient, dataclass_to_json_schema
from skills.schemas import (
    RegressionDiagnosis, HypothesisTestResult, RegressionDecision,
    dataclass_to_dict, compute_quality_score,
)
from skills.quality_gate import QualityGate


# 确定性规则：即使不调用 LLM，也能做的自动诊断
HARD_RULES = {
    "no_variation": {
        "check": lambda r: (
            "results" in r and len(r.get("results", [])) > 0 and
            all(
                h.get("coefficient") is None and not h.get("significance")
                for h in r["results"]
            )
        ),
        "cause": "数据问题",
        "action": "acquire_new_data",
        "fallback": "4.5",
        "message": "所有核心变量均无回归结果——可能是数据路径错误或变量名不匹配",
    },
    "obvious_misspecification": {
        "check": lambda r: r.get("r_squared", 1.0) > 0.99 or r.get("r_squared", 0.5) < 0.01,
        "cause": "模型误设",
        "action": "revise_model",
        "fallback": "3",
        "message": f"R²异常——可能遗漏关键变量或存在完全共线性",
    },
    "perfect_multicollinearity": {
        "check": lambda r: "singular" in str(r.get("error", "")).lower() or
                           "collinear" in str(r.get("error", "")).lower() or
                           "singular" in str(r.get("summary", "")).lower(),
        "cause": "模型误设",
        "action": "revise_model",
        "fallback": "3",
        "message": "完全共线性——检查是否包含了线性相关的变量",
    },
}


class RegressionDiagnosisEngine(BaseSkill):
    """
    回归诊断与决策引擎。

    使用方式：
      engine = RegressionDiagnosisEngine()
      diagnosis = engine.diagnose(regression_results, hypotheses, ...)
      decision = engine.decide(diagnosis)
      # decision 告诉你下一步: PROCEED / REVISE_* / RECONSIDER
    """

    def __init__(self):
        super().__init__(
            name="RegressionDiagnosisEngine",
            description="回归结果结构化诊断 + 自动决策树"
        )
        self.llm = LlmClient()
        self._prompts_dir = os.path.abspath("references/prompts")

    def execute(self, action: str, **kwargs):
        if action == "diagnose":
            return self.diagnose(**kwargs)
        elif action == "decide":
            return self.decide(**kwargs)
        elif action == "full":
            return self.diagnose_and_decide(**kwargs)
        else:
            raise NotImplementedError(f"未实现: {action}")

    # ═══════════════════════════════════════════════════════════
    # 主流程
    # ═══════════════════════════════════════════════════════════

    def diagnose(
        self,
        regression_results: Dict,
        hypotheses: List[Dict] = None,
        literature_evidence: str = "",
        paper_summaries: List[Dict] = None,
        backend: str = None,
        model: str = None,
    ) -> Dict:
        """
        对回归结果进行完整诊断。

        :param regression_results: 回归输出（Stata 日志 或 regression_lib 产出的 JSON）
        :param hypotheses: 假设体系 [{id: "H1", claim: "...", direction: "+", ...}]
        :param literature_evidence: 已有文献中的证据（用于对比系数方向和大小）
        :return: RegressionDiagnosis dict
        """
        print(f"\n[{self.name}] ╔══════════════════════════════════════╗")
        print(f"[{self.name}] ║  Step 4.6: 回归诊断与决策              ║")
        print(f"[{self.name}] ╚══════════════════════════════════════╝")

        hypotheses = hypotheses or []

        # ── 快速确定性检查 ──
        quick = self._run_hard_rules(regression_results)
        if quick:
            print(f"[{self.name}] ⚠ 确定性规则触发: {quick['message'][:80]}")
            diagnosis = self._build_quick_diagnosis(hypotheses, quick)
            return dataclass_to_dict(diagnosis)

        # ── LLM 深度诊断 ──
        prompt_path = os.path.join(self._prompts_dir, "regression_diagnosis.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
        else:
            template = self._get_inline_prompt()

        # 构建假设上下文
        hyp_text = self._format_hypotheses(hypotheses)

        # 构建文献证据
        lit_text = literature_evidence or self._extract_literature_evidence(paper_summaries, hypotheses)

        full_prompt = (template
            .replace("{hypotheses_context}", hyp_text)
            .replace("{theoretical_expectations}", self._format_theoretical_expectations(hypotheses))
            .replace("{regression_output}", json.dumps(regression_results, ensure_ascii=False, indent=2)[:8000])
            .replace("{literature_evidence}", lit_text[:3000] or "（无已有文献证据——这是第一个检验该假设的研究？）"))

        output_schema = dataclass_to_json_schema(RegressionDiagnosis)
        gate = QualityGate(threshold=0.3)

        try:
            diagnosis_dict = self.llm.structured_output(
                prompt=full_prompt,
                output_schema=output_schema,
                system_prompt="你是一位经济学实证研究专家。请对回归结果进行诚实的诊断。不显著=不显著，不要强行解释。符号相反可能是更大的发现。",
                backend=backend,
                model=model,
                max_tokens=5000,
                max_retries=2,
                quality_validator=gate.make_validator("empirical"),
            )
        except Exception as e:
            print(f"[{self.name}] LLM 诊断失败: {e}，使用确定性回退")
            diagnosis_dict = self._build_minimal_diagnosis(hypotheses, regression_results)

        # 保存
        diag_path = os.path.join(
            os.path.abspath("workspace/regression"), "diagnosis.json"
        )
        os.makedirs(os.path.dirname(diag_path), exist_ok=True)
        with open(diag_path, "w", encoding="utf-8") as f:
            json.dump(diagnosis_dict, f, ensure_ascii=False, indent=2)

        verdict = diagnosis_dict.get("overall_verdict", "?")
        action = diagnosis_dict.get("recommended_action", "?")
        print(f"[{self.name}] 诊断: {verdict} → {action}")
        print(f"[{self.name}]   支撑: {diagnosis_dict.get('supported_count', 0)} "
              f"部分: {diagnosis_dict.get('partial_count', 0)} "
              f"拒绝: {diagnosis_dict.get('rejected_count', 0)}")
        print(f"[{self.name}]   → {diag_path}")

        return diagnosis_dict

    def decide(self, diagnosis: Dict) -> Dict:
        """
        基于诊断结果，生成结构化的 RegressionDecision。

        :param diagnosis: RegressionDiagnosis dict
        :return: RegressionDecision dict
        """
        action = diagnosis.get("recommended_action", "proceed")

        if action == "proceed":
            decision = RegressionDecision(
                decision_type="PROCEED",
                blueprint_ready=True,
                diagnosis_summary=f"全部 {diagnosis.get('supported_count', 0)} 条假设得到支撑，可进入蓝图汇总",
                decision_confidence="高",
            )
        elif action == "revise_hypotheses":
            decision = RegressionDecision(
                decision_type="REVISE_HYPOTHESES",
                blueprint_ready=False,
                target_step="2",
                revision_instructions={
                    "hypotheses_to_modify": diagnosis.get("hypotheses_to_revise", []),
                    "hypotheses_to_drop": diagnosis.get("hypotheses_to_drop", []),
                    "reversed_interpretation": diagnosis.get("reversed_interpretation", ""),
                },
                diagnosis_summary=f"{diagnosis.get('rejected_count', 0)} 条假设被拒绝/不支撑，需修正",
                decision_confidence=diagnosis.get("diagnosis_quality_score", "中"),
            )
        elif action == "revise_model":
            decision = RegressionDecision(
                decision_type="REVISE_MODEL",
                blueprint_ready=False,
                target_step="3",
                revision_instructions={
                    "model_adjustments": diagnosis.get("model_adjustments", []),
                    "variables_to_add": diagnosis.get("variables_to_add", []),
                },
                suggested_regressions=diagnosis.get("suggested_regressions", []),
                diagnosis_summary="模型设定可能存在问题，建议调整后重新回归",
                decision_confidence="中",
            )
        elif action == "acquire_new_data":
            decision = RegressionDecision(
                decision_type="ACQUIRE_DATA",
                blueprint_ready=False,
                target_step="4.5",
                revision_instructions={
                    "variables_needed": diagnosis.get("variables_to_add", []),
                    "possible_causes": diagnosis.get("possible_causes", []),
                },
                diagnosis_summary="数据问题——建议增加/替换变量后重新回归",
                decision_confidence="中",
            )
        elif action == "reconsider_topic":
            decision = RegressionDecision(
                decision_type="RECONSIDER_TOPIC",
                blueprint_ready=False,
                target_step="0",
                revision_instructions={
                    "diagnosis": diagnosis.get("possible_causes", []),
                    "alternative_direction": "可考虑将'不存在因果'本身作为研究发现",
                },
                diagnosis_summary="回归结果完全不支撑研究假设，建议重新考虑选题方向",
                decision_confidence="高" if diagnosis.get("rejected_count", 0) == diagnosis.get("total_hypotheses", 1) else "中",
            )
        else:
            # 默认为继续
            decision = RegressionDecision(
                decision_type="PROCEED",
                blueprint_ready=True,
                diagnosis_summary="默认继续",
                decision_confidence="低",
            )

        return dataclass_to_dict(decision)

    def diagnose_and_decide(self, **kwargs) -> Dict:
        """一步完成诊断+决策"""
        diag = self.diagnose(**kwargs)
        dec = self.decide(diag)
        return {"diagnosis": diag, "decision": dec, "success": True}

    # ═══════════════════════════════════════════════════════════
    # 辅助
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _run_hard_rules(regression_results: Dict) -> Optional[Dict]:
        """运行确定性规则——检测明显的回归失败"""
        for rule_name, rule in HARD_RULES.items():
            try:
                if rule["check"](regression_results):
                    return {
                        "rule": rule_name,
                        "cause": rule["cause"],
                        "action": rule["action"],
                        "fallback": rule["fallback"],
                        "message": rule["message"],
                    }
            except Exception:
                pass
        return None

    @staticmethod
    def _build_quick_diagnosis(hypotheses: List[Dict], quick: Dict) -> RegressionDiagnosis:
        """从确定性规则快速构建诊断"""
        return RegressionDiagnosis(
            overall_verdict="完全不支撑",
            recommended_action=quick["action"],
            action_rationale=quick["message"],
            fallback_step=quick["fallback"],
            possible_causes=[{"cause": quick["cause"], "likelihood": "高", "evidence": quick["message"]}],
            writable_findings=[{
                "finding": f"回归未能成功运行: {quick['message']}",
                "writing_section": "5.4",
                "evidence_level": "不适用",
            }],
        )

    @staticmethod
    def _build_minimal_diagnosis(hypotheses: List[Dict], results: Dict) -> Dict:
        """最小化回退诊断（当 LLM 不可用时）"""
        return {
            "overall_verdict": "无法自动诊断",
            "recommended_action": "proceed",
            "action_rationale": "LLM 诊断不可用，建议人工检查回归结果后决定",
            "writable_findings": [{
                "finding": "回归已完成，但自动诊断不可用。请人工检查结果。",
                "writing_section": "5.1",
                "evidence_level": "未评估",
            }],
        }

    @staticmethod
    def _format_hypotheses(hypotheses: List[Dict]) -> str:
        parts = []
        for h in (hypotheses or []):
            if isinstance(h, dict):
                parts.append(
                    f"**{h.get('id', '?')}**: {h.get('claim', h.get('content', ''))}\n"
                    f"  方向: {h.get('direction', '?')} | Y: {h.get('y_var', '')} | X: {h.get('x_var', '')}\n"
                    f"  检验方法: {h.get('test_method', '')} | 理论: {', '.join(h.get('theory_basis', []))}"
                )
            elif isinstance(h, str):
                parts.append(h)
        return "\n\n".join(parts) if parts else "（无假设信息）"

    @staticmethod
    def _format_theoretical_expectations(hypotheses: List[Dict]) -> str:
        parts = []
        for h in (hypotheses or []):
            if isinstance(h, dict):
                parts.append(
                    f"{h.get('id', '?')}: 预期方向={h.get('expected_sign', h.get('direction', '?'))} | "
                    f"理论={', '.join(h.get('theory_basis', []))}"
                )
        return "\n".join(parts) if parts else "（无预期信息）"

    @staticmethod
    def _extract_literature_evidence(paper_summaries: List[Dict], hypotheses: List[Dict]) -> str:
        """从 paper_summaries 中提取已有文献的实证证据"""
        if not paper_summaries:
            return ""

        parts = []
        for ps in (paper_summaries or []):
            title = ps.get("paper_title", "")
            sections = ps.get("sections", {})
            baseline = sections.get("06_baseline_results", {})
            sign = baseline.get("core_coefficient_sign", "")
            findings = baseline.get("key_findings", [])

            if sign or findings:
                parts.append(f"**{title[:40]}**:")
                if sign:
                    parts.append(f"  核心系数方向: {sign}")
                for f in (findings or [])[:2]:
                    if isinstance(f, str) and len(f) > 10:
                        parts.append(f"  - {f[:150]}")

        return "\n".join(parts) if parts else "（无已有文献证据）"

    @staticmethod
    def _get_inline_prompt() -> str:
        return """你是一位经济学实证专家。请诊断回归结果。

假设: {hypotheses_context}
预期: {theoretical_expectations}
结果: {regression_output}
文献: {literature_evidence}

请输出 RegressionDiagnosis JSON，逐条假设给出 verdict。
如果显著且方向一致→支撑，不显著→不支撑，方向相反→反向显著。
如果不支撑，推断原因（数据/模型/识别/假设/选题）并推荐回退路径。"""
