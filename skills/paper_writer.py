import os
import json
import re
from skills.base import BaseSkill
from skills.llm_client import LlmClient


class PaperWriter(BaseSkill):
    """
    全流程论文写作技能。
    覆盖：选题 → 假设 → 模型选择 → 变量选取 → 结论 → 全文写作。
    全部由 LLM 驱动，核心数据源为：
      - _paper_summary.json（每篇论文的结构化记忆）
      - _cross_paper_summary.json / _writing_synthesis.json（跨论文共性数据）
    """

    def __init__(self):
        super().__init__(
            name="PaperWriter",
            description="LLM驱动的论文写作技能——选题、假设、模型、变量、结论、全文"
        )
        self.llm = LlmClient()
        self._prompts_dir = os.path.abspath("references/prompts")
        self._output_dir = os.path.abspath("workspace/writing")

    # ─── 公共入口 ──────────────────────────────────────────────

    def execute(self, action: str, **kwargs):
        if action == "select_topic":
            return self._select_topic(**kwargs)
        elif action == "formulate_hypothesis":
            return self._formulate_hypothesis(**kwargs)
        elif action == "select_model":
            return self._select_model(**kwargs)
        elif action == "select_variables":
            return self._select_variables(**kwargs)
        elif action == "write_conclusion":
            return self._write_conclusion(**kwargs)
        elif action == "write_full_paper":
            return self._write_full_paper(**kwargs)
        else:
            raise NotImplementedError(f"未实现的动作: {action}")

    # ─── 选题 ──────────────────────────────────────────────────

    def _select_topic(
        self,
        review_text: str = "",
        paper_summaries: list = None,
        cross_synthesis: dict = None,
        section_results: list = None,
        empirical_results: list = None,
        papers: list = None,
        bridge_report: dict = None,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        从分析报告中提取候选题目。

        ★ 增强版：注入跨集群桥梁分析结果。
        如果有 bridge_report，优先推荐来自桥梁的选题。
        """
        print(f"\n[{self.name}] 正在基于分析报告生成候选题目...")
        if bridge_report:
            print(f"[{self.name}]   ★ 跨集群桥梁模式：{bridge_report.get('bridge_count', 0)} 个桥梁, "
                  f"{bridge_report.get('topic_count', 0)} 个候选题目")

        prompt_path = os.path.join(self._prompts_dir, "topic_selection.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()

        # 从综述提取 Gaps
        review_gaps = self._extract_section(review_text, "七、研究空缺")
        if not review_gaps:
            review_gaps = self._extract_section(review_text, "研究空缺")

        # 从 paper_summaries 汇总 Gaps
        analysis_gaps = self._collect_all_gaps_from_summaries(paper_summaries or [])

        # 从跨论文数据提取共识空缺
        cross_consensus_gaps = self._format_consensus_gaps(cross_synthesis or {})

        # 格式化跨论文共性数据
        cross_synthesis_text = self._format_cross_synthesis_for_prompt(cross_synthesis or {})

        # ★ 格式化跨集群桥梁数据
        bridge_text = self._format_bridge_report_for_prompt(bridge_report)

        # 创新空间
        innovation_spaces = ""
        if empirical_results:
            for er in empirical_results:
                innovation_spaces += f"## {er.get('title', '')}\n"
                innovation_spaces += er.get("markdown", "")[:2000] + "\n"

        # 论文摘要
        papers_summary = self._format_papers_summary(paper_summaries or [], papers)

        full_prompt = (template
            .replace("{bridge_analysis}", bridge_text or "（未运行跨集群桥梁检测——仅使用集群内增量选题）")
            .replace("{review_gaps}", review_gaps or "（综述中未找到Gap章节）")
            .replace("{analysis_gaps}", analysis_gaps or "（无分析Gap数据）")
            .replace("{cross_consensus_gaps}", cross_consensus_gaps or "（无跨论文共识空缺数据）")
            .replace("{cross_synthesis}", cross_synthesis_text or "（无跨论文共性数据）")
            .replace("{innovation_spaces}", innovation_spaces or "（无创新推断数据）")
            .replace("{papers_summary}", papers_summary or "（无论文摘要）"))

        print(f"[{self.name}] 选题Prompt: {len(full_prompt)} 字符")
        try:
            raw = self.llm.execute(
                prompt=full_prompt,
                system_prompt="你是一位经济学博士生导师，正在指导学生选题。请严格遵循输出格式，标注每个推荐的支撑论文，末尾完成质量自检。",
                backend=backend, model=model, max_tokens=6000)
        except Exception as e:
            return {"success": False, "error": str(e)}

        os.makedirs(self._output_dir, exist_ok=True)
        path = os.path.join(self._output_dir, "topic_proposals.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)

        print(f"[{self.name}] 候选题目生成完成 → {path}")
        return {"success": True, "markdown": raw, "path": path}

    # ─── 假设 ──────────────────────────────────────────────────

    def _formulate_hypothesis(
        self,
        topic_info: str,
        paper_summaries: list = None,
        cross_synthesis: dict = None,
        section_results: list = None,
        empirical_results: list = None,
        bridge_report: dict = None,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        根据选题提出研究假设。

        ★ 增强版：注入跨集群桥梁数据，要求每条假设标注桥梁理论来源。
        """
        print(f"\n[{self.name}] 正在提出研究假设...")
        if bridge_report:
            print(f"[{self.name}]   ★ 桥梁约束模式")

        prompt_path = os.path.join(self._prompts_dir, "hypothesis.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()

        mechanism_summary = self._collect_mechanisms_from_summaries(paper_summaries or [])
        theory_summary = self._collect_theories_from_summaries(paper_summaries or [])
        hypothesis_reference = self._collect_hypotheses_from_summaries(paper_summaries or [])
        cross_synthesis_text = self._format_cross_synthesis_for_prompt(cross_synthesis or {})

        # ★ 格式化桥梁数据
        bridge_text = self._format_bridge_data_for_hypothesis(bridge_report, topic_info)

        full_prompt = (template
            .replace("{topic_info}", topic_info)
            .replace("{bridge_data}", bridge_text or "（选题未使用跨集群桥梁——使用集群内传统推导）")
            .replace("{cross_synthesis}", cross_synthesis_text or "（无跨论文共性数据）")
            .replace("{mechanism_summary}", mechanism_summary or "（无机制数据）")
            .replace("{theory_summary}", theory_summary or "（无理论数据）")
            .replace("{hypothesis_reference}", hypothesis_reference or "（无假设参考）"))

        try:
            raw = self.llm.execute(
                prompt=full_prompt,
                system_prompt="你是一位经济学理论研究者，请构建逻辑自洽、可检验、有理论深度的研究假设体系。严格遵循输出格式，每项假设标注理论基础和检验方法。",
                backend=backend, model=model, max_tokens=6000)
        except Exception as e:
            return {"success": False, "error": str(e)}

        os.makedirs(self._output_dir, exist_ok=True)
        path = os.path.join(self._output_dir, "hypotheses.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)

        print(f"[{self.name}] 假设生成完成 → {path}")
        return {"success": True, "markdown": raw, "path": path}

    # ─── 模型选择 ──────────────────────────────────────────────

    def _select_model(
        self,
        topic_and_hypothesis: str,
        paper_summaries: list = None,
        cross_synthesis: dict = None,
        section_results: list = None,
        empirical_results: list = None,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """推荐基准计量模型，基于跨论文频率统计"""
        print(f"\n[{self.name}] 正在推荐计量模型...")

        prompt_path = os.path.join(self._prompts_dir, "model_selection.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()

        model_statistics = self._collect_model_stats_from_summaries(paper_summaries or [])
        identification_statistics = self._collect_id_stats_from_summaries(paper_summaries or [])
        cross_synthesis_text = self._format_cross_synthesis_for_prompt(cross_synthesis or {})

        full_prompt = (template
            .replace("{topic_and_hypothesis}", topic_and_hypothesis)
            .replace("{cross_synthesis}", cross_synthesis_text or "（无跨论文共性数据）")
            .replace("{model_statistics}", model_statistics or "（无模型统计）")
            .replace("{identification_statistics}", identification_statistics or "（无识别策略统计）"))

        try:
            raw = self.llm.execute(
                prompt=full_prompt,
                system_prompt="你是一位计量经济学方法论专家，请推荐最合适的实证模型，附带完整的诊断检验清单和实施指南。",
                backend=backend, model=model, max_tokens=6000)
        except Exception as e:
            return {"success": False, "error": str(e)}

        os.makedirs(self._output_dir, exist_ok=True)
        path = os.path.join(self._output_dir, "model_recommendation.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)

        print(f"[{self.name}] 模型推荐完成 → {path}")
        return {"success": True, "markdown": raw, "path": path}

    # ─── 变量选取 ──────────────────────────────────────────────

    def _select_variables(
        self,
        topic_and_model: str,
        paper_summaries: list = None,
        cross_synthesis: dict = None,
        section_results: list = None,
        empirical_results: list = None,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """根据模型和假设推荐变量体系，基于跨论文变量频率统计"""
        print(f"\n[{self.name}] 正在推荐变量体系...")

        var_stats = self._collect_variable_stats_from_summaries(paper_summaries or [])
        cross_synthesis_text = self._format_cross_synthesis_for_prompt(cross_synthesis or {})

        var_prompt = f"""你是一位经济学实证研究专家。请根据以下材料，为论文推荐完整的变量体系。

【论文题目、假设与模型】
{topic_and_model}

【跨论文共性数据（变量频率统计、共识测度方式）】
{cross_synthesis_text or '（无跨论文共性数据）'}

【论文素材中的变量测度统计（来自 _paper_summary.json）】
{var_stats}

【输出格式】

### 一、被解释变量（Y）

| 变量名 | 变量符号 | 定义与测度方式 | 预期符号 | 内生性风险 | 数据来源建议 | 论文素材中使用频率 | 支撑论文 |
|--------|---------|--------------|---------|-----------|-------------|-----------------|---------|

### 二、核心解释变量（X）

| 变量名 | 变量符号 | 定义与测度方式 | 预期符号 | 内生性风险 | 数据来源建议 | 论文素材中使用频率 | 支撑论文 |
|--------|---------|--------------|---------|-----------|-------------|-----------------|---------|

### 三、中介变量

| 变量名 | 变量符号 | 对应假设 | 定义与测度方式 | 数据来源建议 | 论文素材中使用频率 | 支撑论文 |
|--------|---------|---------|--------------|-------------|-----------------|---------|

### 四、调节变量（异质性分析用）

| 变量名 | 变量符号 | 调节的效应 | 分组方式 | 数据来源建议 | 支撑论文 |
|--------|---------|----------|---------|-------------|---------|

### 五、控制变量

| 变量名 | 变量符号 | 定义与测度方式 | 选取理由 | 预期符号 | 数据来源建议 | 论文素材中使用频率 | 支撑论文 |
|--------|---------|--------------|---------|---------|-------------|-----------------|---------|

### 六、工具变量（如需）

| 变量名 | 变量符号 | 定义与测度方式 | 相关性论证 | 排他性论证 | 数据来源建议 | 论文素材先例 |
|--------|---------|--------------|----------|----------|-------------|-----------|

### 七、变量体系整体评估
- 变量体系的完备性（是否覆盖了假设检验需要的全部变量？）
- 变量之间的共线性风险评估
- 变量测度的整体可靠性评估
- 数据获取的总体可行性

【引用约束】
- 每个变量的"支撑论文"列必须标注来自输入材料的真实论文
- 优先推荐在论文素材中高频使用的测度方式
- 如果某变量没有论文素材先例，标注"⚠️ 无先例，需自行论证"

【质量自检】
- [ ] 每个 Y 和 X 变量有论文素材测度先例？
- [ ] 中介变量与假设一一对应？
- [ ] 控制变量有明确的选取理由（非随意堆砌）？
- [ ] 工具变量有相关性论证 + 排他性论证？
- [ ] 变量内生性风险已逐项评估？
- [ ] 数据源在中国情境下可得？
- [ ] 变量符号不与论文素材已有惯例冲突？
"""

        try:
            raw = self.llm.execute(
                prompt=var_prompt,
                system_prompt="你是一位经济学实证研究专家，请推荐完整的变量体系。每个变量必须标注论文素材先例和内生性风险。",
                backend=backend, model=model, max_tokens=6000)
        except Exception as e:
            return {"success": False, "error": str(e)}

        os.makedirs(self._output_dir, exist_ok=True)
        path = os.path.join(self._output_dir, "variable_selection.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)

        print(f"[{self.name}] 变量选取完成 → {path}")
        return {"success": True, "markdown": raw, "path": path}

    # ─── 结论写作 ──────────────────────────────────────────────

    def _write_conclusion(
        self,
        regression_results: str,
        topic_info: str,
        cross_synthesis: dict = None,
        paper_summaries: list = None,
        empirical_results: list = None,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """基于回归结果撰写结论与政策建议，与已有文献对话"""
        prompt_path = os.path.join(self._prompts_dir, "conclusion_writing.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
            cross_synthesis_text = self._format_cross_synthesis_for_prompt(cross_synthesis or {})
            papers_fulltext = self._format_papers_summary(paper_summaries or [])
            prompt = (template
                .replace("{topic_and_findings}", topic_info)
                .replace("{regression_results}", regression_results)
                .replace("{robustness_summary}", "稳健性检验详见实证报告。")
                .replace("{cross_synthesis}", cross_synthesis_text or "（无跨论文共性数据）")
                .replace("{papers_fulltext}", papers_fulltext or "（无参考论文全文数据）"))
        else:
            pt = self._format_papers_summary(paper_summaries or [])
            prompt = f"""基于以下论文信息和回归结果，撰写结论与政策建议。

{topic_info}

{pt}

【回归结果摘要】
{regression_results}

请输出：核心结论（标注实证支撑+文献对比）→ 政策启示（按可操作性分级）→ 研究局限（可修复/本质/外部有效性）→ 未来方向。"""

        try:
            raw = self.llm.execute(
                prompt=prompt,
                system_prompt="你是一位经济学研究者，请撰写论文结论。每项结论标注实证支撑并与已有文献对话，每项政策建议标注可操作性等级。",
                backend=backend, model=model, max_tokens=5000)
        except Exception as e:
            return {"success": False, "error": str(e)}

        path = os.path.join(self._output_dir, "conclusion.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)
        return {"success": True, "markdown": raw, "path": path}

    # ─── 完整论文写作 ──────────────────────────────────────────

    def _write_full_paper(
        self,
        topic_and_hypothesis: str = "",
        model_and_variables: str = "",
        cross_synthesis: dict = None,
        empirical_results: str = "",
        literature_review: str = "",
        paper_summaries: list = None,
        backend: str = None,
        model: str = None,
        # 向后兼容
        all_materials: str = "",
    ) -> dict:
        """
        撰写完整论文。优先使用新的分项输入，回退到旧的 all_materials。
        """
        print(f"\n[{self.name}] 正在撰写完整论文...")

        prompt_path = os.path.join(self._prompts_dir, "full_paper_writing.txt")
        if not os.path.exists(prompt_path):
            # 回退：无模板时使用旧逻辑
            prompt = f"""请根据以下材料撰写一篇完整的经济学实证论文。

{all_materials or topic_and_hypothesis}

【论文结构】摘要→引言→理论分析→研究设计→实证结果→稳健性→结论→参考文献"""
            try:
                raw = self.llm.execute(
                    prompt=prompt,
                    system_prompt="你是一位经济学教授，请撰写一篇完整的实证论文。",
                    backend=backend, model=model, max_tokens=10000)
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()

            # 组装各分项输入
            cross_synthesis_text = self._format_cross_synthesis_for_prompt(cross_synthesis or {})

            # 构建可引用论文清单
            citation_list = self._build_citation_list(paper_summaries or [])

            # 构建质量标准
            quality_checklist = self._build_quality_checklist()

            # 文献综述文本
            lit_review_text = literature_review or ""
            if not lit_review_text:
                lr_path = os.path.abspath("workspace/literature_review.md")
                if os.path.exists(lr_path):
                    with open(lr_path, "r", encoding="utf-8") as f:
                        lit_review_text = f.read()[:8000]

            full_prompt = (template
                .replace("{topic_and_hypothesis}", topic_and_hypothesis or all_materials[:3000])
                .replace("{model_and_variables}", model_and_variables or "")
                .replace("{cross_synthesis}", cross_synthesis_text or "（无跨论文共性数据）")
                .replace("{empirical_results}", empirical_results or "（见实证回归产出）")
                .replace("{literature_review}", lit_review_text or "（见文献综述）")
                .replace("{citation_list}", citation_list)
                .replace("{quality_checklist}", quality_checklist))

            print(f"[{self.name}] 全文Prompt: {len(full_prompt)} 字符")

            try:
                raw = self.llm.execute(
                    prompt=full_prompt,
                    system_prompt="你是一位经济学教授，正在撰写一篇完整的实证论文。严格遵循学术规范，每个论断标注支撑论文，不编造任何数据或结论。完成后进行质量自检。",
                    backend=backend, model=model, max_tokens=12000)
            except Exception as e:
                return {"success": False, "error": str(e)}

        os.makedirs(self._output_dir, exist_ok=True)
        path = os.path.join(self._output_dir, "full_paper.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)

        print(f"[{self.name}] 完整论文 → {path}")
        return {"success": True, "markdown": raw, "path": path}

    # ═══════════════════════════════════════════════════════════
    # 格式化辅助方法
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _format_cross_synthesis_for_prompt(cross_synthesis: dict) -> str:
        """将跨论文共性数据格式化为 Prompt 可用的文本块"""
        if not cross_synthesis:
            return ""

        parts = []

        # Meta info
        meta = cross_synthesis.get("meta", {})
        if meta:
            parts.append(f"**论文数量**: {meta.get('total_papers', 0)}")
            papers_list = meta.get("papers", [])
            if papers_list:
                parts.append(f"**论文列表**: {', '.join(papers_list[:10])}")

        # Dimension insights summary
        dim_insights = cross_synthesis.get("dimension_insights", {})
        if dim_insights:
            parts.append("\n### 各维度共性摘要")
            for dim_key, dim_data in dim_insights.items():
                patterns = dim_data.get("common_patterns", [])
                gaps = dim_data.get("consensus_gaps", [])
                takeaway = dim_data.get("key_takeaway", "")
                if patterns or gaps:
                    parts.append(f"\n**{dim_key}**:")
                    if takeaway:
                        parts.append(f"  - 核心启示: {takeaway}")
                    for p in patterns[:3]:
                        if isinstance(p, dict):
                            parts.append(f"  - 共性: {p.get('pattern', '')} (覆盖 {p.get('papers_count', 0)} 篇)")

        # Empirical insights summary
        emp_insights = cross_synthesis.get("empirical_insights", {})
        if emp_insights:
            parts.append("\n### 实证方面共性摘要")
            for emp_key, emp_data in emp_insights.items():
                patterns = emp_data.get("common_patterns", [])
                freq = emp_data.get("frequency_table", {})
                takeaway = emp_data.get("key_takeaway", "")
                if patterns or freq:
                    parts.append(f"\n**{emp_key}**:")
                    if takeaway:
                        parts.append(f"  - 核心启示: {takeaway}")
                    if freq:
                        freq_str = ", ".join(f"{k}: {v}" for k, v in sorted(freq.items(), key=lambda x: -x[1])[:5])
                        parts.append(f"  - 频率统计: {freq_str}")

        # Synthesis for writing
        sfw = cross_synthesis.get("synthesis_for_writing", {})
        if sfw:
            top_gaps = sfw.get("top_gaps", [])
            if top_gaps:
                parts.append("\n### 共识空缺 (Top 5)")
                for g in top_gaps[:5]:
                    if isinstance(g, dict):
                        papers = g.get("source_papers", [])
                        parts.append(f"- {g.get('description', '')} (来源: {', '.join(papers[:3])})")

            freq_summary = sfw.get("frequency_summary", {})
            if freq_summary:
                parts.append("\n### 方法/变量频率统计")
                for k, v in freq_summary.items():
                    if isinstance(v, dict):
                        top_items = sorted(v.items(), key=lambda x: -x[1])[:5]
                        parts.append(f"- {k}: {', '.join(f'{item}({count})' for item, count in top_items)}")

        # Narrative synthesis (from _writing_synthesis.json)
        narrative = cross_synthesis.get("narrative_synthesis", "")
        if narrative:
            parts.append(f"\n### 综合推荐叙述\n{narrative[:2000]}")

        return "\n".join(parts) if parts else ""

    @staticmethod
    def _format_consensus_gaps(cross_synthesis: dict) -> str:
        """格式化共识空缺为文本"""
        sfw = cross_synthesis.get("synthesis_for_writing", {})
        top_gaps = sfw.get("top_gaps", [])
        if not top_gaps:
            return ""
        parts = ["以下是被多篇论文共同指向但尚未被充分研究的问题：", ""]
        for i, g in enumerate(top_gaps[:10]):
            if isinstance(g, dict):
                papers = g.get("source_papers", [])
                parts.append(f"{i+1}. **{g.get('description', '')}**")
                parts.append(f"   来源论文: {', '.join(papers[:5])}")
                parts.append(f"   来源维度: {g.get('source_dimension', '')}")
        return "\n".join(parts)

    @staticmethod
    def _format_papers_summary(paper_summaries: list = None, papers: list = None) -> str:
        """格式化论文摘要（含 fulltext）"""
        parts = []
        if paper_summaries:
            for ps in paper_summaries:
                parts.append(
                    f"- **{ps.get('paper_title', '')}** "
                    f"({ps.get('authors', '')}, {ps.get('source', '')}, {ps.get('pub_date', '')})"
                )
                abstract = ps.get("abstract", "")
                if abstract:
                    parts.append(f"  摘要: {abstract[:300]}")
                fulltext = ps.get("fulltext", "")
                if fulltext:
                    parts.append(f"  PDF全文（{len(fulltext)}字符）: {fulltext[:5000]}")
        elif papers:
            for p in papers:
                parts.append(
                    f"- **{p.get('title', '')}** ({p.get('authors', '')}, "
                    f"{p.get('source', '')}, {p.get('pub_date', '')})"
                )
                abstract = p.get("abstract", "")
                if abstract:
                    parts.append(f"  摘要: {abstract[:300]}")
                fulltext = p.get("fulltext", "")
                if fulltext:
                    parts.append(f"  PDF全文（{len(fulltext)}字符）: {fulltext[:5000]}")
        return "\n".join(parts) if parts else ""

    @staticmethod
    def _build_citation_list(paper_summaries: list) -> str:
        """构建可引用论文清单（硬约束——只能引用这些论文）"""
        if not paper_summaries:
            return "（无可引用论文清单——请从输入材料中提取）"

        parts = ["以下论文可以被引用到正文和参考文献中：", ""]
        for i, ps in enumerate(paper_summaries):
            title = ps.get("paper_title", "未知")
            authors = ps.get("authors", "未知")
            source = ps.get("source", "未知")
            pub_date = ps.get("pub_date", "未知")
            parts.append(f"{i+1}. {authors}. {title}[J]. {source}, {pub_date}.")
        parts.append("")
        parts.append("**重要**: 只能引用以上论文。不得引用清单之外的任何论文，除非是经济学经典教科书（如 Greene, Wooldridge, Angrist & Pischke）。")
        return "\n".join(parts)

    @staticmethod
    def _build_quality_checklist() -> str:
        """构建按章节的学术质量标准"""
        return """
【按章节质量标准】

### 摘要
- [ ] 包含问题-方法-发现-含义四要素
- [ ] 200-300字

### 引言
- [ ] 第1段清晰陈述研究问题与制度背景
- [ ] 引用 ≥ 5 篇可引用论文清单中的论文
- [ ] 文献缺口是具体的（非"鲜有研究"）
- [ ] 本文贡献逐维度列出（识别/数据/机制/异质性）

### 理论分析与研究假设
- [ ] 理论基础明确（标注理论名称+来源）
- [ ] 每条假设有方向性预测
- [ ] 每条假设有可检验性评估
- [ ] 讨论了竞争性假说

### 研究设计
- [ ] 数据来源完整（名称/版本/时间）
- [ ] 变量测度有论文素材先例
- [ ] 回归方程完整（含下标/FE/误差项）
- [ ] 标准误聚类有论证

### 实证结果
- [ ] 每表有编号和标题
- [ ] 系数标注显著性星号
- [ ] 核心发现与文献进行了比较
- [ ] 区分了统计显著性与经济显著性

### 稳健性与内生性
- [ ] ≥ 3 种不同类型的稳健性检验
- [ ] 内生性处理假设有逐一论证
- [ ] 讨论了残余内生性担忧

### 结论
- [ ] 每项结论有实证支撑
- [ ] 政策建议按可操作性分级
- [ ] 局限覆盖可修复/本质/外部有效性

### 参考文献
- [ ] 全部来自可引用论文清单
- [ ] 每篇被引论文在正文中出现 ≥ 1 次
- [ ] 格式符合 GB/T 7714
"""

    # ═══════════════════════════════════════════════════════════
    # 数据收集辅助方法（基于 _paper_summary.json）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _extract_section(text: str, keyword: str) -> str:
        """从Markdown文本中提取特定章节"""
        pattern = rf'##\s+[^#]*{keyword}[^#]*\n(.*?)(?=\n##\s+|\Z)'
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip()[:3000] if m else ""

    @staticmethod
    def _collect_all_gaps_from_summaries(paper_summaries: list) -> str:
        """从 paper_summaries 汇总所有 Gaps"""
        parts = []
        for ps in (paper_summaries or []):
            title = ps.get("paper_title", "未知")
            sections = ps.get("sections", {})
            for sec_key, sec_data in sections.items():
                gaps = sec_data.get("gaps", [])
                if gaps:
                    parts.append(f"### {title} — {sec_key}")
                    for g in gaps[:3]:
                        parts.append(f"- {g}")
        return "\n".join(parts) if parts else ""

    @staticmethod
    def _collect_mechanisms_from_summaries(paper_summaries: list) -> str:
        parts = []
        for ps in (paper_summaries or []):
            title = ps.get("paper_title", "未知")
            sections = ps.get("sections", {})
            mech = sections.get("08_mechanism", {})
            channels = mech.get("mechanism_channels", [])
            if channels:
                parts.append(f"### {title}")
                for ch in channels:
                    if isinstance(ch, dict):
                        parts.append(f"- {ch.get('name', '')}: 中介变量={ch.get('mediator_variable', '')} | 证据强度={ch.get('evidence_strength', '')}")
                    else:
                        parts.append(f"- {ch}")
        return "\n".join(parts) if parts else ""

    @staticmethod
    def _collect_theories_from_summaries(paper_summaries: list) -> str:
        parts = []
        for ps in (paper_summaries or []):
            title = ps.get("paper_title", "未知")
            sections = ps.get("sections", {})
            theory = sections.get("02_theoretical_framework", {})
            theories = theory.get("theories_used", [])
            hypotheses = theory.get("hypotheses_derived", [])
            if theories or hypotheses:
                parts.append(f"### {title}")
                if theories:
                    parts.append(f"  使用理论: {', '.join(theories)}")
                for h in (hypotheses or []):
                    if isinstance(h, dict):
                        parts.append(f"  - {h.get('id', '')}: {h.get('content', '')}")
                    else:
                        parts.append(f"  - {h}")
        return "\n".join(parts) if parts else ""

    @staticmethod
    def _collect_model_stats_from_summaries(paper_summaries: list) -> str:
        parts = []
        for ps in (paper_summaries or []):
            title = ps.get("paper_title", "未知")
            sections = ps.get("sections", {})
            meth = sections.get("05_empirical_methodology", {})
            model_form = meth.get("baseline_model_form", "")
            est_method = meth.get("estimation_method", "")
            fe = meth.get("fixed_effects", [])
            se_type = meth.get("standard_error_type", "")
            if model_form or est_method:
                parts.append(f"### {title}")
                parts.append(f"- 模型: {model_form} | 估计: {est_method} | FE: {', '.join(fe) if fe else '未注明'} | SE: {se_type}")
            emp = sections.get("empirical", {})
            if emp.get("model_type"):
                parts.append(f"  (实证) 模型类型: {emp['model_type']}")
            if emp.get("endogeneity_strategy"):
                parts.append(f"  (实证) 内生性策略: {emp['endogeneity_strategy']}")
        return "\n".join(parts) if parts else ""

    @staticmethod
    def _collect_id_stats_from_summaries(paper_summaries: list) -> str:
        parts = []
        for ps in (paper_summaries or []):
            title = ps.get("paper_title", "未知")
            sections = ps.get("sections", {})
            ident = sections.get("03_identification", {})
            strategy = ident.get("identification_strategy", "")
            threats = ident.get("endogeneity_threats", [])
            endo = sections.get("10_endogeneity", {})
            treatment = endo.get("treatment_method", "")
            if strategy or treatment:
                parts.append(f"### {title}")
                parts.append(f"- 识别策略: {strategy} | 内生性处理方法: {treatment}")
                if threats:
                    threat_strs = []
                    for t in threats:
                        if isinstance(t, dict):
                            threat_strs.append(f"{t.get('type', '')}(严重度:{t.get('severity', '')})")
                        else:
                            threat_strs.append(str(t))
                    parts.append(f"  内生性威胁: {', '.join(threat_strs)}")
        return "\n".join(parts) if parts else ""

    @staticmethod
    def _collect_hypotheses_from_summaries(paper_summaries: list) -> str:
        parts = []
        for ps in (paper_summaries or []):
            title = ps.get("paper_title", "未知")
            sections = ps.get("sections", {})
            emp = sections.get("empirical", {})
            hyps = emp.get("hypotheses", {})
            if hyps:
                parts.append(f"### {title}")
                for hk, hv in hyps.items():
                    parts.append(f"- {hk}: {hv}")
        return "\n".join(parts) if parts else ""

    @staticmethod
    def _collect_variable_stats_from_summaries(paper_summaries: list) -> str:
        parts = []
        for ps in (paper_summaries or []):
            title = ps.get("paper_title", "未知")
            sections = ps.get("sections", {})
            dv = sections.get("04_data_variables", {})
            key_vars = dv.get("key_variables", {})
            if key_vars:
                parts.append(f"### {title}")
                if isinstance(key_vars.get("Y"), dict):
                    parts.append(f"- Y: {key_vars['Y'].get('name', '')} ({key_vars['Y'].get('definition', '')})")
                else:
                    parts.append(f"- Y: {key_vars.get('Y', '')}")
                if isinstance(key_vars.get("X"), dict):
                    parts.append(f"- X: {key_vars['X'].get('name', '')} ({key_vars['X'].get('definition', '')})")
                else:
                    parts.append(f"- X: {key_vars.get('X', '')}")
                parts.append(f"- 控制变量: {key_vars.get('controls', [])}")
            emp = sections.get("empirical", {})
            if emp.get("y_var"):
                parts.append(f"  (实证) Y: {emp['y_var']}")
            if emp.get("x_var"):
                parts.append(f"  (实证) X: {emp['x_var']}")
            if emp.get("mechanism_vars"):
                parts.append(f"  (实证) 机制变量: {', '.join(emp['mechanism_vars'])}")
        return "\n".join(parts) if parts else ""

    # ═══════════════════════════════════════════════════════════
    # 跨集群桥梁格式化辅助
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _format_bridge_report_for_prompt(bridge_report: dict = None) -> str:
        """将跨集群桥梁报告格式化为选题 Prompt 可用的文本"""
        if not bridge_report:
            return ""

        report = bridge_report.get("report", bridge_report)
        if not report:
            return ""

        parts = []

        # 集群概览
        clusters = report.get("clusters_identified", [])
        if clusters:
            parts.append(f"## 文献池自动识别为 {len(clusters)} 个主题集群：\n")
            for c in clusters:
                if isinstance(c, dict):
                    parts.append(
                        f"- **集群 {c.get('cluster_id', '')}**: {c.get('cluster_label', '')[:60]} "
                        f"({c.get('paper_count', 0)} 篇论文)\n"
                        f"  X: {c.get('common_x_vars', [])} | Y: {c.get('common_y_vars', [])}\n"
                        f"  机制池: {c.get('mechanism_pool', [])[:5]}\n"
                        f"  理论: {c.get('common_theories', [])[:5]}"
                    )

        # 桥梁详情
        bridges = report.get("cluster_bridges", [])
        if bridges:
            parts.append(f"\n## 跨集群桥梁分析（{len(bridges)} 个桥梁）：\n")
            for b in bridges:
                if isinstance(b, dict):
                    parts.append(
                        f"### 桥梁: {b.get('cluster_a', '')[:40]} × {b.get('cluster_b', '')[:40]}\n\n"
                        f"**统合理论**: {b.get('bridge_theory_name', 'N/A')}\n"
                        f"**理论逻辑**: {b.get('theoretical_bridge_summary', '')[:500]}\n"
                        f"**理论推导**: {b.get('theoretical_derivation', '')[:500]}\n\n"
                    )
                    # 可移植机制
                    tms = b.get("transplantable_mechanisms", [])
                    if tms:
                        parts.append("**可移植的因果链**:\n")
                        for tm in tms[:5]:
                            if isinstance(tm, dict):
                                parts.append(
                                    f"- [{tm.get('source_cluster', '')[:20]} → {tm.get('target_cluster', '')[:20]}] "
                                    f"{tm.get('new_mechanism_path', '')}\n"
                                    f"  假说: {tm.get('new_hypothesis', '')}\n"
                                    f"  理论严谨性: {tm.get('theoretical_strength', '?')}\n"
                                )
                    # 变量角色变化
                    vrcs = b.get("variable_role_changes", [])
                    if vrcs:
                        parts.append("\n**变量角色转换**:\n")
                        for vrc in vrcs[:5]:
                            if isinstance(vrc, dict):
                                parts.append(f"- {vrc.get('variable_name', '')}: {vrc.get('roles', {})}\n")
                    # 矛盾与张力
                    conts = b.get("contradictions", [])
                    if conts:
                        parts.append("\n**矛盾与张力**:\n")
                        for ct in conts[:3]:
                            if isinstance(ct, dict):
                                parts.append(
                                    f"- {ct.get('contradiction_description', '')}\n"
                                    f"  缺失调节变量: {ct.get('missing_moderator', 'N/A')}\n"
                                )

        # 候选题目
        ranked = report.get("ranked_topics", [])
        if ranked:
            parts.append(f"\n## 跨集群桥梁候选题目（共 {len(ranked)} 个，按创新评分排序）：\n")
            for i, t in enumerate(ranked[:10]):
                if isinstance(t, dict):
                    parts.append(
                        f"{i+1}. **{t.get('title', '')}** "
                        f"[创新={t.get('innovation_score', 0):.0f} "
                        f"理论={t.get('theoretical_rigor', 0):.0f} "
                        f"可行={t.get('feasibility', 0):.0f} "
                        f"总分={t.get('overall_score', 0):.1f}]\n"
                        f"   研究问题: {t.get('research_question', '')}\n"
                        f"   创新类型: {t.get('innovation_type', '')}\n"
                        f"   桥梁理论: {t.get('bridge_theory', '')}\n"
                        f"   关键变量: {t.get('key_variables', [])}\n"
                        f"   理论基础: {t.get('theoretical_basis', '')[:200]}\n"
                    )

        return "\n".join(parts) if parts else ""

    @staticmethod
    def _format_bridge_data_for_hypothesis(bridge_report: dict = None, topic_info: str = "") -> str:
        """
        从桥梁报告中提取与所选题目相关的具体桥梁数据，
        供假设推导时精确引用。
        """
        if not bridge_report:
            return ""

        report = bridge_report.get("report", bridge_report)
        if not report:
            return ""

        # 尝试匹配 topic_info 中的题目与桥梁中的候选题目
        parts = []
        bridges = report.get("cluster_bridges", [])
        ranked = report.get("ranked_topics", [])

        # 找到与当前选题最相关的桥梁
        relevant_bridge = None
        for b in bridges:
            if isinstance(b, dict):
                for ct in b.get("candidate_topics", []):
                    if isinstance(ct, dict) and ct.get("title", "")[:30] in topic_info:
                        relevant_bridge = b
                        break
            if relevant_bridge:
                break

        # 如果找到了精确匹配的桥梁
        if relevant_bridge:
            parts.append(f"**本题目的桥梁理论**: {relevant_bridge.get('bridge_theory_name', '')}")
            parts.append(f"**理论推导链**: {relevant_bridge.get('theoretical_derivation', '')}")
            parts.append("\n**可移植的因果链**（假设应基于以下嫁接逻辑）:")
            for tm in relevant_bridge.get("transplantable_mechanisms", []):
                if isinstance(tm, dict):
                    parts.append(
                        f"- 来源: [{tm.get('source_cluster', '')}] → "
                        f"目标: [{tm.get('target_cluster', '')}]\n"
                        f"  新因果链: {tm.get('new_mechanism_path', '')}\n"
                        f"  可检验假说: {tm.get('new_hypothesis', '')}\n"
                        f"  支撑文献: {tm.get('theoretical_support_papers', [])}"
                    )
            return "\n".join(parts)

        # 回退：没有精确匹配，输出所有桥梁中排名最高的
        if ranked:
            top_topic = ranked[0] if isinstance(ranked[0], dict) else {}
            if top_topic:
                parts.append(f"**最相关桥梁理论**: {top_topic.get('bridge_theory', 'N/A')}")
                parts.append(f"**桥梁逻辑**: {top_topic.get('bridge_logic', top_topic.get('theoretical_basis', ''))[:500]}")

        return "\n".join(parts) if parts else ""

    def generate_blueprint(
        self,
        paper_summaries: list = None,
        cross_synthesis: dict = None,
        empirical_results: list = None,
        topic_info: str = "",
        hypothesis_info: str = "",
        model_info: str = "",
        variable_info: str = "",
        regression_results: str = "",
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        Step 5（新版）：生成论文写作蓝图。

        汇总全部分析数据，生成 PaperBlueprint JSON。
        替代旧的 paper_blueprint.md（自由文本），变为结构化约束文件。
        """
        from skills.section_writer import SectionWriter
        sw = SectionWriter()
        return sw.generate_blueprint(
            paper_summaries=paper_summaries,
            cross_synthesis=cross_synthesis,
            empirical_results=empirical_results,
            topic_info=topic_info,
            hypothesis_info=hypothesis_info,
            model_info=model_info,
            variable_info=variable_info,
            regression_results=regression_results,
            backend=backend,
            model=model,
        )

    def write_by_blueprint(
        self,
        blueprint: dict,
        paper_summaries: list = None,
        cross_synthesis: dict = None,
        section_analyses: dict = None,
        regression_results: str = "",
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        Step 6（新版）：基于蓝图逐节撰写 + 拼接全文。

        替代旧的一次性 write_full_paper()。
        """
        from skills.section_writer import SectionWriter
        sw = SectionWriter()

        # 6a-6e: 逐节撰写
        sections_result = sw.write_all_sections(
            blueprint=blueprint,
            paper_summaries=paper_summaries,
            cross_synthesis=cross_synthesis,
            section_analyses=section_analyses,
            regression_results=regression_results,
            backend=backend,
            model=model,
        )

        if not sections_result.get("success"):
            return {"success": False, "error": "逐节写作失败", "sections": sections_result}

        # 拼接全文
        assembly = sw.assemble_full_paper(
            sections=sections_result["sections"],
            blueprint=blueprint,
            title=blueprint.get("thesis_title", ""),
        )

        return {
            "success": True,
            "blueprint": blueprint,
            "sections": sections_result,
            "full_paper": assembly,
        }

    def audit_and_assemble(
        self,
        sections: dict,
        blueprint: dict,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        Step 7-8（新版）：一致性审查 + 修正 + 最终拼接。

        1. 运行 Level 1-3 审查
        2. 如有问题，生成修正方案
        3. 拼接为最终论文
        """
        from skills.consistency_auditor import ConsistencyAuditor
        from skills.section_writer import SectionWriter

        auditor = ConsistencyAuditor()

        # 将 sections 格式从 section_writer 格式转为 auditor 格式
        sections_for_audit = {}
        sections_result = sections.get("sections", {})
        for sec_id, sec_data in sections_result.items():
            sections_for_audit[sec_id] = {
                "markdown": sec_data.get("markdown", ""),
                "path": sec_data.get("path", ""),
            }

        # Step 7: 一致性审查
        audit_report = auditor.audit(
            sections=sections_for_audit,
            blueprint=blueprint,
            backend=backend,
            model=model,
        )

        # Step 8: 如有错误，生成修正方案
        fixes = None
        if audit_report["errors"] > 0 or audit_report["warnings"] > 0:
            fixes = auditor.suggest_fixes(
                audit_report=audit_report,
                sections=sections_for_audit,
                blueprint=blueprint,
                backend=backend,
                model=model,
            )

        # 最终拼接
        sw = SectionWriter()
        assembly = sw.assemble_full_paper(
            sections=sections_result,
            blueprint=blueprint,
            title=blueprint.get("thesis_title", ""),
        )

        return {
            "success": True,
            "audit_report": audit_report,
            "fixes": fixes,
            "full_paper": assembly,
        }
