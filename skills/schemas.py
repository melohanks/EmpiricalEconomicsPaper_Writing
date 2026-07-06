"""
统一 JSON Schema 定义 — 全流程论文写作系统的数据契约。

所有 LLM 分析输出必须符合此 Schema。结构化输出替代手写正则提取，
确保数据质量可验证、可追溯、可机器处理。

设计原则：
1. 每个维度有专属子 Schema（不搞万能字段）
2. 字段使用具体类型而非自由文本（能枚举就枚举）
3. 所有 Schema 自带 quality_score 计算逻辑
4. 支持增量合并（新增论文不破坏已有数据）
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Union, Literal
from enum import Enum


# ═══════════════════════════════════════════════════════════════
# 枚举类型（统一术语，避免 LLM 自由发挥）
# ═══════════════════════════════════════════════════════════════

class QuestionType(str, Enum):
    CAUSAL = "因果"
    DESCRIPTIVE = "描述"
    PREDICTIVE = "预测"
    EXPLORATORY = "探索性"
    METHODOLOGICAL = "方法论"

class EstimationMethod(str, Enum):
    OLS = "OLS"
    TWOFE = "面板双向固定效应"
    GMM_SYS = "系统GMM"
    GMM_DIFF = "差分GMM"
    DID = "双重差分"
    DDD = "三重差分"
    STAGGERED_DID = "多时点DID"
    RDD = "断点回归"
    IV_2SLS = "工具变量2SLS"
    PSM = "倾向得分匹配"
    HECKMAN = "Heckman两步法"
    TOBIT = "Tobit"
    PROBIT = "Probit"
    LOGIT = "Logit"
    POISSON = "泊松回归"
    COX = "Cox比例风险"
    QUANTILE = "分位数回归"
    SPATIAL = "空间计量"
    SEM = "结构方程模型"
    DML = "双重机器学习"
    OTHER = "其他"

class StandardErrorType(str, Enum):
    CLUSTER = "聚类稳健"
    HETERO_ROBUST = "异方差稳健"
    BOOTSTRAP = "自举法"
    CONVENTIONAL = "常规"
    NOT_SPECIFIED = "未说明"

class ClusterLevel(str, Enum):
    CITY = "城市"
    FIRM = "企业"
    PROVINCE = "省份"
    INDUSTRY = "行业"
    COUNTY = "县区"
    COUNTRY = "国家"
    NOT_SPECIFIED = "未说明"

class InfoSufficiency(str, Enum):
    FULL = "充分"
    PARTIAL = "部分充分"
    INSUFFICIENT = "不足"

class RobustnessScore(str, Enum):
    EXCELLENT = "优秀"     # 5+种不同类型的检验
    GOOD = "良好"         # 3-4种
    ADEQUATE = "一般"     # 1-2种
    WEAK = "较弱"         # 未做稳健性检验

class ConvergenceLevel(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"

class SignificanceLevel(str, Enum):
    P001 = "p<0.01"
    P005 = "p<0.05"
    P010 = "p<0.10"
    NOT_SIG = "不显著"
    NOT_REPORTED = "未报告"


# ═══════════════════════════════════════════════════════════════
# 通用数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class HypothesisEntry:
    """单条研究假设"""
    id: str                                    # H1, H2, ...
    content: str                               # 假设内容
    direction: str = ""                        # 正向/负向/U型/倒U型
    theory_basis: List[str] = field(default_factory=list)  # 理论基础
    testable: bool = True                      # 是否可检验
    test_method: str = ""                      # 检验方法

@dataclass
class CoefficientEntry:
    """单个回归系数"""
    variable: str                              # 变量名
    coefficient: Optional[float] = None        # 系数值
    standard_error: Optional[float] = None     # 标准误
    t_stat: Optional[float] = None
    p_value: Optional[float] = None
    significance: SignificanceLevel = SignificanceLevel.NOT_REPORTED
    ci_lower: Optional[float] = None           # 95% CI 下界
    ci_upper: Optional[float] = None           # 95% CI 上界

@dataclass
class VariableDefinition:
    """变量定义"""
    name: str                                  # 变量名（中文）
    symbol: str = ""                           # 变量符号（英文）
    definition: str = ""                       # 测度方式
    unit: str = ""                             # 单位
    data_source: str = ""                      # 数据来源
    is_core: bool = False                      # 是否核心变量

@dataclass
class MechanismChannel:
    """机制/中介渠道"""
    name: str                                  # 机制名称
    mediator_variable: str = ""                # 中介变量
    mediator_definition: str = ""              # 中介变量定义
    test_method: str = ""                      # 检验方法（三步法/Bootstrap/因果中介）
    effect_direction: str = ""                 # 效应方向
    evidence_strength: str = ""                # 证据强度
    coefficient: Optional[float] = None        # 间接效应系数

@dataclass
class HeterogeneityDimension:
    """异质性维度"""
    dimension: str                             # 异质性维度名
    grouping_method: str = ""                  # 分组方式
    key_finding: str = ""                      # 核心发现
    subgroup_effects: Dict[str, float] = field(default_factory=dict)  # 子组效应

@dataclass
class DiagnosticTest:
    """诊断检验"""
    name: str                                  # 检验名
    performed: bool = False
    passed: Optional[bool] = None
    result_detail: str = ""
    impact_on_conclusion: str = ""

@dataclass
class EndogeneityThreat:
    """内生性威胁"""
    type: str                                  # 遗漏变量/反向因果/测量误差/样本选择
    severity: str = ""                         # 高/中/低
    treatment: str = ""                        # 处理方法

@dataclass
class IVDetail:
    """工具变量详情"""
    variable: str = ""                         # IV 变量名
    definition: str = ""                       # IV 定义
    relevance_rationale: str = ""              # 相关性论证
    exclusion_rationale: str = ""              # 排他性论证
    f_statistic: Optional[float] = None        # 第一阶段 F 统计量


# ═══════════════════════════════════════════════════════════════
# 11 维度专用 Schema（每个维度的结构化输出）
# ═══════════════════════════════════════════════════════════════

@dataclass
class Section01Introduction:
    """01. 研究问题与动机"""
    section_key: str = "01"
    section_title: str = "研究问题与动机"
    research_question: str = ""
    question_type: QuestionType = QuestionType.EXPLORATORY
    real_world_motivation: str = ""            # 现实动机
    theoretical_motivation: str = ""           # 理论动机
    contribution_claims: Dict[str, str] = field(default_factory=dict)  # {"理论贡献": "...", "实证贡献": "..."}
    core_endogeneity_threat: str = ""          # 最核心的内生性挑战
    positioning_vs_literature: str = ""        # 相对文献的定位
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    information_sufficiency: InfoSufficiency = InfoSufficiency.PARTIAL
    quality_score: float = 0.0

@dataclass
class Section02TheoreticalFramework:
    """02. 理论框架"""
    section_key: str = "02"
    section_title: str = "理论框架"
    theories_used: List[str] = field(default_factory=list)  # 使用的理论
    theoretical_model_type: str = ""           # 理论模型类型
    hypotheses_derived: List[HypothesisEntry] = field(default_factory=list)
    conceptual_framework: str = ""             # 概念框架描述
    assumptions: List[str] = field(default_factory=list)  # 关键假设
    competing_hypotheses: List[str] = field(default_factory=list)  # 竞争性假说
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    information_sufficiency: InfoSufficiency = InfoSufficiency.PARTIAL
    quality_score: float = 0.0

@dataclass
class Section03Identification:
    """03. 识别策略"""
    section_key: str = "03"
    section_title: str = "识别策略"
    identification_strategy: str = ""          # 核心识别策略
    quasi_experiment_description: str = ""     # 准实验描述
    treatment_definition: str = ""             # 处理组/处理变量定义
    control_group_definition: str = ""         # 对照组定义
    parallel_trends_tested: bool = False
    parallel_trends_passed: Optional[bool] = None
    anticipation_concern_addressed: bool = False
    endogeneity_threats: List[EndogeneityThreat] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    information_sufficiency: InfoSufficiency = InfoSufficiency.PARTIAL
    quality_score: float = 0.0

@dataclass
class Section04DataVariables:
    """04. 数据与变量"""
    section_key: str = "04"
    section_title: str = "数据与变量"
    data_source: str = ""                      # 数据来源
    data_structure: str = ""                   # 数据结构（面板/截面/混合截面）
    sample_period: str = ""                    # 样本期间
    sample_size: str = ""                      # 样本量
    unit_of_analysis: str = ""                 # 分析单位
    y_variable: Optional[VariableDefinition] = None
    x_variable: Optional[VariableDefinition] = None
    control_variables: List[VariableDefinition] = field(default_factory=list)
    key_variables: Dict[str, Any] = field(default_factory=dict)  # 保留兼容
    summary_statistics_summary: str = ""       # 描述性统计摘要
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    information_sufficiency: InfoSufficiency = InfoSufficiency.PARTIAL
    quality_score: float = 0.0

@dataclass
class Section05EmpiricalMethodology:
    """05. 实证方法与模型设定"""
    section_key: str = "05"
    section_title: str = "实证方法与模型设定"
    baseline_model_form: str = ""              # 基准回归方程（LaTeX）
    estimation_method: EstimationMethod = EstimationMethod.OLS
    fixed_effects: List[str] = field(default_factory=list)
    standard_error_type: StandardErrorType = StandardErrorType.NOT_SPECIFIED
    cluster_level: ClusterLevel = ClusterLevel.NOT_SPECIFIED
    diagnostic_tests: List[DiagnosticTest] = field(default_factory=list)
    method_problem_match_score: int = 0        # 1-5
    methodological_rigor_score: str = ""       # 优秀/良好/一般/较弱
    strongest_aspect: str = ""
    weakest_aspect: str = ""
    alternative_methods_suggested: List[str] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    information_sufficiency: InfoSufficiency = InfoSufficiency.PARTIAL
    quality_score: float = 0.0

@dataclass
class Section06BaselineResults:
    """06. 基准结果"""
    section_key: str = "06"
    section_title: str = "基准结果"
    core_coefficient_sign: str = ""            # 正向/负向/不显著
    core_coefficient_table: List[CoefficientEntry] = field(default_factory=list)
    statistical_significance: SignificanceLevel = SignificanceLevel.NOT_REPORTED
    economic_significance: str = ""            # 经济显著性描述
    r_squared: Optional[float] = None
    n_observations: Optional[int] = None
    consistency_with_literature: str = ""      # 与文献的一致性
    interpretation_quality: str = ""           # 解读质量评估
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    information_sufficiency: InfoSufficiency = InfoSufficiency.PARTIAL
    quality_score: float = 0.0

@dataclass
class Section07Robustness:
    """07. 稳健性检验"""
    section_key: str = "07"
    section_title: str = "稳健性检验"
    robustness_checks_performed: List[str] = field(default_factory=list)
    overall_robustness_score: RobustnessScore = RobustnessScore.WEAK
    checks_detail: List[Dict[str, str]] = field(default_factory=list)  # [{"check": "替换Y", "result": "稳健"}]
    missing_essential_checks: List[str] = field(default_factory=list)  # 缺失的关键检验
    conclusion_stable: Optional[bool] = None
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    information_sufficiency: InfoSufficiency = InfoSufficiency.PARTIAL
    quality_score: float = 0.0

@dataclass
class Section08Mechanism:
    """08. 机制分析"""
    section_key: str = "08"
    section_title: str = "机制分析"
    mechanism_channels: List[MechanismChannel] = field(default_factory=list)
    mechanism_test_method: str = ""            # 总体机制检验方法
    mechanism_evidence_overall: str = ""       # 整体证据强度评估
    missing_mechanisms: List[str] = field(default_factory=list)  # 应该检验但未检验的机制
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    information_sufficiency: InfoSufficiency = InfoSufficiency.PARTIAL
    quality_score: float = 0.0

@dataclass
class Section09Heterogeneity:
    """09. 异质性分析"""
    section_key: str = "09"
    section_title: str = "异质性分析"
    heterogeneity_dimensions: List[HeterogeneityDimension] = field(default_factory=list)
    multiple_testing_correction: bool = False  # 是否做了多重检验校正
    consistent_pattern: str = ""               # 一致性模式
    missing_dimensions: List[str] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    information_sufficiency: InfoSufficiency = InfoSufficiency.PARTIAL
    quality_score: float = 0.0

@dataclass
class Section10Endogeneity:
    """10. 内生性处理"""
    section_key: str = "10"
    section_title: str = "内生性处理"
    endogeneity_types: List[EndogeneityThreat] = field(default_factory=list)
    treatment_method: str = ""                 # 主要处理方法
    iv_details: Optional[IVDetail] = None
    did_details: Dict[str, str] = field(default_factory=dict)
    residual_concerns: List[str] = field(default_factory=list)  # 残余内生性担忧
    overall_endogeneity_handling: str = ""     # 整体处理质量评估
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    information_sufficiency: InfoSufficiency = InfoSufficiency.PARTIAL
    quality_score: float = 0.0

@dataclass
class Section11Conclusion:
    """11. 结论与政策含义"""
    section_key: str = "11"
    section_title: str = "结论与政策含义"
    core_conclusions: List[str] = field(default_factory=list)
    policy_recommendations: List[Dict[str, str]] = field(default_factory=list)  # [{"rec": "...", "operability": "高/中/低"}]
    limitations_acknowledged: List[str] = field(default_factory=list)
    future_directions: List[str] = field(default_factory=list)
    overall_scores: Dict[str, int] = field(default_factory=dict)  # {"理论贡献": 4, "实证严谨": 3, ...}
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    information_sufficiency: InfoSufficiency = InfoSufficiency.PARTIAL
    quality_score: float = 0.0


# ═══════════════════════════════════════════════════════════════
# 实证分析专用 Schema
# ═══════════════════════════════════════════════════════════════

@dataclass
class EmpiricalAnalysis:
    """实证方法论四维分析"""
    title: str = ""
    # 维度一：研究假设
    hypotheses: List[HypothesisEntry] = field(default_factory=list)
    hypothesis_count: int = 0
    # 维度二：实证方法
    model_type: str = ""                       # 模型类型
    estimation_method: EstimationMethod = EstimationMethod.OLS
    baseline_model_form: str = ""              # 回归方程
    fixed_effects: List[str] = field(default_factory=list)
    standard_error_type: StandardErrorType = StandardErrorType.NOT_SPECIFIED
    cluster_level: ClusterLevel = ClusterLevel.NOT_SPECIFIED
    endogeneity_strategy: str = ""
    iv_details: Optional[IVDetail] = None
    did_details: Dict[str, str] = field(default_factory=dict)
    diagnostic_tests: List[DiagnosticTest] = field(default_factory=list)
    # 维度三：变量体系
    y_var: str = ""
    y_definition: str = ""
    x_var: str = ""
    x_definition: str = ""
    control_vars: List[str] = field(default_factory=list)
    mechanism_vars: List[str] = field(default_factory=list)
    mechanism_channels: List[MechanismChannel] = field(default_factory=list)
    heterogeneity_dims: List[str] = field(default_factory=list)
    heterogeneity_details: List[HeterogeneityDimension] = field(default_factory=list)
    # 维度四：实证结果
    key_coefficients: List[CoefficientEntry] = field(default_factory=list)
    robustness_checks: List[str] = field(default_factory=list)
    robustness_score: RobustnessScore = RobustnessScore.WEAK
    key_results: List[str] = field(default_factory=list)
    # 通用
    key_findings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    quality_score: float = 0.0


# ═══════════════════════════════════════════════════════════════
# 跨论文对比 Schema
# ═══════════════════════════════════════════════════════════════

@dataclass
class CommonPattern:
    """共性模式"""
    id: int = 0
    pattern: str = ""
    papers_count: int = 0
    papers: List[str] = field(default_factory=list)
    details: str = ""
    is_consensus: bool = False

@dataclass
class Divergence:
    """差异点"""
    id: int = 0
    aspect: str = ""
    approaches: Dict[str, str] = field(default_factory=dict)  # {"论文A": "做法", "论文B": "做法"}
    reason: str = ""
    recommended: str = ""

@dataclass
class ConsensusGap:
    """共识性空缺"""
    description: str = ""
    source_papers: List[str] = field(default_factory=list)
    source_dimension: str = ""

@dataclass
class DimensionComparison:
    """单个维度的跨论文对比"""
    dimension_key: str = ""
    dimension_title: str = ""
    paper_count: int = 0
    papers: List[str] = field(default_factory=list)
    common_patterns: List[CommonPattern] = field(default_factory=list)
    divergences: List[Divergence] = field(default_factory=list)
    consensus_gaps: List[ConsensusGap] = field(default_factory=list)
    methodological_insights: List[str] = field(default_factory=list)
    convergence_level: ConvergenceLevel = ConvergenceLevel.LOW
    key_takeaway: str = ""
    quality_score: float = 0.0

@dataclass
class EmpiricalAspectComparison:
    """单个实证方面的跨论文对比"""
    aspect: str = ""
    aspect_title: str = ""
    paper_count: int = 0
    papers: List[str] = field(default_factory=list)
    distribution_summary: str = ""
    common_patterns: List[CommonPattern] = field(default_factory=list)
    divergences: List[Divergence] = field(default_factory=list)
    methodological_rules: List[str] = field(default_factory=list)
    frequency_table: Dict[str, int] = field(default_factory=dict)
    convergence_level: ConvergenceLevel = ConvergenceLevel.LOW
    key_takeaway: str = ""
    quality_score: float = 0.0

@dataclass
class CrossPaperSummary:
    """跨论文综合记忆"""
    meta: Dict[str, Any] = field(default_factory=dict)
    dimension_insights: Dict[str, DimensionComparison] = field(default_factory=dict)
    empirical_insights: Dict[str, EmpiricalAspectComparison] = field(default_factory=dict)
    synthesis_for_writing: Dict[str, Any] = field(default_factory=dict)

@dataclass
class WritingSynthesis:
    """写作素材综合推荐"""
    methodological_insights: List[str] = field(default_factory=list)
    common_patterns_summary: List[Dict] = field(default_factory=list)
    consensus_gaps: List[ConsensusGap] = field(default_factory=list)
    frequency_summary: Dict[str, Any] = field(default_factory=dict)
    citation_map: Dict[str, List[str]] = field(default_factory=dict)
    narrative_synthesis: str = ""
    total_papers: int = 0
    papers: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 统一论文记忆 (PaperSummary) — 全流程的核心数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class PaperSummary:
    """
    单篇论文的完整结构化记忆。
    这是全流程的核心数据契约：所有阶段都读取此结构，
    所有分析结果都写入此结构。
    """
    paper_title: str = ""
    authors: str = ""
    source: str = ""
    pub_date: str = ""
    keywords: List[str] = field(default_factory=list)
    abstract: str = ""
    doi: str = ""
    fulltext: str = ""                         # PDF 全文（可截断到合理长度）
    fulltext_length: int = 0                   # 原始全文长度

    # 11 维度分析（使用专用 Schema）
    section_01_introduction: Optional[Section01Introduction] = None
    section_02_theoretical: Optional[Section02TheoreticalFramework] = None
    section_03_identification: Optional[Section03Identification] = None
    section_04_data: Optional[Section04DataVariables] = None
    section_05_methodology: Optional[Section05EmpiricalMethodology] = None
    section_06_baseline: Optional[Section06BaselineResults] = None
    section_07_robustness: Optional[Section07Robustness] = None
    section_08_mechanism: Optional[Section08Mechanism] = None
    section_09_heterogeneity: Optional[Section09Heterogeneity] = None
    section_10_endogeneity: Optional[Section10Endogeneity] = None
    section_11_conclusion: Optional[Section11Conclusion] = None

    # 实证分析
    empirical: Optional[EmpiricalAnalysis] = None

    # 总体评估
    overall_assessment: Dict[str, Any] = field(default_factory=dict)
    sections_completed: List[str] = field(default_factory=list)  # ["01", "02", ...]

    # 质量元数据
    overall_quality_score: float = 0.0
    last_updated: str = ""


# ═══════════════════════════════════════════════════════════════
# 质量评分工具
# ═══════════════════════════════════════════════════════════════

def compute_quality_score(section_data: Any) -> float:
    """
    基于信息完整性自动计算 quality_score (0-1)。
    通用逻辑：检查关键字段的非空率。
    """
    if section_data is None:
        return 0.0

    score = 0.0
    max_score = 0.0

    if isinstance(section_data, dict):
        fields = section_data
    elif hasattr(section_data, '__dataclass_fields__'):
        fields = asdict(section_data)
    else:
        return 0.5  # 无法判断

    for key, value in fields.items():
        if key.startswith('_') or key in ('section_key', 'section_title', 'quality_score'):
            continue

        max_score += 1.0

        if value is None or value == "" or value == [] or value == {}:
            continue  # 空字段不得分

        if isinstance(value, list):
            # 列表字段：至少 1 个有效元素得满分
            score += 1.0
        elif isinstance(value, dict):
            # 字典字段：至少 1 个非空键得满分
            if any(v for v in value.values() if v):
                score += 1.0
        elif isinstance(value, str) and len(value) > 10:
            score += 1.0
        elif isinstance(value, (int, float)) and value != 0:
            score += 1.0
        elif isinstance(value, bool):
            score += 1.0
        else:
            score += 0.5  # 有值但很短

    return round(score / max(max_score, 1), 2)


def validate_paper_summary(summary: PaperSummary) -> Dict[str, Any]:
    """
    验证 PaperSummary 的完整性，返回问题列表。
    用于质量门控：在进入下一阶段前检查。
    """
    issues = []

    # 基本信息检查
    if not summary.paper_title:
        issues.append({"severity": "error", "field": "paper_title", "msg": "论文标题为空"})

    # 11 维度完成度
    section_fields = [
        ("01", summary.section_01_introduction),
        ("02", summary.section_02_theoretical),
        ("03", summary.section_03_identification),
        ("04", summary.section_04_data),
        ("05", summary.section_05_methodology),
        ("06", summary.section_06_baseline),
        ("07", summary.section_07_robustness),
        ("08", summary.section_08_mechanism),
        ("09", summary.section_09_heterogeneity),
        ("10", summary.section_10_endogeneity),
        ("11", summary.section_11_conclusion),
    ]

    completed = []
    insufficient = []
    for num, section in section_fields:
        if section is not None:
            completed.append(num)
            score = compute_quality_score(section)
            if score < 0.3:
                issues.append({
                    "severity": "warning",
                    "field": f"section_{num}",
                    "msg": f"维度 {num} quality_score={score}（<0.3），信息严重不足",
                })
            if hasattr(section, 'information_sufficiency') and section.information_sufficiency == InfoSufficiency.INSUFFICIENT:
                insufficient.append(num)
        else:
            issues.append({
                "severity": "warning",
                "field": f"section_{num}",
                "msg": f"维度 {num} 未完成分析",
            })

    if insufficient:
        issues.append({
            "severity": "warning",
            "field": "information_sufficiency",
            "msg": f"{len(insufficient)} 个维度信息不足: {insufficient}",
        })

    # 实证分析
    if summary.empirical is None:
        issues.append({"severity": "info", "field": "empirical", "msg": "实证分析未完成"})
    else:
        emp_score = compute_quality_score(summary.empirical)
        if emp_score < 0.3:
            issues.append({"severity": "warning", "field": "empirical", "msg": f"实证分析 quality_score={emp_score}"})

    # 计算整体质量分
    section_scores = [compute_quality_score(s[1]) for s in section_fields if s[1] is not None]
    summary.overall_quality_score = round(sum(section_scores) / max(len(section_scores), 1), 2)
    summary.sections_completed = completed

    return {
        "quality_score": summary.overall_quality_score,
        "completed_sections": completed,
        "insufficient_sections": insufficient,
        "issues": issues,
        "passed": len([i for i in issues if i["severity"] == "error"]) == 0,
    }


# ═══════════════════════════════════════════════════════════════
# 序列化工具
# ═══════════════════════════════════════════════════════════════

def dataclass_to_dict(obj: Any) -> dict:
    """将数据类转为 JSON 可序列化的字典"""
    if obj is None:
        return None
    if hasattr(obj, '__dataclass_fields__'):
        result = {}
        for key, field_def in obj.__dataclass_fields__.items():
            value = getattr(obj, key)
            if isinstance(value, Enum):
                result[key] = value.value
            elif isinstance(value, list):
                result[key] = [dataclass_to_dict(item) for item in value]
            elif isinstance(value, dict):
                result[key] = {k: dataclass_to_dict(v) for k, v in value.items()}
            elif hasattr(value, '__dataclass_fields__'):
                result[key] = dataclass_to_dict(value)
            else:
                result[key] = value
        return result
    return obj


def dict_to_dataclass(data: dict, cls):
    """从字典恢复数据类实例（简单版，仅支持一层嵌套）"""
    if data is None:
        return None
    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}
    for key, value in data.items():
        if key not in field_types:
            continue
        # 简单类型直接赋值（枚举/列表/字典保持原样）
        kwargs[key] = value
    return cls(**kwargs)


# ═══════════════════════════════════════════════════════════════
# 11 维度 Schema 注册表
# ═══════════════════════════════════════════════════════════════

SECTION_SCHEMAS = {
    "01": Section01Introduction,
    "02": Section02TheoreticalFramework,
    "03": Section03Identification,
    "04": Section04DataVariables,
    "05": Section05EmpiricalMethodology,
    "06": Section06BaselineResults,
    "07": Section07Robustness,
    "08": Section08Mechanism,
    "09": Section09Heterogeneity,
    "10": Section10Endogeneity,
    "11": Section11Conclusion,
}

SECTION_FIELD_MAP = {
    "01": "section_01_introduction",
    "02": "section_02_theoretical",
    "03": "section_03_identification",
    "04": "section_04_data",
    "05": "section_05_methodology",
    "06": "section_06_baseline",
    "07": "section_07_robustness",
    "08": "section_08_mechanism",
    "09": "section_09_heterogeneity",
    "10": "section_10_endogeneity",
    "11": "section_11_conclusion",
}


# ═══════════════════════════════════════════════════════════════
# 论文蓝图 Schema — 三段式结构化写作的核心
# ═══════════════════════════════════════════════════════════════

@dataclass
class HypothesisBlueprint:
    """
    单条假设的完整写作约束。
    每条假设从"理论来源 → 变量定义 → 检验方法 → 预期结果 → 文献证据"全链路锁定。
    """
    id: str = ""                               # H1, H2, ...
    claim: str = ""                            # 假设陈述（一句话）
    direction: str = ""                        # 正向/负向/U型
    theory_basis: List[str] = field(default_factory=list)  # 理论基础
    theory_source_papers: List[str] = field(default_factory=list)  # 理论来源论文
    y_var: str = ""                            # 被解释变量
    y_definition: str = ""                     # Y 的测度方式
    x_var: str = ""                            # 核心解释变量
    x_definition: str = ""                     # X 的测度方式
    mediator_vars: List[str] = field(default_factory=list)  # 中介变量（如有）
    test_method: str = ""                      # 检验方法
    expected_sign: str = ""                    # 预期符号
    expected_magnitude_reference: str = ""     # 预期效应量参考（来自已有文献）
    evidence_from_literature: List[str] = field(default_factory=list)  # 支撑文献及系数
    competing_hypothesis: str = ""             # 竞争性假说
    testable: bool = True                      # 是否可检验


@dataclass
class VariableMapEntry:
    """变量映射表中的单个变量定义"""
    symbol: str = ""                           # 变量符号（如 Livability, SmartCity）
    name_cn: str = ""                          # 中文名
    role: str = ""                             # Y / X / control / mediator / moderator / IV
    definition: str = ""                       # 定义与测度方式
    unit: str = ""                             # 单位
    data_source: str = ""                      # 数据来源
    expected_sign: str = ""                    # 预期符号（对 Y 的影响方向）
    endogeneity_risk: str = ""                 # 内生性风险
    literature_precedent: List[str] = field(default_factory=list)  # 使用该变量的文献


@dataclass
class SectionContract:
    """
    每节的"写作合同"——该节必须达成的内容约定。
    写作引擎在生成该节时读取此合同，一致性审查时对照此合同检查。
    """
    section_id: str = ""                       # section_1_intro / section_2_theory / ...
    section_title: str = ""                    # 中文标题
    must_derive: List[str] = field(default_factory=list)      # 必须推导的内容
    must_define: List[str] = field(default_factory=list)      # 必须定义的概念/变量
    must_specify: Dict[str, str] = field(default_factory=dict)  # 必须指定的方程/设定
    must_report: List[str] = field(default_factory=list)      # 必须报告的结果
    must_cite: List[str] = field(default_factory=list)        # 必须引用的论文
    must_compare: List[str] = field(default_factory=list)     # 必须与文献对比的点
    must_discuss: List[str] = field(default_factory=list)     # 必须讨论的问题
    must_echo: List[str] = field(default_factory=list)        # 必须回扣的论点（来自引言）
    forbidden: List[str] = field(default_factory=list)        # 禁止出现的内容
    max_words: int = 0                         # 字数上限（0=不限）


@dataclass
class CitationContract:
    """引用约束——每篇文献的完整引用规定"""
    paper_title: str = ""
    authors_short: str = ""                    # 作者简称（如 "张三等, 2023"）
    used_in_sections: List[str] = field(default_factory=list)  # 在哪些节中出现
    claims_supported: List[str] = field(default_factory=list)  # 支撑的论点
    citation_format_gbt7714: str = ""          # GB/T 7714 引用格式
    must_appear_in_text: bool = True           # 是否必须在正文中出现
    max_citation_count: int = 3                # 最多引用次数（避免过度引用单篇）


@dataclass
class CrossSectionDependency:
    """
    跨节依赖——连接两节之间的逻辑约束。
    这是保证全文逻辑严谨性的关键数据结构。
    """
    id: str = ""                               # 依赖 ID
    from_section: str = ""                     # 来源节
    from_element: str = ""                     # 来源元素（如 "H1", "contribution_1"）
    to_section: str = ""                       # 目标节
    to_element: str = ""                       # 目标元素
    relationship: str = ""                     # 关系类型：must_echo / must_test / must_define / must_compare
    description: str = ""                      # 人类可读的描述
    verified: bool = False                     # 审查时是否已通过


@dataclass
class PaperBlueprint:
    """
    论文蓝图——全文写作的唯一约束源。

    生成于 Step 5（蓝图汇总），是整个写作流水线的核心数据结构。
    每一节写作都从此结构读取约束，一致性审查也基于此结构执行。

    ★ 每条要素都通过 provenance_map 记录其完整来源链，
    确保分段撰写时 LLM 知道"这个结论从哪篇论文的哪个分析维度得出的"。
    """
    # 元信息
    thesis_title: str = ""                     # 论文标题
    thesis_statement: str = ""                 # 核心论点（一段话，所有节必须围绕此论点）
    research_question: str = ""                # 研究问题
    contribution_claims: List[str] = field(default_factory=list)  # 边际贡献（3-4条）

    # 假设体系
    hypotheses: List[HypothesisBlueprint] = field(default_factory=list)

    # 变量体系
    variable_map: List[VariableMapEntry] = field(default_factory=list)

    # 模型设定
    baseline_model_form: str = ""              # 基准回归方程（LaTeX）
    estimation_method: str = ""                # 估计方法
    fixed_effects: List[str] = field(default_factory=list)
    standard_error_type: str = ""
    identification_strategy: str = ""          # 识别策略
    endogeneity_handling: str = ""             # 内生性处理方案

    # 分节合同
    section_contracts: Dict[str, SectionContract] = field(default_factory=dict)

    # 引用约束
    citation_contracts: List[CitationContract] = field(default_factory=list)
    # 跨节依赖
    cross_section_dependencies: List[CrossSectionDependency] = field(default_factory=list)

    # ★ 全链路溯源：记录蓝图中每个要素的完整来源
    provenance_map: Optional[ProvenanceMap] = None

    # 质量要求
    quality_checklist: List[str] = field(default_factory=list)

    # 数据源回溯
    analysis_papers_used: List[str] = field(default_factory=list)  # 从哪些论文的分析中提取
    cross_synthesis_used: bool = False         # 是否使用了跨论文对比数据
    empirical_data_available: bool = False     # 是否有实际回归结果

    # 元数据
    generated_at: str = ""
    quality_score: float = 0.0


# ═══════════════════════════════════════════════════════════════
# 全链路溯源追踪 Schema
# ═══════════════════════════════════════════════════════════════

@dataclass
class ProvenanceSource:
    """
    单个溯源来源——记录蓝图中某个决策/要素的一个具体来源。

    就像图书馆书籍上的标签：
    - source_type: 这个标签来自哪类材料（桥梁发现/单篇论文/跨论文共性/用户输入）
    - source_detail: 标签上的摘要
    - 指向具体位置：哪篇论文、哪个维度、什么发现
    """
    source_type: str = ""          # bridge / single_paper / cross_paper / empirical / user_input
    source_detail: str = ""        # 人类可读的来源描述

    # 桥梁来源
    bridge_id: str = ""            # 跨集群桥梁ID (如 "bridge_c0_c1")
    bridge_theory: str = ""        # 桥梁理论名称
    graft_logic: str = ""          # 嫁接逻辑

    # 单篇论文来源
    paper_title: str = ""          # 来源论文标题
    section_key: str = ""          # 来源维度 (如 "02", "05", "08", "empirical")
    section_title: str = ""        # 维度标题
    finding_excerpt: str = ""      # 该维度中的具体发现摘录

    # 跨论文来源
    cross_pattern: str = ""        # 共性模式描述
    cross_frequency: str = ""      # 频率统计 (如 "17/21 篇")
    cross_consensus_level: str = ""  # 共识程度

    # 质量标记
    confidence: str = "中"          # 高/中/低
    verification_status: str = ""  # 已验证/待验证/无法验证


@dataclass
class ElementProvenance:
    """
    单个蓝图要素的完整溯源链。

    蓝图中的每个关键决策——每条假设、每个变量、每个方法选择——
    都对应一个 ElementProvenance，记录这个决策从哪些来源推导而来。
    """
    element_id: str = ""           # 要素ID (如 "H1", "var_Livability", "method_DID", "claim_1")
    element_type: str = ""         # hypothesis / variable / method / mechanism / claim / model_spec
    element_label: str = ""        # 人类可读标签

    # 溯源链（按优先级从高到低排列）
    sources: List[ProvenanceSource] = field(default_factory=list)

    # 溯源完整性
    has_bridge_source: bool = False      # 是否有桥梁发现来源
    has_paper_source: bool = False       # 是否有单篇论文来源
    has_cross_source: bool = False       # 是否有跨论文共性来源
    has_empirical_source: bool = False   # 是否有实证分析来源
    is_complete: bool = False            # 溯源链是否完整（至少有1个来源）


@dataclass
class ProvenanceMap:
    """
    全链路溯源映射——蓝图的"标签系统"。

    记录蓝图中所有关键要素的完整来源链。
    在生成蓝图时填充，在分段撰写时按节查询，在一致性审查时校验。
    """
    blueprint_title: str = ""

    # 所有要素的溯源（按 element_id 索引）
    elements: Dict[str, ElementProvenance] = field(default_factory=dict)

    # 按类型快速检索
    hypotheses_provenance: Dict[str, ElementProvenance] = field(default_factory=dict)   # element_id → provenance
    variables_provenance: Dict[str, ElementProvenance] = field(default_factory=dict)
    methods_provenance: Dict[str, ElementProvenance] = field(default_factory=dict)
    claims_provenance: Dict[str, ElementProvenance] = field(default_factory=dict)

    # 统计
    total_elements: int = 0
    elements_with_bridge_source: int = 0
    elements_with_paper_source: int = 0
    overall_completeness: float = 0.0      # 溯源完整度 (0-1)

    # 获取特定节所需的所有溯源信息
    def get_provenance_for_section(self, section_id: str) -> List[ElementProvenance]:
        """
        提取特定节需要的所有要素溯源。

        section_1_intro: 需要 claims + 核心 hypothesis
        section_2_theory: 需要所有 hypotheses + 理论来源
        section_3_design: 需要 variables + methods + identification
        section_5_results: 需要 hypotheses + 实证来源 + 机制
        section_6_conclusion: 需要 claims + 所有结果
        """
        section_map = {
            "section_1_intro": ["claim", "hypothesis"],
            "section_2_theory": ["hypothesis", "mechanism"],
            "section_3_design": ["variable", "method", "model_spec"],
            "section_5_results": ["hypothesis", "mechanism", "method"],
            "section_6_conclusion": ["claim", "hypothesis"],
        }
        target_types = section_map.get(section_id, [])
        result = []
        for elem_id, elem in self.elements.items():
            if elem.element_type in target_types:
                result.append(elem)
        return result

    def format_for_section_prompt(self, section_id: str) -> str:
        """
        将本节需要的溯源信息格式化为 Prompt 可用的文本块。
        这是分段撰写时注入到每节 Prompt 中的关键材料。
        """
        elements = self.get_provenance_for_section(section_id)
        if not elements:
            return "（本节无溯源信息——使用通用分析材料）"

        parts = [f"## ★ 本节要素溯源（共 {len(elements)} 个要素，每个标注了完整来源链）\n"]
        parts.append("以下是本节需要处理的关键要素。每个要素标注了它的来源——"
                     "就像书籍上的标签，告诉你这个结论是从哪篇论文的哪个分析维度得出的。\n")

        for elem in elements:
            type_label = {"hypothesis": "假设", "variable": "变量", "method": "方法",
                         "mechanism": "机制", "claim": "贡献声明", "model_spec": "模型设定"}
            label = type_label.get(elem.element_type, elem.element_type)
            parts.append(f"### {label}: {elem.element_label}\n")

            if not elem.sources:
                parts.append("⚠️ **无溯源来源**——此要素的来源未在分析材料中找到。\n")
                continue

            for i, src in enumerate(elem.sources):
                type_icon = {"bridge": "🔗 跨集群桥梁", "single_paper": "📄 单篇论文分析",
                            "cross_paper": "📊 跨论文共性", "empirical": "🔬 实证分析",
                            "user_input": "✏️ 用户输入"}
                icon = type_icon.get(src.source_type, "❓")

                parts.append(f"**来源 {i+1}** [{icon}] 置信度: {src.confidence}")
                parts.append(f"  {src.source_detail}")

                if src.paper_title:
                    parts.append(f"  → 论文: {src.paper_title[:60]}")
                if src.section_key:
                    parts.append(f"  → 维度: {src.section_key} ({src.section_title})")
                if src.finding_excerpt:
                    parts.append(f"  → 具体发现: {src.finding_excerpt[:200]}")
                if src.bridge_theory:
                    parts.append(f"  → 桥梁理论: {src.bridge_theory}")
                if src.graft_logic:
                    parts.append(f"  → 嫁接逻辑: {src.graft_logic[:200]}")
                if src.cross_frequency:
                    parts.append(f"  → 频率: {src.cross_frequency}")
                parts.append("")

        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# 一致性审查 Schema
# ═══════════════════════════════════════════════════════════════

@dataclass
class ConsistencyFinding:
    """单条一致性审查发现"""
    id: str = ""                               # 发现编号
    severity: str = ""                         # error / warning / info
    rule: str = ""                             # 触发的规则名
    description: str = ""                      # 人类可读的描述
    source_section: str = ""                   # 问题来源章节
    target_section: str = ""                   # 问题目标章节
    source_excerpt: str = ""                   # 源文本片段
    target_excerpt: str = ""                   # 目标文本片段
    suggested_fix: str = ""                    # 建议修正方案
    fixed: bool = False                        # 是否已修正


@dataclass
class ConsistencyReport:
    """
    一致性审查报告——Pass 3 的产出。

    包含所有交叉校验发现的问题，按严重程度排序。
    writer 据此进行定点修正。
    """
    paper_title: str = ""
    generated_at: str = ""
    total_checks: int = 0
    passed: int = 0
    warnings: int = 0
    errors: int = 0
    findings: List[ConsistencyFinding] = field(default_factory=list)
    overall_verdict: str = ""                  # "通过" / "有警告" / "不通过"
    sections_reviewed: List[str] = field(default_factory=list)
    sections_needing_revision: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 蓝图构建辅助
# ═══════════════════════════════════════════════════════════════

def build_blueprint_from_summaries(
    paper_summaries: List[Dict],
    cross_synthesis: Dict = None,
    empirical_results: List[Dict] = None,
    topic_info: str = "",
    hypothesis_info: str = "",
    model_info: str = "",
    variable_info: str = "",
) -> Dict:
    """
    从已有分析数据构建 PaperBlueprint 的 LLM Prompt 输入。
    聚合所有论文的分析结果、跨论文共性和用户在前几步的选择。

    返回一个 prompt 参数 dict，供 LLM 生成 PaperBlueprint JSON。
    """
    # 汇总所有论文的假设
    all_hypotheses = []
    for ps in (paper_summaries or []):
        sections = ps.get("sections", {})
        theory = sections.get("02_theoretical_framework", {})
        hyps = theory.get("hypotheses_derived", [])
        for h in hyps:
            if isinstance(h, dict):
                all_hypotheses.append({
                    "source_paper": ps.get("paper_title", ""),
                    "id": h.get("id", ""),
                    "content": h.get("content", ""),
                })

    # 汇总变量
    all_variables = []
    for ps in (paper_summaries or []):
        sections = ps.get("sections", {})
        dv = sections.get("04_data_variables", {})
        kv = dv.get("key_variables", {})
        if kv:
            all_variables.append({
                "source_paper": ps.get("paper_title", ""),
                "y_var": kv.get("Y", {}).get("name", "") if isinstance(kv.get("Y"), dict) else str(kv.get("Y", "")),
                "x_var": kv.get("X", {}).get("name", "") if isinstance(kv.get("X"), dict) else str(kv.get("X", "")),
                "controls": kv.get("controls", []) if isinstance(kv, dict) else [],
            })

    # 汇总方法
    all_methods = []
    for ps in (paper_summaries or []):
        sections = ps.get("sections", {})
        meth = sections.get("05_empirical_methodology", {})
        if meth.get("baseline_model_form") or meth.get("estimation_method"):
            all_methods.append({
                "source_paper": ps.get("paper_title", ""),
                "model_form": meth.get("baseline_model_form", ""),
                "estimation": meth.get("estimation_method", ""),
                "fixed_effects": meth.get("fixed_effects", []),
                "se_type": meth.get("standard_error_type", ""),
            })

    # 汇总实证发现
    all_empirical_findings = []
    for er in (empirical_results or []):
        jd = er.get("json", {})
        all_empirical_findings.append({
            "source_paper": er.get("title", ""),
            "hypotheses": jd.get("hypotheses", {}),
            "y_var": jd.get("y_var", ""),
            "x_var": jd.get("x_var", ""),
            "mechanism_vars": jd.get("mechanism_vars", []),
            "key_results": jd.get("key_results", []),
            "robustness_checks": jd.get("robustness_checks", []),
        })

    return {
        "topic_info": topic_info,
        "hypothesis_info": hypothesis_info,
        "model_info": model_info,
        "variable_info": variable_info,
        "cross_synthesis": cross_synthesis or {},
        "all_hypotheses_from_literature": all_hypotheses,
        "all_variables_from_literature": all_variables,
        "all_methods_from_literature": all_methods,
        "all_empirical_findings": all_empirical_findings,
        "total_source_papers": len(paper_summaries or []),
    }


# ═══════════════════════════════════════════════════════════════
# 跨集群桥梁发现 Schema — Step 0 的核心数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class PaperCluster:
    """
    论文集群——由主题相似的多篇论文组成。
    通过 LDA/关键词相似度/LLM 自动识别。
    """
    cluster_id: str = ""                       # 集群ID
    cluster_label: str = ""                    # 人类可读的集群标签
    papers: List[str] = field(default_factory=list)        # 论文标题列表
    paper_count: int = 0
    # 集群特征摘要
    common_x_vars: List[str] = field(default_factory=list)  # 共同的核心解释变量
    common_y_vars: List[str] = field(default_factory=list)  # 共同的核心被解释变量
    common_methods: List[str] = field(default_factory=list)  # 共同的方法
    common_theories: List[str] = field(default_factory=list)  # 共同的理论
    mechanism_pool: List[str] = field(default_factory=list)  # 集群内的机制池
    heterogeneity_pool: List[str] = field(default_factory=list)  # 异质性维度池
    representative_findings: List[str] = field(default_factory=list)  # 代表性发现


@dataclass
class MechanismNode:
    """
    机制网络中的单个节点。
    从论文中提取的完整因果链片段：X → M → Y。
    """
    id: str = ""                               # 节点ID
    paper_title: str = ""                      # 来源论文
    cluster_id: str = ""                       # 所属集群
    # 因果链三要素
    x_var: str = ""                            # 原因变量
    x_definition: str = ""                     # X的定义
    y_var: str = ""                            # 结果变量
    y_definition: str = ""                     # Y的定义
    mediator_var: str = ""                     # 中介变量
    mediator_definition: str = ""              # 中介变量定义
    mechanism_name: str = ""                   # 机制名称
    mechanism_direction: str = ""              # 效应方向（+/-）
    theory_basis: str = ""                     # 理论依据
    coefficient_info: str = ""                 # 系数信息（如有）
    # 可迁移性评估
    context_dependency: str = ""               # 对情境的依赖程度（高/中/低）


@dataclass
class MechanismNetwork:
    """
    全文献池的机制网络。
    将各论文中提取的 MechanismNode 连接起来，
    识别跨集群的因果链嫁接点。
    """
    nodes: List[MechanismNode] = field(default_factory=list)
    clusters: List[PaperCluster] = field(default_factory=list)
    # 共享变量（在不同集群中扮演不同角色）
    shared_variables: List[Dict[str, Any]] = field(default_factory=list)
    # 共享机制（在不同集群中均出现）
    shared_mechanisms: List[Dict[str, Any]] = field(default_factory=list)
    # 可嫁接因果链（从集群A到集群B的因果链延伸）
    graftable_chains: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class VariableRole:
    """变量在不同集群中的角色变化"""
    variable_name: str = ""
    roles: Dict[str, str] = field(default_factory=dict)  # {"集群A": "Y", "集群B": "中介", "集群C": "X"}
    definitions: Dict[str, str] = field(default_factory=dict)  # 各集群中的定义
    bridge_potential: str = ""                 # 作为桥梁的潜力（高/中/低）


@dataclass
class TransplantableMechanism:
    """
    可移植机制——从一个集群可以"嫁接"到另一个集群的因果链。
    这是跨集群创新的核心单元。
    """
    id: str = ""
    source_cluster: str = ""                   # 来源集群
    source_mechanism_node: MechanismNode = None  # 来源机制节点
    target_cluster: str = ""                   # 目标集群
    # 嫁接逻辑
    graft_logic: str = ""                      # 为什么这个机制可以移植？
    theoretical_bridge: str = ""               # 支撑移植的桥梁理论
    # 嫁接后的新因果链
    new_x_in_target: str = ""                  # 在目标集群中新的X
    new_y_in_target: str = ""                  # 在目标集群中新的Y
    new_mechanism_path: str = ""               # 新的因果链描述
    new_hypothesis: str = ""                   # 基于此嫁接的可检验假设
    # 理论严谨性
    theoretical_support_papers: List[str] = field(default_factory=list)  # 支撑文献
    theoretical_strength: str = ""             # 理论严谨性（强/中/弱）
    # 可行性
    data_availability: str = ""                # 数据可得性
    identification_feasibility: str = ""       # 识别策略可行性
    methodological_precedent: List[str] = field(default_factory=list)  # 方法论先例


@dataclass
class ContradictoryTension:
    """
    两个集群之间的发现矛盾或张力。
    矛盾本身往往是最大的创新来源——它暗示了一个缺失的调节变量或边界条件。
    """
    id: str = ""
    cluster_a: str = ""                        # 集群A
    cluster_b: str = ""                        # 集群B
    finding_a: str = ""                        # 集群A的发现
    finding_b: str = ""                        # 集群B的发现
    contradiction_description: str = ""        # 矛盾描述
    possible_resolution: str = ""              # 可能的解决方案
    missing_moderator: str = ""                # 缺失的调节变量（如有）
    candidate_topic: str = ""                  # 基于此矛盾的候选题目


@dataclass
class ClusterBridge:
    """
    ★ 跨集群桥梁——两个主题集群之间的完整理论/方法/机制/变量桥梁分析。

    这是 BridgeDetection 的核心产出，也是增强版选题的直接输入。
    """
    id: str = ""                               # 桥梁ID
    cluster_a: str = ""                        # 集群A标签
    cluster_b: str = ""                        # 集群B标签
    cluster_a_papers: List[str] = field(default_factory=list)
    cluster_b_papers: List[str] = field(default_factory=list)

    # 1. 理论桥梁
    theoretical_bridge_summary: str = ""       # 桥梁理论的一段话总结
    bridge_theory_name: str = ""               # 桥梁理论的名称
    bridge_theory_description: str = ""        # 桥梁理论的详细说明
    theoretical_derivation: str = ""           # 从桥梁理论到新假说的完整推导链

    # 2. 机制桥梁
    shared_mechanisms: List[Dict[str, str]] = field(default_factory=list)
    transplantable_mechanisms: List[TransplantableMechanism] = field(default_factory=list)

    # 3. 方法桥梁
    methodological_insights: List[Dict[str, str]] = field(default_factory=list)

    # 4. 变量桥梁
    variable_role_changes: List[VariableRole] = field(default_factory=list)

    # 5. 矛盾与张力
    contradictions: List[ContradictoryTension] = field(default_factory=list)

    # 6. 创新题目候选
    candidate_topics: List[Dict[str, Any]] = field(default_factory=list)

    # 评分
    innovation_score: float = 0.0              # 0-10 创新性评分
    theoretical_rigor_score: float = 0.0       # 0-10 理论严谨性
    feasibility_score: float = 0.0             # 0-10 可行性
    overall_score: float = 0.0                 # 加权总评分

    # 元数据
    analysis_summary: str = ""                 # 分析过程摘要


@dataclass
class CrossClusterInnovationReport:
    """
    Step 0 的完整产出——跨集群创新空间分析报告。

    包含：
    - 所有识别的集群
    - 完整的机制网络
    - 所有集群对之间的桥梁分析
    - 按创新评分排序的候选题目
    """
    paper_pool_size: int = 0
    clusters_identified: List[PaperCluster] = field(default_factory=list)
    mechanism_network: Optional[MechanismNetwork] = None
    cluster_bridges: List[ClusterBridge] = field(default_factory=list)
    # 排序后的候选题目（去重、去低分）
    ranked_topics: List[Dict[str, Any]] = field(default_factory=list)
    # 方法论建议
    methodological_recommendations: List[str] = field(default_factory=list)
    # 元数据
    generated_at: str = ""
    total_bridges_found: int = 0
    quality_score: float = 0.0


# ═══════════════════════════════════════════════════════════════
# 回归诊断与决策 Schema — 回归结果驱动的写作方向决策
# ═══════════════════════════════════════════════════════════════

@dataclass
class HypothesisTestResult:
    """
    单条假设的实证检验结果。
    回归跑完后，每条假设都会被评估为以下状态之一。
    """
    hypothesis_id: str = ""                    # H1, H2, ...
    hypothesis_claim: str = ""                 # 假设原文
    expected_direction: str = ""               # 预期方向（+/-）
    actual_coefficient: Optional[float] = None  # 实际系数
    actual_standard_error: Optional[float] = None
    actual_significance: str = ""              # p<0.01 / p<0.05 / p<0.10 / 不显著
    actual_direction: str = ""                 # 实际方向（+/-/不显著）
    direction_match: bool = True               # 方向是否与预期一致
    coefficient_plausible: bool = True         # 系数大小是否合理（不是异常值）
    verdict: str = ""                          # 支撑/不支撑/部分支撑/反向显著
    interpretation: str = ""                   # 对结果的简要解释


@dataclass
class RegressionDiagnosis:
    """
    回归结果的完整诊断——回答"这个结果意味着什么？下一步该做什么？"

    不是简单的"显著or不显著"——而是：
    1. 每条假设的状态
    2. 如果不支撑，最可能的原因是什么
    3. 基于原因，自动推荐回退路径
    4. 无论结果如何，哪些内容可以用于写作
    """
    # 元信息
    paper_title: str = ""
    generated_at: str = ""
    total_hypotheses: int = 0
    total_tested: int = 0

    # 每条假设的结果
    hypothesis_results: List[HypothesisTestResult] = field(default_factory=list)

    # 整体判定
    supported_count: int = 0                   # 被支撑的假设数
    partial_count: int = 0                     # 部分支撑的假设数
    rejected_count: int = 0                    # 被拒绝的假设数
    overall_verdict: str = ""                  # 全部支撑 / 大部分支撑 / 部分支撑 / 大部分不支撑 / 完全不支撑

    # 如果不支撑，推断原因（多选排序）
    possible_causes: List[Dict[str, Any]] = field(default_factory=list)
    # [{"cause": "数据问题", "likelihood": "高", "evidence": "样本量过小/异常值未处理/测度误差"},
    #  {"cause": "模型误设", "likelihood": "中", "evidence": "遗漏关键控制变量/FE层级不当"},
    #  {"cause": "假设错误", "likelihood": "低", "evidence": "理论机制在新的制度情境下不适用"}]

    # 自动决策
    recommended_action: str = ""               # proceed / revise_hypotheses / revise_model / acquire_new_data / reconsider_topic
    action_rationale: str = ""                 # 推荐理由
    fallback_step: str = ""                    # 回退到哪个步骤: "2"=假设, "3"=模型, "4"=变量, "4.5"=数据, "0"=选题
    hypotheses_to_revise: List[str] = field(default_factory=list)  # 需要修正的假设ID
    hypotheses_to_drop: List[str] = field(default_factory=list)    # 需要放弃的假设ID
    variables_to_add: List[str] = field(default_factory=list)      # 可能遗漏的变量
    model_adjustments: List[str] = field(default_factory=list)     # 模型调整建议

    # 符号反向的特殊处理（往往是最有价值的发现）
    reversed_hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    # [{"hypothesis_id": "H2", "expected": "+", "actual": "-",
    #   "new_theory_interpretation": "智慧城市反而加剧了数字鸿沟，导致..."}]
    reversed_interpretation: str = ""          # 如果存在反向结果，新的理论解释

    # ★ 无论如何，有哪些内容可以进入写作
    writable_findings: List[Dict[str, Any]] = field(default_factory=list)
    # [{"finding": "H1得到支撑，效应量为X", "writing_section": "5.1",
    #   "evidence_level": "强"},
    #  {"finding": "H2不显著，可能因为样本量不足", "writing_section": "5.4",
    #   "evidence_level": "弱，需作为局限讨论"}]

    # 质量元数据
    diagnosis_quality_score: float = 0.0       # 诊断本身的质量分


@dataclass
class RegressionDecision:
    """
    基于回归诊断的结构化决策——告诉系统下一步做什么。

    这是一个明确的指令，不依赖 LLM 的"判断"。
    """
    # 决策类型
    decision_type: str = ""                    # PROCEED / REVISE_HYPOTHESES / REVISE_MODEL / REVISE_VARIABLES / ACQUIRE_DATA / RECONSIDER_TOPIC

    # 如果 PROCEED：可以直接生成蓝图
    blueprint_ready: bool = False

    # 如果 REVISE_*：具体修正内容
    revision_instructions: Dict[str, Any] = field(default_factory=dict)
    # {"hypotheses_to_modify": ["H2"], "new_model_spec": "...", "variables_to_add": [...]}
    target_step: str = ""                      # 回退到哪个步骤

    # 推荐运行的新回归（如有）
    suggested_regressions: List[Dict[str, Any]] = field(default_factory=list)

    # 元数据
    diagnosis_summary: str = ""
    decision_confidence: str = ""              # 高/中/低


# ═══════════════════════════════════════════════════════════════
# 桥梁发现辅助
# ═══════════════════════════════════════════════════════════════

def extract_mechanism_nodes_from_summaries(
    paper_summaries: List[Dict],
) -> List[MechanismNode]:
    """
    从 _paper_summary.json 列表中提取所有可用的机制节点（因果链片段）。

    每篇论文的 section_08 (机制分析) 和 empirical 字段是主要来源。
    """
    nodes = []
    for ps in (paper_summaries or []):
        title = ps.get("paper_title", "")
        sections = ps.get("sections", {})

        # 从 section_04 获取 Y 和 X
        dv = sections.get("04_data_variables", {})
        kv = dv.get("key_variables", {})
        y_var = ""
        x_var = ""
        if isinstance(kv.get("Y"), dict):
            y_var = kv["Y"].get("name", "")
        else:
            y_var = str(kv.get("Y", ""))
        if isinstance(kv.get("X"), dict):
            x_var = kv["X"].get("name", "")
        else:
            x_var = str(kv.get("X", ""))

        # 从 section_02 获取理论
        theory_sec = sections.get("02_theoretical_framework", {})
        theories = theory_sec.get("theories_used", [])

        # 从 section_08 获取机制通道
        mech_sec = sections.get("08_mechanism", {})
        channels = mech_sec.get("mechanism_channels", [])
        if isinstance(channels, list):
            for ch in channels:
                if isinstance(ch, dict):
                    nodes.append(MechanismNode(
                        paper_title=title,
                        x_var=x_var,
                        y_var=y_var,
                        mediator_var=ch.get("mediator_variable", ""),
                        mechanism_name=ch.get("name", ""),
                        mechanism_direction=ch.get("effect_direction", ""),
                        theory_basis="; ".join(theories[:2]) if theories else "",
                        coefficient_info=ch.get("evidence_strength", ""),
                    ))
                elif isinstance(ch, str):
                    nodes.append(MechanismNode(
                        paper_title=title,
                        x_var=x_var,
                        y_var=y_var,
                        mechanism_name=ch,
                        theory_basis="; ".join(theories[:2]) if theories else "",
                    ))

        # 从 empirical 补充
        emp = sections.get("empirical", {})
        emp_y = emp.get("y_var", "")
        emp_x = emp.get("x_var", "")
        emp_mechs = emp.get("mechanism_vars", [])
        if isinstance(emp_mechs, list):
            for mv in emp_mechs:
                # 避免重复
                if not any(n.mediator_var == mv and n.paper_title == title for n in nodes):
                    nodes.append(MechanismNode(
                        paper_title=title,
                        x_var=emp_x or x_var,
                        y_var=emp_y or y_var,
                        mediator_var=mv if isinstance(mv, str) else "",
                        mechanism_name=mv if isinstance(mv, str) else str(mv),
                        theory_basis=emp.get("endogeneity_strategy", ""),
                    ))

    return nodes


def cluster_papers_by_topic(
    paper_summaries: List[Dict],
) -> List[PaperCluster]:
    """
    基于标题关键词 + X/Y 变量 + 理论框架的相似度，将论文聚类为主题集群。

    使用两阶段聚类：
    1. 粗聚类：基于标题中的核心主题词（智慧城市/金融化/数据跨境/耐心资本/...）
    2. 细聚类：基于 X/Y 变量名相似度（对粗聚类内部的细分）
    """

    if len(paper_summaries) < 2:
        return [
            PaperCluster(
                cluster_id="c0",
                cluster_label=paper_summaries[0].get("paper_title", "唯一论文")[:40] if paper_summaries else "空",
                papers=[ps.get("paper_title", "") for ps in (paper_summaries or [])],
                paper_count=len(paper_summaries or []),
            )
        ]

    # ── 阶段1: 粗聚类（基于标题核心主题词）──
    # 定义核心主题词的检测规则
    TOPIC_PATTERNS = [
        ("智慧城市", ["智慧城市", "智慧社区", "数智化", "数字化转型"]),
        ("企业金融化", ["金融化", "脱实向虚", "金融资产", "金融周期", "金融投资"]),
        ("数据跨境流动", ["数据跨境", "跨境数据", "数据流动", "数字贸易", "数字化交付"]),
        ("耐心资本与创新", ["耐心资本", "政府基金", "核心技术突破", "关键核心技术"]),
        ("政策试点过程", ["试点单位", "试点推广", "政策过程", "科学性"]),
    ]

    # 为每篇论文分配主题标签
    paper_topics = []
    for ps in paper_summaries:
        title = ps.get("paper_title", "")
        abstract = ps.get("abstract", "")
        keywords = " ".join(ps.get("keywords", []) or [])
        full_text = title + " " + abstract[:200] + " " + keywords

        matched_topics = []
        for topic_label, patterns in TOPIC_PATTERNS:
            for pat in patterns:
                if pat in full_text:
                    matched_topics.append(topic_label)
                    break

        if not matched_topics:
            # 回退：使用标题前20字符
            matched_topics.append(title[:30])
        paper_topics.append(matched_topics)

    # 按主主题分组
    topic_groups: Dict[str, List[int]] = {}
    for i, topics in enumerate(paper_topics):
        primary = topics[0]  # 第一个匹配的主题作为主主题
        topic_groups.setdefault(primary, []).append(i)

    # ── 阶段2: 构建集群 ──
    clusters = []
    for topic_label, indices in topic_groups.items():
        if len(indices) == 0:
            continue

        cluster_titles = [paper_summaries[i].get("paper_title", "") for i in indices]

        # 收集集群特征
        y_vars = set()
        x_vars = set()
        methods = set()
        theories = set()
        mech_pool = set()

        for i in indices:
            ps = paper_summaries[i]
            sections = ps.get("sections", {})
            emp = sections.get("empirical", {})
            meth = sections.get("05_empirical_methodology", {})

            # Y/X
            y = emp.get("y_var", "")
            x = emp.get("x_var", "")
            # 清理：如果 Y/X 是长文本（说明 JSON 提取失败），截取短片段
            if len(y) > 30:
                y = ""
            if len(x) > 30:
                x = ""
            if y:
                y_vars.add(y)
            if x:
                x_vars.add(x)

            # 方法
            est = meth.get("estimation_method", "")
            if est and len(est) < 30:
                methods.add(est)

            # 理论
            theory_sec = sections.get("02_theoretical_framework", {})
            for t in (theory_sec.get("theories_used", []) or []):
                if isinstance(t, str) and len(t) < 50:
                    theories.add(t)

            # 机制
            mech_sec = sections.get("08_mechanism", {})
            channels = mech_sec.get("mechanism_channels", [])
            if isinstance(channels, list):
                for ch in channels:
                    if isinstance(ch, dict) and ch.get("name"):
                        mech_pool.add(ch["name"][:40])

        cluster = PaperCluster(
            cluster_id=f"c{len(clusters)}",
            cluster_label=topic_label,
            papers=cluster_titles,
            paper_count=len(cluster_titles),
            common_y_vars=list(y_vars)[:5],
            common_x_vars=list(x_vars)[:5],
            common_methods=list(methods)[:5],
            common_theories=list(theories)[:10],
            mechanism_pool=list(mech_pool)[:10],
        )
        clusters.append(cluster)

    # 如果只产生了一个集群，但论文数≥5，尝试用细聚类拆分
    if len(clusters) == 1 and clusters[0].paper_count >= 5:
        return _split_large_cluster(clusters[0], paper_summaries)

    return clusters


def _split_large_cluster(
    cluster: PaperCluster,
    paper_summaries: List[Dict],
) -> List[PaperCluster]:
    """对一个大型集群内的论文进行基于Y变量相似度的细分"""
    # 构建论文标题到索引的映射
    title_to_idx = {}
    for i, ps in enumerate(paper_summaries):
        title_to_idx[ps.get("paper_title", "")] = i

    # 按 Y 变量分组
    y_groups: Dict[str, List[str]] = {}
    for title in cluster.papers:
        idx = title_to_idx.get(title)
        if idx is None:
            continue
        ps = paper_summaries[idx]
        sections = ps.get("sections", {})
        emp = sections.get("empirical", {})
        y = emp.get("y_var", "")
        if len(y) > 30:
            y = title[:20]  # 回退：用标题
        y_groups.setdefault(y, []).append(title)

    if len(y_groups) <= 1:
        return [cluster]

    sub_clusters = []
    for y_var, titles in y_groups.items():
        sub = PaperCluster(
            cluster_id=f"{cluster.cluster_id}_sub{len(sub_clusters)}",
            cluster_label=f"{cluster.cluster_label}: {y_var[:30]}" if y_var else cluster.cluster_label,
            papers=titles,
            paper_count=len(titles),
            common_y_vars=[y_var] if y_var else [],
            common_x_vars=cluster.common_x_vars,
            common_methods=cluster.common_methods,
            common_theories=cluster.common_theories,
        )
        sub_clusters.append(sub)

    return sub_clusters
