"""
质量门控模块 — 确保每个阶段产出达标后才进入下一阶段。

功能：
1. quality_score 自动计算（基于 schemas.py 的 compute_quality_score）
2. 门控规则：score < threshold → 自动重试或告警
3. 批量质量报告
4. 与 LlmClient.structured_output() 集成的 validator 回调
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any, Callable, Tuple
from dataclasses import asdict
import json
import os
from datetime import datetime


class QualityGate:
    """
    质量门控。检查每个分析产出的完整性，决定是否通过。

    使用方式:
      gate = QualityGate(threshold=0.4, max_retries=2)
      passed, report = gate.check_section(analysis_result, section_key="05")
      if not passed:
          # 触发重试
          ...
    """

    # 各维度的最低质量阈值
    DEFAULT_THRESHOLD = 0.35
    # 关键维度（方法论、基准结果）应有更高要求
    CRITICAL_SECTIONS = {"05", "06", "10"}

    def __init__(self, threshold: float = None, max_retries: int = 2):
        self.threshold = threshold or self.DEFAULT_THRESHOLD
        self.max_retries = max_retries
        self.reports: List[Dict] = []

    # ═══════════════════════════════════════════════════════════
    # 门控检查
    # ═══════════════════════════════════════════════════════════

    def check_section(
        self,
        result: Dict[str, Any],
        section_key: str = "",
        section_title: str = "",
        paper_title: str = "",
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        检查单个维度的分析质量。

        :param result: 分析结果 dict（来自 LiteratureAnalyzer 或 EmpiricalAnalyzer）
        :param section_key: 维度编号（"01"-"11"）
        :param section_title: 维度标题
        :param paper_title: 论文标题
        :return: (passed: bool, report: dict)
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "paper": paper_title,
            "section_key": section_key,
            "section_title": section_title,
            "passed": False,
            "checks": [],
            "quality_score": 0.0,
        }

        # 1. 基本成功检查
        if not result.get("success", False) and not result.get("json"):
            report["checks"].append({
                "check": "success_flag",
                "passed": False,
                "msg": "分析未成功完成",
                "severity": "error",
            })
            self.reports.append(report)
            return False, report

        # 2. 获取 JSON 数据
        json_data = result.get("json", {})
        if not json_data and isinstance(result.get("structured"), dict):
            json_data = result["structured"]

        if not json_data:
            report["checks"].append({
                "check": "json_exists",
                "passed": False,
                "msg": "未产出结构化 JSON 数据",
                "severity": "error",
            })
            self.reports.append(report)
            return False, report

        # 3. 计算 quality_score
        from skills.schemas import compute_quality_score
        score = compute_quality_score(json_data)
        report["quality_score"] = score

        # 4. 维度专属检查
        self._run_section_specific_checks(section_key, json_data, report)

        # 5. 信息充分性检查
        info_suff = json_data.get("information_sufficiency", "")
        if info_suff in ("不足", "insufficient"):
            report["checks"].append({
                "check": "information_sufficiency",
                "passed": False,
                "msg": f"信息充分性为「{info_suff}」，分析质量受限",
                "severity": "warning",
            })

        # 6. 关键字段非空检查
        critical_fields = self._get_critical_fields(section_key)
        for field_name in critical_fields:
            value = json_data.get(field_name)
            is_empty = (
                value is None or value == "" or value == [] or value == {} or value == 0
            )
            if is_empty:
                report["checks"].append({
                    "check": f"critical_field_{field_name}",
                    "passed": False,
                    "msg": f"关键字段「{field_name}」为空",
                    "severity": "warning",
                })

        # 7. 决定是否通过
        effective_threshold = self.threshold
        if section_key in self.CRITICAL_SECTIONS:
            effective_threshold = max(self.threshold, 0.45)

        errors = [c for c in report["checks"] if c["severity"] == "error"]
        report["passed"] = len(errors) == 0 and score >= effective_threshold

        self.reports.append(report)
        return report["passed"], report

    def check_empirical(
        self,
        result: Dict[str, Any],
        paper_title: str = "",
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        检查实证分析质量。比普通维度更严格。
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "paper": paper_title,
            "section_key": "empirical",
            "section_title": "实证方法论分析",
            "passed": False,
            "checks": [],
            "quality_score": 0.0,
        }

        if not result.get("success", False) and not result.get("json"):
            report["checks"].append({
                "check": "success_flag",
                "passed": False,
                "msg": "实证分析未成功完成",
                "severity": "error",
            })
            self.reports.append(report)
            return False, report

        json_data = result.get("json", {})

        from skills.schemas import compute_quality_score
        score = compute_quality_score(json_data)
        report["quality_score"] = score

        # 实证分析的关键字段
        must_have_fields = ["y_var", "x_var", "model_type", "hypotheses"]
        for field in must_have_fields:
            value = json_data.get(field)
            is_empty = (
                value is None or value == "" or value == [] or value == {} or
                (isinstance(value, str) and len(value) < 2)
            )
            if is_empty:
                report["checks"].append({
                    "check": f"must_have_{field}",
                    "passed": False,
                    "msg": f"实证关键字段「{field}」缺失或为空",
                    "severity": "warning" if field != "y_var" else "error",
                })

        errors = [c for c in report["checks"] if c["severity"] == "error"]
        report["passed"] = len(errors) == 0 and score >= 0.40

        self.reports.append(report)
        return report["passed"], report

    def check_paper_summary(self, summary_path: str) -> Tuple[bool, Dict[str, Any]]:
        """
        检查 _paper_summary.json 的完整性。
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "paper": os.path.basename(os.path.dirname(summary_path)),
            "section_key": "_paper_summary",
            "passed": False,
            "checks": [],
            "quality_score": 0.0,
        }

        if not os.path.exists(summary_path):
            report["checks"].append({
                "check": "file_exists",
                "passed": False,
                "msg": "_paper_summary.json 不存在",
                "severity": "error",
            })
            self.reports.append(report)
            return False, report

        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            report["checks"].append({
                "check": "valid_json",
                "passed": False,
                "msg": f"JSON 解析失败: {e}",
                "severity": "error",
            })
            self.reports.append(report)
            return False, report

        sections = data.get("sections", {})
        completed = [k for k in sections if sections[k].get("key_findings")]
        report["completed_sections"] = len(completed)
        report["total_sections"] = 11
        report["quality_score"] = data.get("overall_quality_score", 0.0)

        if len(completed) < 6:
            report["checks"].append({
                "check": "min_sections",
                "passed": False,
                "msg": f"仅完成 {len(completed)}/11 个维度分析（阈值: 6）",
                "severity": "warning",
            })

        # 检查 empirical 字段
        if "empirical" not in sections or not sections["empirical"]:
            report["checks"].append({
                "check": "has_empirical",
                "passed": False,
                "msg": "缺少实证分析（empirical 字段）",
                "severity": "info",
            })

        errors = [c for c in report["checks"] if c["severity"] == "error"]
        report["passed"] = len(errors) == 0

        self.reports.append(report)
        return report["passed"], report

    # ═══════════════════════════════════════════════════════════
    # 批量报告
    # ═══════════════════════════════════════════════════════════

    def get_summary_report(self) -> Dict[str, Any]:
        """生成质量总览报告"""
        if not self.reports:
            return {"message": "无检查记录"}

        passed = [r for r in self.reports if r["passed"]]
        failed = [r for r in self.reports if not r["passed"]]
        scores = [r["quality_score"] for r in self.reports]

        return {
            "total_checks": len(self.reports),
            "passed": len(passed),
            "failed": len(failed),
            "pass_rate": round(len(passed) / max(len(self.reports), 1), 2),
            "avg_quality_score": round(sum(scores) / max(len(scores), 1), 2),
            "failed_items": [
                {
                    "paper": r["paper"],
                    "section": r.get("section_key", ""),
                    "score": r["quality_score"],
                    "issues": [c["msg"] for c in r.get("checks", []) if not c["passed"]],
                }
                for r in failed
            ],
        }

    def print_report(self):
        """打印质量报告到控制台"""
        summary = self.get_summary_report()
        print(f"\n{'='*60}")
        print(f"[QualityGate] 质量门控报告")
        print(f"{'='*60}")
        print(f"  检查总数: {summary['total_checks']}")
        print(f"  通过: {summary['passed']} | 未通过: {summary['failed']}")
        print(f"  通过率: {summary['pass_rate']:.0%}")
        print(f"  平均质量分: {summary['avg_quality_score']:.2f}")
        if summary["failed_items"]:
            print(f"\n  未通过项:")
            for item in summary["failed_items"][:10]:
                print(f"    [{item['section']}] {item['paper'][:40]} (score={item['score']:.2f})")
                for issue in item["issues"][:3]:
                    print(f"      - {issue}")

    # ═══════════════════════════════════════════════════════════
    # LlmClient validator 回调工厂
    # ═══════════════════════════════════════════════════════════

    def make_validator(self, section_key: str) -> Callable[[dict], Tuple[bool, str]]:
        """
        生成一个 validator 回调，供 LlmClient.structured_output() 使用。

        用法:
          gate = QualityGate()
          result = llm.structured_output(
              prompt, output_schema,
              quality_validator=gate.make_validator("05"),
          )
        """
        def validator(parsed: dict) -> Tuple[bool, str]:
            from skills.schemas import compute_quality_score
            score = compute_quality_score(parsed)
            effective_threshold = self.threshold
            if section_key in self.CRITICAL_SECTIONS:
                effective_threshold = max(self.threshold, 0.45)
            # 实证分析也提高门槛
            if section_key == "empirical":
                effective_threshold = max(self.threshold, 0.40)

            if score < effective_threshold:
                return False, (
                    f"Quality score {score:.2f} 低于阈值 {effective_threshold:.2f}。"
                    f"请确保所有字段都已填写，特别是关键字段不能为空。"
                )

            # 检查关键字段
            critical_fields = self._get_critical_fields(section_key)
            empty_fields = []
            for field in critical_fields:
                value = parsed.get(field)
                if value is None or value == "" or value == [] or value == {}:
                    empty_fields.append(field)

            if empty_fields:
                return False, (
                    f"以下关键字段为空: {', '.join(empty_fields)}。"
                    f"请填写这些字段的具体内容，如果论文未提供，请标注'论文未明确说明'。"
                )

            return True, "OK"

        return validator

    # ═══════════════════════════════════════════════════════════
    # 辅助
    # ═══════════════════════════════════════════════════════════

    def _run_section_specific_checks(self, section_key: str, json_data: dict, report: dict):
        """维度专属检查"""
        checks = []

        if section_key == "01":
            if not json_data.get("research_question"):
                checks.append({
                    "check": "has_research_question",
                    "passed": False,
                    "msg": "未提取到研究问题",
                    "severity": "warning",
                })
        elif section_key == "05":
            if not json_data.get("estimation_method") or json_data.get("estimation_method") == "OLS":
                pass  # OLS 是合理的默认值
            if not json_data.get("baseline_model_form"):
                checks.append({
                    "check": "has_model_form",
                    "passed": False,
                    "msg": "未提取到基准回归方程",
                    "severity": "warning",
                })
        elif section_key == "06":
            if not json_data.get("core_coefficient_sign"):
                checks.append({
                    "check": "has_coefficient_sign",
                    "passed": False,
                    "msg": "未提取到核心系数方向",
                    "severity": "warning",
                })
            if not json_data.get("key_findings"):
                checks.append({
                    "check": "has_findings",
                    "passed": False,
                    "msg": "基准结果无任何关键发现",
                    "severity": "error",
                })
        elif section_key == "10":
            if not json_data.get("treatment_method"):
                checks.append({
                    "check": "has_treatment",
                    "passed": False,
                    "msg": "未提取到内生性处理方法",
                    "severity": "warning",
                })

        report["checks"].extend(checks)

    @staticmethod
    def _get_critical_fields(section_key: str) -> List[str]:
        """各维度的关键字段列表"""
        common = ["key_findings"]
        specific = {
            "01": ["research_question", "question_type"],
            "02": ["theories_used", "hypotheses_derived"],
            "03": ["identification_strategy"],
            "04": ["data_source", "key_variables"],
            "05": ["baseline_model_form", "estimation_method"],
            "06": ["core_coefficient_sign", "key_findings"],
            "07": ["robustness_checks_performed"],
            "08": ["mechanism_channels"],
            "09": ["heterogeneity_dimensions"],
            "10": ["treatment_method", "endogeneity_types"],
            "11": ["core_conclusions"],
            "empirical": ["y_var", "x_var", "model_type", "hypotheses"],  # 实证分析
        }
        return common + specific.get(section_key, [])


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def quick_quality_check(json_data: dict, section_key: str = "") -> Dict[str, Any]:
    """
    快速质量检查（不依赖 QualityGate 实例）。
    返回 {"passed": bool, "score": float, "issues": [...]}
    """
    from skills.schemas import compute_quality_score
    score = compute_quality_score(json_data)
    issues = []

    # 检查关键字段
    critical = QualityGate._get_critical_fields(section_key)
    for field in critical:
        value = json_data.get(field)
        if value is None or value == "" or value == [] or value == {}:
            issues.append(f"关键字段「{field}」为空")

    threshold = 0.45 if section_key in QualityGate.CRITICAL_SECTIONS else 0.35
    passed = len(issues) == 0 and score >= threshold

    return {
        "passed": passed,
        "score": score,
        "threshold": threshold,
        "issues": issues,
    }
