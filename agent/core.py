import os
import json
from agent.state import StateManager
from skills.file_handler import FileHandler
from skills.llm_client import LlmClient
from skills.literature_analyzer import LiteratureAnalyzer
from skills.cross_paper_analyzer import CrossPaperAnalyzer
from skills.presentation_generator import PresentationGenerator
from skills.empirical_analyzer import EmpiricalAnalyzer
from skills.paper_writer import PaperWriter


class ResearchAgent:
    """
    全流程科研学术论文写作 Agent 主控核心。
    编排原子化的 Skills 并加载 references 中的 Prompt 知识库，完成状态流转。

    流程：
      阶段一：文献导入 (collect_literature)
      阶段二：文献综述分析 (review_literature)
              ├── Step A: 每篇论文独立 11 维度分析
              ├── Step B: 跨论文对比分析（逐维度+实证方面 → 共性提取 → 写作推荐）
              └── Step C: 生成组会演示材料（HTML + 演讲稿）
      阶段三：实证方法论分析 (empirical_analysis)
              ├── Step A: 单篇论文四维实证分析
              └── Step B: (可选) 多篇横向比较 + 创新空间推断
    """

    def __init__(self):
        self.state_manager = StateManager()
        self.context = self.state_manager.load_state()
        self.file_handler = FileHandler()
        self.llm = LlmClient()
        self.analyzer = LiteratureAnalyzer()
        self.cross_analyzer = CrossPaperAnalyzer()
        self.presenter = PresentationGenerator()
        self.empirical = EmpiricalAnalyzer()
        self.writer = PaperWriter()

    # ═══════════════════════════════════════════════════════════
    # 阶段一：文献导入
    # ═══════════════════════════════════════════════════════════

    def collect_literature(self, papers_dir: str = "workspace/papers") -> bool:
        """阶段一：文献导入。从本地目录读取用户放置的论文元数据文件。"""
        print(f"\n[ResearchAgent] 启动文献导入任务.")
        print(f"[ResearchAgent] 扫描目录: {papers_dir}")

        try:
            result = self.file_handler.execute(action="import_papers", papers_dir=papers_dir)

            if not result.get("exists") or result.get("count", 0) == 0:
                print("[ResearchAgent] 未找到有效论文数据，导入中断。")
                self._print_import_help()
                self.context["collect_completed"] = False
                self.state_manager.save_state(self.context)
                return False

            papers = result["papers"]
            self.context["papers_count"] = result["count"]
            self.context["metadata_json_path"] = os.path.abspath(
                os.path.join(papers_dir, "metadata.json")
            )
            self.context["collect_completed"] = True

            self.state_manager.save_state(self.context)
            print(f"[ResearchAgent] 文献导入成功，共 {result['count']} 篇论文。")
            return True

        except Exception as e:
            print(f"[ResearchAgent] 文献导入异常中断: {e}")
            self.context["collect_completed"] = False
            self.state_manager.save_state(self.context)
            return False

    @staticmethod
    def _print_import_help():
        print("[ResearchAgent] ┌─────────────────────────────────────────┐")
        print("[ResearchAgent] │ 请在 workspace/papers/ 下放置以下任一文件:     │")
        print("[ResearchAgent] │   metadata.json — 标准论文元数据数组          │")
        print("[ResearchAgent] │   *.csv         — 含标题/作者等列的表格     │")
        print("[ResearchAgent] └─────────────────────────────────────────┘")

    # ═══════════════════════════════════════════════════════════
    # 阶段二：文献综述分析（per-paper 独立分析流程）
    # ═══════════════════════════════════════════════════════════

    def review_literature(
        self,
        backend: str = None,
        model: str = None,
        sections: str = None,
        skip_presentation: bool = False,
    ) -> bool:
        """
        阶段二：文献综述分析 — 每篇论文独立 11 维度分析 + 跨论文合成。

        Step A: 逐论文逐结构分析 — 每篇论文在自己目录下产出 11 维度分析
        Step B: 跨论文合成 — 对比矩阵 + 完整文献综述
        Step C: 演示材料 — 生成 HTML 演示幻灯片 + Markdown 演讲稿

        :param backend: LLM 后端 ("anthropic" 或 "openai")
        :param model: 模型名
        :param sections: 逗号分隔的结构编号，如 "1,6,11"，默认全部
        :param skip_presentation: 是否跳过演示材料生成
        """
        print("\n[ResearchAgent] ╔══════════════════════════════════════════╗")
        print("[ResearchAgent] ║  阶段二：计量经济学文献综述分析           ║")
        print("[ResearchAgent] ║  Step A: 每篇论文独立 11 维度分析        ║")
        print("[ResearchAgent] ║  Step B: 跨论文对比矩阵 + 完整文献综述   ║")
        print("[ResearchAgent] ║  Step C: 生成组会演示材料                 ║")
        print("[ResearchAgent] ╚══════════════════════════════════════════╝")

        # 载入文献
        load_result = self.file_handler.execute(action="load_papers")
        if not load_result.get("exists") or not load_result.get("papers"):
            print("[ResearchAgent] 失败：工作空间中无已收集的文献。请先执行 collect 导入文献。")
            return False

        papers = load_result["papers"]
        print(f"[ResearchAgent] 载入 {len(papers)} 篇论文。")

        # 解析 section 过滤列表
        section_filter = None
        if sections:
            section_filter = [s.strip().zfill(2) for s in sections.split(",") if s.strip().isdigit()]

        # ─── Step A: 逐论文逐结构分析 ───────────────────────────
        print(f"\n{'─'*60}")
        print(f"[ResearchAgent] Step A: 每篇论文独立分析 ({len(papers)} 篇 × 11 维度)")
        print(f"{'─'*60}")

        # 断点恢复：analysis_state = {"<paper_title>": ["01","02",...], ...}
        analysis_state = self.context.get("analysis_state", {})

        for paper_idx, paper in enumerate(papers):
            title = paper.get("title", f"论文{paper_idx+1}")
            title_key = title[:60]  # 用前60字符作为 key

            # 检查该论文的完成状态
            completed_sections = analysis_state.get(title_key, [])
            effective_filter = None
            if section_filter and completed_sections:
                effective_filter = [s for s in section_filter if s not in completed_sections]
                if not effective_filter:
                    print(f"[ResearchAgent] 论文 [{paper_idx+1}/{len(papers)}] 「{title[:40]}」已完成全部维度，跳过。")
                    continue
            elif section_filter:
                effective_filter = section_filter

            print(f"\n{'─'*60}")
            print(f"[ResearchAgent] 论文进度: [{paper_idx+1}/{len(papers)}]")
            print(f"{'─'*60}")

            def section_progress(section_num, section_title, result):
                """每完成一个维度，更新断点状态"""
                if result.get("success"):
                    current = analysis_state.get(title_key, [])
                    if section_num not in current:
                        current.append(section_num)
                    analysis_state[title_key] = current
                    self.context["analysis_state"] = analysis_state
                    self.state_manager.save_state(self.context)
                status = "✓" if result.get("success") else "✗"
                skipped = " (跳过)" if result.get("skipped") else ""
                print(f"  [{section_num}/11] {section_title} {status}{skipped}")

            try:
                result = self.analyzer.execute(
                    action="analyze_single_paper",
                    paper=paper,
                    section_filter=effective_filter,
                    backend=backend,
                    model=model,
                    on_progress=section_progress,
                    skip_existing=True,
                )
                if not result.get("success"):
                    print(f"  ⚠ 论文分析部分失败：成功 {result.get('success_count', 0)}/{result.get('total', 11)} 维度")
            except Exception as e:
                print(f"  ✗ 论文分析异常: {e}")
                import traceback
                traceback.print_exc()

        # ─── Step B: 跨论文对比分析 ───────────────────────────
        print(f"\n{'─'*60}")
        print(f"[ResearchAgent] Step B: 跨论文对比分析（逐维度 + 实证方面 → 共性提取）")
        print(f"{'─'*60}")

        # 使用 CrossPaperAnalyzer 进行全面的跨论文对比
        try:
            cross_result = self.cross_analyzer.execute(
                action="compare_all",
                backend=backend,
                model=model,
            )
        except Exception as e:
            print(f"[ResearchAgent] Step B 跨论文对比异常: {e}")
            cross_result = {"success": False, "reason": str(e)}

        if cross_result.get("success"):
            print(f"[ResearchAgent] 跨论文对比完成:")
            print(f"  综合记忆: {cross_result.get('cross_summary_path', 'N/A')}")
            print(f"  写作推荐: {cross_result.get('synthesis_path', 'N/A')}")
            self.context["cross_paper_summary_path"] = cross_result.get("cross_summary_path")
            self.context["writing_synthesis_path"] = cross_result.get("synthesis_path")
        else:
            print(f"[ResearchAgent] 跨论文对比未完成: {cross_result.get('reason', '未知')}")

        # 生成完整文献综述（基于单篇分析 + 跨论文对比）
        try:
            synthesis_result = self.analyzer.execute(
                action="synthesize",
                papers=papers,
                backend=backend,
                model=model,
            )
        except Exception as e:
            print(f"[ResearchAgent] 文献综述合成异常: {e}")
            synthesis_result = {"success": False, "markdown": str(e), "path": None}

        review_text = synthesis_result.get("markdown", "")
        self._save_legacy_report(papers, review_text, backend)

        self.context["review_md_path"] = synthesis_result.get("path")
        self.context["review_completed"] = True
        self.context["review_llm_completed"] = True

        # ─── Step C: 演示材料生成 ──────────────────────────────
        if not skip_presentation:
            print(f"\n{'─'*60}")
            print(f"[ResearchAgent] Step C: 生成组会演示材料")
            print(f"{'─'*60}")

            try:
                pres_result = self.presenter.execute(
                    action="generate_all",
                    review_text=review_text,
                    section_results=[],  # 不再需要，用 review_text 替代
                    papers=papers,
                    backend=backend,
                    model=model,
                )

                if pres_result.get("html", {}).get("success"):
                    self.context["presentation_html_path"] = pres_result["html"]["html_path"]
                    print(f"[ResearchAgent] HTML 演示: {pres_result['html']['html_path']}")

                if pres_result.get("speech", {}).get("success"):
                    self.context["speech_script_path"] = pres_result["speech"]["speech_path"]
                    print(f"[ResearchAgent] 演讲稿:   {pres_result['speech']['speech_path']}")

            except Exception as e:
                print(f"[ResearchAgent] Step C 异常 (不影响综述结果): {e}")
        else:
            print("[ResearchAgent] Step C 已跳过 (--skip-presentation)")
            self.context["presentation_html_path"] = None
            self.context["speech_script_path"] = None

        # 保存最终状态
        self.context.pop("analysis_completed_sections", None)
        self.state_manager.save_state(self.context)

        print(f"\n[ResearchAgent] ╔══════════════════════════════════════════╗")
        print(f"[ResearchAgent] ║  阶段二完成！产出物:                      ║")
        print(f"[ResearchAgent] ║  · 单篇分析: workspace/analysis/<论文>/     ║")
        print(f"[ResearchAgent] ║  · 跨论文对比: workspace/analysis/_cross_paper/")
        print(f"[ResearchAgent] ║  · 共性记忆: _cross_paper_summary.json    ║")
        print(f"[ResearchAgent] ║  · 写作推荐: _writing_synthesis.json      ║")
        print(f"[ResearchAgent] ║  · 完整综述:   {synthesis_result.get('path', 'N/A')}")
        if not skip_presentation:
            print(f"[ResearchAgent] ║  · HTML 演示:  {self.context.get('presentation_html_path', 'N/A')}")
            print(f"[ResearchAgent] ║  · 演讲稿:     {self.context.get('speech_script_path', 'N/A')}")
        print(f"[ResearchAgent] ╚══════════════════════════════════════════╝")
        return True

    # ═══════════════════════════════════════════════════════════
    # 阶段三：实证方法分析
    # ═══════════════════════════════════════════════════════════

    def empirical_analysis(
        self,
        backend: str = None,
        model: str = None,
        compare: bool = False,
    ) -> bool:
        """
        阶段三：实证方法论深度分析。
        对每篇论文进行四维结构化实证分析（假设、方法、变量、结果），
        输出到论文专属目录，更新 _paper_summary.json。
        多篇时支持横向比较矩阵和创新空间推断。

        :param backend: LLM 后端
        :param model: 模型名
        :param compare: 是否进行多篇横向比较（需至少2篇）
        """
        print("\n[ResearchAgent] ╔══════════════════════════════════════════╗")
        print("[ResearchAgent] ║  阶段三：实证方法论深度分析               ║")
        print("[ResearchAgent] ║  四维度：假设→方法→变量→结果           ║")
        print("[ResearchAgent] ╚══════════════════════════════════════════╝")

        load_result = self.file_handler.execute(action="load_papers")
        if not load_result.get("exists") or not load_result.get("papers"):
            print("[ResearchAgent] 失败：工作空间中无已导入的论文。")
            return False

        papers = load_result["papers"]
        print(f"[ResearchAgent] 载入 {len(papers)} 篇论文。")

        # 断点恢复
        emp_state = self.context.get("empirical_state", {})

        # Step A: 单篇分析
        single_results = []
        for i, p in enumerate(papers):
            title = p.get("title", "未命名")
            title_key = title[:60]

            # 检查是否已完成
            if emp_state.get(title_key):
                print(f"\n[ResearchAgent] 论文 [{i+1}/{len(papers)}] 「{title[:40]}」实证分析已完成，跳过。")
                continue

            print(f"\n[ResearchAgent] 实证分析论文 {i+1}/{len(papers)}: {title[:60]}")
            paper_text = self._load_paper_fulltext(title)

            result = self.empirical.execute(
                action="analyze_single",
                paper=p,
                paper_text=paper_text,
                backend=backend,
                model=model,
            )
            single_results.append(result)

            if result.get("success"):
                emp_state[title_key] = True
                self.context["empirical_state"] = emp_state
                self.state_manager.save_state(self.context)
                print(f"  → {result.get('paper_dir', '')}/empirical.md")
            else:
                print(f"  ✗ 分析失败")

        success_count = sum(1 for r in single_results if r.get("success"))
        print(f"\n[ResearchAgent] Step A 完成: {success_count}/{len(papers)} 篇分析成功")

        # Step B: 横向比较（可选，需≥2篇）
        if compare and success_count >= 2:
            print(f"\n[ResearchAgent] Step B: 横向比较 + 创新推断...")
            cmp_result = self.empirical.execute(
                action="compare_multi",
                single_results=single_results,
                backend=backend,
                model=model,
            )
            if cmp_result.get("success"):
                print(f"[ResearchAgent] 比较矩阵 → {cmp_result.get('cmp_path')}")
                print(f"[ResearchAgent] 创新推断 → {cmp_result.get('inv_path')}")
                self.context["empirical_compare_completed"] = True
        elif compare:
            print("[ResearchAgent] 横向比较需要至少2篇成功分析，跳过。")

        self.context["empirical_completed"] = True
        self.state_manager.save_state(self.context)

        print(f"\n[ResearchAgent] 阶段三完成。产出: workspace/analysis/<论文>/empirical.*")
        return success_count > 0

    def _load_paper_fulltext(self, title: str) -> str:
        """尝试从论文素材目录加载 PDF 全文"""
        materials_dir = os.path.abspath("论文素材")
        if not os.path.exists(materials_dir):
            return ""
        for fname in os.listdir(materials_dir):
            if fname.endswith(".pdf") and any(
                kw in fname for kw in title.split() if len(kw) >= 2
            ):
                try:
                    import PyPDF2
                    reader = PyPDF2.PdfReader(os.path.join(materials_dir, fname))
                    text = ""
                    for page in reader.pages[:6]:
                        t = page.extract_text()
                        if t:
                            text += t + "\n"
                    if len(text) > 200:
                        return text[:8000]
                except Exception:
                    pass
        return ""

    # ═══════════════════════════════════════════════════════════
    # 阶段四：论文写作
    # ═══════════════════════════════════════════════════════════

    def writing_select_topic(self, backend: str = None, model: str = None) -> dict:
        """
        Step 1（增强版）: 选题

        在选题之前自动运行 Step 0 跨集群桥梁检测。
        如果有 ≥2 个主题集群，桥梁发现结果将作为选题的主要输入。
        """
        projects = self._collect_all_projects()
        papers = []
        for p in projects:
            papers.extend(p.get("papers", []))
        review = self._load_review_text(include_archived=True)
        paper_summaries = self._load_paper_summaries(include_archived=True)
        empirical = self._load_empirical_results(include_archived=True)
        cross_synthesis = self._load_cross_paper_synthesis()

        print(f"[ResearchAgent] 选题基于: {len(projects)} 个来源, {len(papers)} 篇论文")
        print(f"[ResearchAgent]   综述: {'有' if review else '无'} | "
              f"记忆: {len(paper_summaries)} 篇 | 实证: {len(empirical)} 条 | "
              f"跨论文共性: {'有' if cross_synthesis else '无'}")

        # ── Step 0: 跨集群桥梁检测（如果论文数量足够）──
        bridge_report = None
        if len(paper_summaries) >= 2:
            print(f"\n[ResearchAgent] ── Step 0: 跨集群桥梁检测 ──")
            try:
                from skills.cross_cluster_bridge import CrossClusterBridgeDetector
                detector = CrossClusterBridgeDetector()
                bridge_result = detector.run(
                    paper_summaries=paper_summaries,
                    cross_synthesis=cross_synthesis,
                    backend=backend,
                    model=model,
                )
                if bridge_result.get("success") and bridge_result.get("bridge_count", 0) > 0:
                    bridge_report = bridge_result
                    print(f"[ResearchAgent] 桥梁检测完成: {bridge_result['bridge_count']} 个桥梁, "
                          f"{bridge_result['topic_count']} 个候选题目")
                else:
                    print(f"[ResearchAgent] 桥梁检测完成: 无可用的跨集群桥梁（回退到集群内选题）")
            except Exception as e:
                print(f"[ResearchAgent] 桥梁检测异常（不影响选题）: {e}")

        return self.writer.execute(
            "select_topic", review_text=review,
            paper_summaries=paper_summaries,
            cross_synthesis=cross_synthesis,
            empirical_results=empirical, papers=papers,
            bridge_report=bridge_report,
            backend=backend, model=model)

    def writing_formulate_hypothesis(self, topic_info: str, backend: str = None,
                                     model: str = None) -> dict:
        """Step 2（增强版）: 提出假设——注入桥梁数据"""
        paper_summaries = self._load_paper_summaries(include_archived=True)
        empirical = self._load_empirical_results(include_archived=True)
        cross_synthesis = self._load_cross_paper_synthesis()

        # 尝试加载已保存的桥梁报告
        bridge_report = None
        bridge_path = os.path.abspath("workspace/writing/cross_cluster_bridge_report.json")
        if os.path.exists(bridge_path):
            try:
                with open(bridge_path, "r", encoding="utf-8") as f:
                    bridge_report = {"report": json.load(f)}
            except Exception:
                pass

        return self.writer.execute(
            "formulate_hypothesis", topic_info=topic_info,
            paper_summaries=paper_summaries, empirical_results=empirical,
            cross_synthesis=cross_synthesis,
            bridge_report=bridge_report,
            backend=backend, model=model)

    def writing_select_model(self, topic_and_hypothesis: str, backend: str = None,
                             model: str = None) -> dict:
        """Step 3: 模型选择"""
        paper_summaries = self._load_paper_summaries(include_archived=True)
        cross_synthesis = self._load_cross_paper_synthesis()
        return self.writer.execute(
            "select_model", topic_and_hypothesis=topic_and_hypothesis,
            paper_summaries=paper_summaries,
            cross_synthesis=cross_synthesis,
            backend=backend, model=model)

    def writing_select_variables(self, topic_and_model: str, backend: str = None,
                                 model: str = None) -> dict:
        """Step 4: 变量选取"""
        paper_summaries = self._load_paper_summaries(include_archived=True)
        empirical = self._load_empirical_results(include_archived=True)
        cross_synthesis = self._load_cross_paper_synthesis()
        return self.writer.execute(
            "select_variables", topic_and_model=topic_and_model,
            paper_summaries=paper_summaries, empirical_results=empirical,
            cross_synthesis=cross_synthesis,
            backend=backend, model=model)

    def writing_conclusion(self, regression_results: str, topic_info: str,
                           backend: str = None, model: str = None) -> dict:
        """Step: 结论与政策建议 — 注入跨论文共性数据 + 论文全文"""
        cross_synthesis = self._load_cross_paper_synthesis()
        paper_summaries = self._load_paper_summaries(include_archived=True)
        empirical = self._load_empirical_results(include_archived=True)
        return self.writer.execute(
            "write_conclusion", regression_results=regression_results,
            topic_info=topic_info, cross_synthesis=cross_synthesis,
            paper_summaries=paper_summaries, empirical_results=empirical,
            backend=backend, model=model)

    def writing_full_paper(
        self,
        topic_and_hypothesis: str = "",
        model_and_variables: str = "",
        empirical_results: str = "",
        backend: str = None,
        model: str = None,
        all_materials: str = "",  # 向后兼容
    ) -> dict:
        """
        Step: 完整论文写作。
        优先使用分项输入（topic_and_hypothesis + model_and_variables + empirical_results），
        回退到 all_materials。
        """
        cross_synthesis = self._load_cross_paper_synthesis()
        paper_summaries = self._load_paper_summaries(include_archived=True)

        # 加载文献综述
        literature_review = ""
        lr_path = os.path.abspath("workspace/literature_review.md")
        if os.path.exists(lr_path):
            with open(lr_path, "r", encoding="utf-8") as f:
                literature_review = f.read()[:10000]

        return self.writer.execute(
            "write_full_paper",
            topic_and_hypothesis=topic_and_hypothesis or all_materials,
            model_and_variables=model_and_variables or "",
            cross_synthesis=cross_synthesis,
            empirical_results=empirical_results or "",
            literature_review=literature_review,
            paper_summaries=paper_summaries,
            all_materials=all_materials,  # 回退兼容
            backend=backend, model=model)

    # ═══════════════════════════════════════════════════════════
    # ★ 新版：蓝图驱动的分段写作流水线 (Step 5-8)
    # ═══════════════════════════════════════════════════════════

    def writing_generate_blueprint(
        self,
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

        汇总前四步的产出 + 全部论文分析 + 跨论文共性 → PaperBlueprint JSON。
        """
        paper_summaries = self._load_paper_summaries(include_archived=True)
        cross_synthesis = self._load_cross_paper_synthesis()
        empirical = self._load_empirical_results(include_archived=True)

        print(f"[ResearchAgent] 蓝图生成基于:")
        print(f"  论文摘要: {len(paper_summaries)} 篇")
        print(f"  跨论文共性: {'有' if cross_synthesis else '无'}")
        print(f"  实证结果: {len(empirical)} 条")
        print(f"  选题: {'有' if topic_info else '无'} | 假设: {'有' if hypothesis_info else '无'}")
        print(f"  模型: {'有' if model_info else '无'} | 变量: {'有' if variable_info else '无'}")

        return self.writer.generate_blueprint(
            paper_summaries=paper_summaries,
            cross_synthesis=cross_synthesis,
            empirical_results=empirical,
            topic_info=topic_info,
            hypothesis_info=hypothesis_info,
            model_info=model_info,
            variable_info=variable_info,
            regression_results=regression_results,
            backend=backend,
            model=model,
        )

    def writing_pipeline_v2(
        self,
        topic_info: str = "",
        hypothesis_info: str = "",
        model_info: str = "",
        variable_info: str = "",
        regression_results: str = "",
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        ★ 新版论文写作全流程：Step 5 → Step 6 → Step 7 → Step 8。

        替代原有的 writing_full_paper() 单次 LLM 调用。

        Step 5: 生成蓝图 (PaperBlueprint JSON)
        Step 6: 逐节撰写 (5 节 × 独立 LLM 调用)
        Step 7: 一致性审查 (结构化规则 + LLM 语义检查)
        Step 8: 修正 + 拼接为最终论文
        """
        print("\n[ResearchAgent] ╔══════════════════════════════════════════╗")
        print("[ResearchAgent] ║  ★ 新版论文写作流水线 (蓝图驱动)        ║")
        print("[ResearchAgent] ║  Step 5: 蓝图 → Step 6: 逐节撰写        ║")
        print("[ResearchAgent] ║  Step 7: 审查 → Step 8: 修正定稿        ║")
        print("[ResearchAgent] ╚══════════════════════════════════════════╝")

        paper_summaries = self._load_paper_summaries(include_archived=True)
        cross_synthesis = self._load_cross_paper_synthesis()
        empirical = self._load_empirical_results(include_archived=True)

        # 收集 11 维度分析数据
        section_analyses = self._collect_section_analyses_for_all_papers()

        # ── Step 5: 生成蓝图 ──
        print(f"\n{'─'*60}")
        print(f"[ResearchAgent] Step 5: 生成论文写作蓝图")
        print(f"{'─'*60}")

        blueprint_result = self.writing_generate_blueprint(
            topic_info=topic_info,
            hypothesis_info=hypothesis_info,
            model_info=model_info,
            variable_info=variable_info,
            regression_results=regression_results,
            backend=backend,
            model=model,
        )

        if not blueprint_result.get("success"):
            print("[ResearchAgent] 蓝图生成失败，中断流水线")
            return {"success": False, "error": "蓝图生成失败", "blueprint": blueprint_result}

        blueprint = blueprint_result["blueprint"]

        # 保存蓝图
        blueprint_path = os.path.abspath("workspace/writing/paper_blueprint.json")
        with open(blueprint_path, "w", encoding="utf-8") as f:
            json.dump(blueprint, f, ensure_ascii=False, indent=2)
        print(f"[ResearchAgent] 蓝图 → {blueprint_path}")

        # ── Step 6: 逐节撰写 ──
        print(f"\n{'─'*60}")
        print(f"[ResearchAgent] Step 6: 逐节撰写 (5 节)")
        print(f"{'─'*60}")

        writing_result = self.writer.write_by_blueprint(
            blueprint=blueprint,
            paper_summaries=paper_summaries,
            cross_synthesis=cross_synthesis,
            section_analyses=section_analyses,
            regression_results=regression_results,
            backend=backend,
            model=model,
        )

        if not writing_result.get("success"):
            print("[ResearchAgent] 逐节写作失败")
            return {"success": False, "error": "逐节写作失败", "writing": writing_result}

        # ── Step 7-8: 审查 + 修正 + 定稿 ──
        print(f"\n{'─'*60}")
        print(f"[ResearchAgent] Step 7-8: 一致性审查 + 修正定稿")
        print(f"{'─'*60}")

        final_result = self.writer.audit_and_assemble(
            sections=writing_result["sections"],
            blueprint=blueprint,
            backend=backend,
            model=model,
        )

        # ── 保存最终产出 ──
        if final_result.get("full_paper", {}).get("success"):
            full_paper = final_result["full_paper"]
            print(f"\n[ResearchAgent] ╔══════════════════════════════════════════╗")
            print(f"[ResearchAgent] ║  ★ 新版写作流水线完成！                ║")
            print(f"[ResearchAgent] ║  最终论文: {full_paper.get('path', 'N/A')}")
            audit = final_result.get("audit_report", {})
            print(f"[ResearchAgent] ║  审查结果: {audit.get('overall_verdict', 'N/A')}")
            print(f"[ResearchAgent] ║  Errors: {audit.get('errors', 0)} | Warnings: {audit.get('warnings', 0)}")
            print(f"[ResearchAgent] ╚══════════════════════════════════════════╝")

        self.context["writing_v2_completed"] = True
        self.context["writing_blueprint_path"] = blueprint_path
        self.state_manager.save_state(self.context)

        return {
            "success": True,
            "blueprint": blueprint,
            "writing": writing_result,
            "final": final_result,
        }

    # ═══════════════════════════════════════════════════════════
    # ★ 新版 v3: 回归驱动的写作流水线 (Step 4.5→5→4.6→决策→6)
    # ═══════════════════════════════════════════════════════════

    def writing_pipeline_v3(
        self,
        topic_info: str = "",
        hypothesis_info: str = "",
        model_info: str = "",
        variable_info: str = "",
        data_path: str = "",
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        ★ 新版论文写作全流程（回归驱动版）：

        Step 1-4: 选题→假设→模型→变量（同前）
        Step 4.5: 数据获取
        Step 5:   实证回归（执行回归，获取结果）
        Step 4.6: 回归诊断与决策（判定支撑/部分/不支撑/反向，推荐回退路径）
        Step 6:   结构化蓝图（仅在 PROCEED 时生成）
        Step 7-8: 逐节撰写 → 审查 → 定稿

        如果回归不支撑：
          - 回退到 Step 2（修正假设）、Step 3（调整模型）、Step 4.5（获取新数据）
          - 或重新考虑选题（RECONSIDER_TOPIC）
        """
        print("\n[ResearchAgent] ╔══════════════════════════════════════════╗")
        print("[ResearchAgent] ║  ★ 论文写作流水线 v3 (回归驱动)        ║")
        print("[ResearchAgent] ║  Step 4.5→5→4.6→决策→6→7→8          ║")
        print("[ResearchAgent] ╚══════════════════════════════════════════╝")

        paper_summaries = self._load_paper_summaries(include_archived=True)
        cross_synthesis = self._load_cross_paper_synthesis()
        empirical = self._load_empirical_results(include_archived=True)
        section_analyses = self._collect_section_analyses_for_all_papers()

        # ── 加载前几步的产出 ──
        hypothesis_data = self._load_step_output("hypotheses")
        model_data = self._load_step_output("model_recommendation")
        variable_data = self._load_step_output("variable_selection")

        # ── Step 4.5: 数据获取 ──
        print(f"\n{'─'*60}")
        print(f"[ResearchAgent] Step 4.5: 数据获取")
        print(f"{'─'*60}")
        if not data_path:
            data_path = os.path.abspath("workspace/data/panel_data.csv")
        if not os.path.exists(data_path):
            print(f"[ResearchAgent] ⚠ 数据文件不存在: {data_path}")
            print(f"[ResearchAgent] 请先获取数据，或将数据放入 workspace/data/")
            self.context["data_acquired"] = False
            self.state_manager.save_state(self.context)
            return {"success": False, "error": "data_not_found", "expected_path": data_path}
        print(f"[ResearchAgent] 数据就绪: {data_path}")
        self.context["data_path"] = data_path
        self.context["data_acquired"] = True

        # ── Step 5: 实证回归 ──
        print(f"\n{'─'*60}")
        print(f"[ResearchAgent] Step 5: 实证回归")
        print(f"{'─'*60}")

        regression_results = self._run_regression(data_path, hypothesis_data, model_data, variable_data)
        if not regression_results.get("success"):
            print(f"[ResearchAgent] ⚠ 回归执行失败: {regression_results.get('error', '')}")
            # 即使回归失败，也可以尝试用蓝图+文献证据继续（降级模式）
            regression_results["success"] = False

        # ── Step 4.6: 回归诊断与决策 ──
        print(f"\n{'─'*60}")
        print(f"[ResearchAgent] Step 4.6: 回归诊断与决策")
        print(f"{'─'*60}")

        from skills.regression_diagnosis import RegressionDiagnosisEngine
        engine = RegressionDiagnosisEngine()

        hypotheses = self._parse_hypotheses_from_output(hypothesis_data)
        diagnosis_result = engine.diagnose_and_decide(
            regression_results=regression_results,
            hypotheses=hypotheses,
            paper_summaries=paper_summaries,
            literature_evidence=variable_data.get("markdown", "")[:3000] if variable_data else "",
            backend=backend,
            model=model,
        )

        diagnosis = diagnosis_result.get("diagnosis", {})
        decision = diagnosis_result.get("decision", {})

        # 保存诊断
        diag_path = os.path.abspath("workspace/regression/diagnosis.json")
        with open(diag_path, "w", encoding="utf-8") as f:
            json.dump(diagnosis, f, ensure_ascii=False, indent=2)

        # ── 决策树 ──
        decision_type = decision.get("decision_type", "PROCEED")
        print(f"\n[ResearchAgent] ╔══════════════════════════════════════════╗")
        print(f"[ResearchAgent] ║  决策: {decision_type}                    ║")
        print(f"[ResearchAgent] ║  诊断: {diagnosis.get('overall_verdict', '?')}")
        print(f"[ResearchAgent] ╚══════════════════════════════════════════╝")

        if decision_type == "RECONSIDER_TOPIC":
            print(f"\n[ResearchAgent] ┌{'─'*50}")
            print(f"[ResearchAgent] │ ⚠ 回归结果完全不支撑假设体系")
            print(f"[ResearchAgent] │ 建议回退到 Step 0 重新选题，或考虑:")
            print(f"[ResearchAgent] │ '不存在因果'本身作为研究发现")
            print(f"[ResearchAgent] │ 诊断原因: {diagnosis.get('possible_causes', [])}")
            print(f"[ResearchAgent] └{'─'*50}")
            return {
                "success": False,
                "verdict": "reconsider_topic",
                "diagnosis": diagnosis,
                "decision": decision,
                "message": "回归结果不支撑。建议运行 /论文写作 重新选题，或手动修改假设体系。",
            }

        if decision_type in ("REVISE_HYPOTHESES", "REVISE_MODEL", "ACQUIRE_DATA"):
            fallback = decision.get("target_step", "2")
            instructions = decision.get("revision_instructions", {})
            print(f"\n[ResearchAgent] ┌{'─'*50}")
            print(f"[ResearchAgent] │ ⚠ 需要回退到 Step {fallback}")
            print(f"[ResearchAgent] │ 修正内容: {json.dumps(instructions, ensure_ascii=False)[:300]}")
            print(f"[ResearchAgent] │ 请根据诊断结果手动调整后重新运行 /论文写作")
            print(f"[ResearchAgent] └{'─'*50}")
            return {
                "success": False,
                "verdict": "revision_needed",
                "diagnosis": diagnosis,
                "decision": decision,
                "fallback_step": fallback,
                "revision_instructions": instructions,
            }

        # ── PROCEED: Step 6-8 ──
        regression_text = self._format_regression_for_blueprint(regression_results, diagnosis)

        # Step 6: 蓝图
        print(f"\n{'─'*60}")
        print(f"[ResearchAgent] Step 6: 生成论文写作蓝图 (基于回归结果)")
        print(f"{'─'*60}")

        blueprint_result = self.writer.generate_blueprint(
            paper_summaries=paper_summaries,
            cross_synthesis=cross_synthesis,
            empirical_results=empirical,
            topic_info=topic_info,
            hypothesis_info=hypothesis_info,
            model_info=model_info,
            variable_info=variable_info,
            regression_results=regression_text,
            backend=backend,
            model=model,
        )

        if not blueprint_result.get("success"):
            return {"success": False, "error": "蓝图生成失败", "diagnosis": diagnosis}

        blueprint = blueprint_result["blueprint"]
        # ★ 注入回归诊断结果到蓝图
        blueprint["regression_diagnosis"] = diagnosis

        blueprint_path = os.path.abspath("workspace/writing/paper_blueprint.json")
        with open(blueprint_path, "w", encoding="utf-8") as f:
            json.dump(blueprint, f, ensure_ascii=False, indent=2)

        # Step 7-8: 逐节撰写 + 审查
        writing_result = self.writer.write_by_blueprint(
            blueprint=blueprint,
            paper_summaries=paper_summaries,
            cross_synthesis=cross_synthesis,
            section_analyses=section_analyses,
            regression_results=regression_text,
            backend=backend,
            model=model,
        )

        final_result = self.writer.audit_and_assemble(
            sections=writing_result.get("sections", {}),
            blueprint=blueprint,
            backend=backend,
            model=model,
        )

        print(f"\n[ResearchAgent] ╔══════════════════════════════════════════╗")
        print(f"[ResearchAgent] ║  ★ v3 流水线完成                         ║")
        print(f"[ResearchAgent] ║  回归判定: {diagnosis.get('overall_verdict', '?')}")
        print(f"[ResearchAgent] ║  最终论文: {final_result.get('full_paper', {}).get('path', 'N/A')}")
        print(f"[ResearchAgent] ╚══════════════════════════════════════════╝")

        self.context["writing_v3_completed"] = True
        self.state_manager.save_state(self.context)

        return {
            "success": True,
            "diagnosis": diagnosis,
            "decision": decision,
            "blueprint": blueprint,
            "writing": writing_result,
            "final": final_result,
        }

    def _run_regression(self, data_path: str, hypothesis_data: dict, model_data: dict, variable_data: dict) -> dict:
        """
        执行实证回归。优先使用 Stata MCP，回退到 Python regression_lib。
        返回标准化的回归结果 dict。
        """
        # 尝试从 hypothesis/variable 数据中提取变量信息
        y_var = ""
        x_var = ""
        controls = []

        if variable_data:
            vd_text = variable_data.get("markdown", "")
            # 简单提取 Y 和 X
            y_match = re.search(r'[Yy]\s*(?:变量|variable)?[:：=]\s*(\w+)', vd_text)
            x_match = re.search(r'[Xx]\s*(?:变量|variable)?[:：=]\s*(\w+)', vd_text)
            if y_match:
                y_var = y_match.group(1)
            if x_match:
                x_var = x_match.group(1)

        if not y_var or not x_var:
            print(f"[ResearchAgent] 无法从变量选取中提取 Y/X，使用默认值")
            return {"success": False, "error": "无法确定 Y 和 X 变量。请在变量选取步骤中明确定义。"}

        print(f"[ResearchAgent] 回归: {y_var} ~ {x_var} (+ controls)")
        print(f"[ResearchAgent] 数据: {data_path}")

        # 尝试使用 Python regression_lib
        try:
            from scripts.regression_lib import run_model
            result = run_model("panel_fe", data_path=data_path, y_var=y_var, x_vars=[x_var])
            if result.get("success"):
                result["y_var"] = y_var
                result["x_var"] = x_var
                return result
        except Exception as e:
            print(f"[ResearchAgent] Python 回归执行失败: {e}")

        # 回退：如果存在 Stata MCP，使用 Stata
        # (实际实现中，这里会调用 Stata MCP)
        return {"success": False, "error": "回归未能执行。请手动运行回归后将结果粘贴到 workspace/regression/results.json"}

    @staticmethod
    def _parse_hypotheses_from_output(hypothesis_data: dict) -> list:
        """从假设步骤的产出中解析假设列表"""
        if not hypothesis_data:
            return []
        text = hypothesis_data.get("markdown", "")
        hypotheses = []
        # 简单的正则提取
        for m in re.finditer(r'\*\*?(H\d)\*\*?[:：]\s*(.+?)(?=\n|$)', text):
            hypotheses.append({"id": m.group(1), "claim": m.group(2).strip()})
        return hypotheses

    @staticmethod
    def _format_regression_for_blueprint(regression_results: dict, diagnosis: dict) -> str:
        """将回归结果和诊断格式化为蓝图 Prompt 可用的文本"""
        parts = []
        parts.append("## 实际回归结果\n")
        parts.append(json.dumps(regression_results, ensure_ascii=False, indent=2)[:5000])
        parts.append("\n\n## 回归诊断\n")
        parts.append(f"整体判定: {diagnosis.get('overall_verdict', '?')}")
        parts.append(f"\n支撑: {diagnosis.get('supported_count', 0)} | "
                     f"部分: {diagnosis.get('partial_count', 0)} | "
                     f"拒绝: {diagnosis.get('rejected_count', 0)}")
        parts.append("\n\n## 可写作的发现\n")
        for wf in diagnosis.get("writable_findings", []):
            if isinstance(wf, dict):
                parts.append(f"- [{wf.get('evidence_level', '?')}] {wf.get('finding', '')}")
        return "\n".join(parts)

    @staticmethod
    def _load_step_output(filename: str) -> dict:
        """加载前几步的产出文件"""
        path = os.path.join(os.path.abspath("workspace/writing"), f"{filename}.md")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return {"markdown": f.read(), "path": path}
        return None

    # ═══════════════════════════════════════════════════════════

    def _collect_section_analyses_for_all_papers(self) -> dict:
        """
        收集所有论文的 11 维度分析 JSON，按论文标题索引。
        返回 {paper_title: {"01": {...}, "02": {...}, ...}}
        """
        result = {}
        summaries = self._load_paper_summaries(include_archived=True)
        for s in summaries:
            title = s.get("paper_title", "")
            if not title:
                continue
            sections = s.get("sections", {})
            if sections:
                result[title] = sections
        return result

    # ─── 辅助加载（per-paper 目录结构）──────────────────────

    def _load_paper_summaries(self, include_archived: bool = False) -> list:
        """
        加载所有 _paper_summary.json 文件。
        如果 summary 中缺少 fulltext，从 metadata.json 回退加载。
        """
        summaries = []

        def _scan(dir_path):
            if not os.path.exists(dir_path):
                return
            for dname in os.listdir(dir_path):
                paper_dir = os.path.join(dir_path, dname)
                if not os.path.isdir(paper_dir) or dname.startswith("_"):
                    continue
                summary_path = os.path.join(paper_dir, "_paper_summary.json")
                if os.path.exists(summary_path):
                    try:
                        with open(summary_path, "r", encoding="utf-8") as f:
                            s = json.load(f)
                        # 回退：如果 _paper_summary.json 没有 fulltext，从 metadata 加载
                        if not s.get("fulltext"):
                            s["fulltext"] = self._load_fulltext_for_paper(s.get("paper_title", ""))
                        summaries.append(s)
                    except Exception:
                        pass

        # 扫描当前工作区
        _scan(os.path.abspath("workspace/analysis"))

        # 扫描已归档项目
        if include_archived:
            proj_root = os.path.abspath("workspace/projects")
            if os.path.exists(proj_root):
                for dname in os.listdir(proj_root):
                    proj_dir = os.path.join(proj_root, dname)
                    if os.path.isdir(proj_dir):
                        # 检查新结构：analysis/<论文>/_paper_summary.json
                        analysis_dir = os.path.join(proj_dir, "analysis")
                        _scan(analysis_dir)
                        # 也检查旧的扁平结构（向后兼容）
                        if os.path.exists(analysis_dir) and any(
                            f.endswith("_analysis.json") for f in os.listdir(analysis_dir)
                        ):
                            # 旧结构，跳过（不能直接使用）
                            pass

        return summaries

    def _collect_all_projects(self) -> list:
        """
        扫描 workspace/projects/ 下所有已归档论文 + 当前工作区。
        适配新的 per-paper 目录结构。
        """
        projects = []
        proj_root = os.path.abspath("workspace/projects")

        if os.path.exists(proj_root):
            for dname in sorted(os.listdir(proj_root)):
                proj_dir = os.path.join(proj_root, dname)
                if not os.path.isdir(proj_dir):
                    continue

                info_path = os.path.join(proj_dir, "project_info.json")
                papers_path = os.path.join(proj_dir, "papers", "metadata.json")
                analysis_dir = os.path.join(proj_dir, "analysis")

                papers = []
                if os.path.exists(papers_path):
                    try:
                        with open(papers_path, "r", encoding="utf-8") as f:
                            papers = json.load(f)
                    except Exception:
                        pass

                title = dname
                if os.path.exists(info_path):
                    try:
                        with open(info_path, "r", encoding="utf-8") as f:
                            info = json.load(f)
                        title = info.get("paper_title", dname)
                    except Exception:
                        pass
                elif papers:
                    title = papers[0].get("title", dname) if papers else dname

                projects.append({
                    "title": title,
                    "folder": dname,
                    "review_path": os.path.join(proj_dir, "literature_review.md"),
                    "analysis_dir": analysis_dir,
                    "empirical_dir": analysis_dir,  # 新结构：empirical 也在 analysis 下
                    "papers": papers,
                })

        # 当前工作区
        current_review = os.path.abspath("workspace/literature_review.md")
        current_analysis = os.path.abspath("workspace/analysis")
        current_papers = os.path.abspath("workspace/papers/metadata.json")

        if os.path.exists(current_papers):
            papers = []
            try:
                with open(current_papers, "r", encoding="utf-8") as f:
                    papers = json.load(f)
            except Exception:
                pass
            title = papers[0].get("title", "当前工作区") if papers else "当前工作区"
            projects.append({
                "title": title,
                "folder": "（当前）",
                "review_path": current_review if os.path.exists(current_review) else None,
                "analysis_dir": current_analysis,
                "empirical_dir": current_analysis,
                "papers": papers,
            })

        return projects

    def _load_review_text(self, include_archived: bool = False) -> str:
        """加载文献综述文本"""
        if not include_archived:
            path = os.path.abspath("workspace/literature_review.md")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            return ""

        parts = []
        for proj in self._collect_all_projects():
            rp = proj.get("review_path")
            if rp and os.path.exists(rp):
                with open(rp, "r", encoding="utf-8") as f:
                    parts.append(f"## 论文: {proj['title']}\n\n{f.read()}")
        return "\n\n---\n\n".join(parts)

    def _load_section_results(self, include_archived: bool = False) -> list:
        """加载11维分析结果（适配新 per-paper 目录结构）"""
        all_results = []

        def _scan(dir_path, source_label=""):
            if not os.path.exists(dir_path):
                return
            for dname in os.listdir(dir_path):
                paper_dir = os.path.join(dir_path, dname)
                if not os.path.isdir(paper_dir) or dname.startswith("_"):
                    continue
                for fname in sorted(os.listdir(paper_dir)):
                    if fname.endswith(".json") and not fname.startswith("_") and fname != "empirical.json":
                        fpath = os.path.join(paper_dir, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8") as f:
                                jd = json.load(f)
                        except Exception:
                            continue
                        jd["_source_paper"] = source_label or dname
                        all_results.append({
                            "section_key": jd.get("section_key", ""),
                            "title": jd.get("section_title", ""),
                            "json": jd,
                            "source_paper": source_label or dname,
                            "success": True,
                        })

        # 当前工作区
        _scan(os.path.abspath("workspace/analysis"))

        # 归档项目
        if include_archived:
            proj_root = os.path.abspath("workspace/projects")
            if os.path.exists(proj_root):
                for dname in sorted(os.listdir(proj_root)):
                    proj_dir = os.path.join(proj_root, dname)
                    if os.path.isdir(proj_dir):
                        analysis_dir = os.path.join(proj_dir, "analysis")
                        _scan(analysis_dir, dname)

        return all_results

    def _load_empirical_results(self, include_archived: bool = False) -> list:
        """加载实证分析结果（从 per-paper 目录读取 empirical.json）"""
        all_results = []

        def _scan(dir_path, source_label=""):
            if not os.path.exists(dir_path):
                return
            for dname in os.listdir(dir_path):
                paper_dir = os.path.join(dir_path, dname)
                if not os.path.isdir(paper_dir) or dname.startswith("_"):
                    continue
                emp_json = os.path.join(paper_dir, "empirical.json")
                emp_md = os.path.join(paper_dir, "empirical.md")
                if os.path.exists(emp_json):
                    try:
                        with open(emp_json, "r", encoding="utf-8") as f:
                            jd = json.load(f)
                        jd["_source_paper"] = source_label or dname
                        entry = {"success": True, "json": jd, "title": jd.get("title", dname)}
                        if os.path.exists(emp_md):
                            with open(emp_md, "r", encoding="utf-8") as f:
                                entry["markdown"] = f.read()
                        all_results.append(entry)
                    except Exception:
                        pass

        # 当前工作区
        _scan(os.path.abspath("workspace/analysis"))

        # 归档项目
        if include_archived:
            proj_root = os.path.abspath("workspace/projects")
            if os.path.exists(proj_root):
                for dname in sorted(os.listdir(proj_root)):
                    proj_dir = os.path.join(proj_root, dname)
                    if os.path.isdir(proj_dir):
                        _scan(os.path.join(proj_dir, "analysis"), dname)

        return all_results

    def _load_fulltext_for_paper(self, paper_title: str) -> str:
        """
        回退加载论文 fulltext。优先从 metadata.json 查找，其次从归档项目查找。
        """
        # 1. 当前工作区的 metadata.json
        meta_path = os.path.abspath("workspace/papers/metadata.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    papers = json.load(f)
                for p in papers:
                    if p.get("title", "") == paper_title:
                        ft = p.get("fulltext", "")
                        if ft:
                            return ft
            except Exception:
                pass

        # 2. 归档项目中的 metadata.json
        proj_root = os.path.abspath("workspace/projects")
        if os.path.exists(proj_root):
            for dname in os.listdir(proj_root):
                meta = os.path.join(proj_root, dname, "papers", "metadata.json")
                if not os.path.exists(meta):
                    continue
                try:
                    with open(meta, "r", encoding="utf-8") as f:
                        papers = json.load(f)
                    for p in papers:
                        if p.get("title", "") == paper_title:
                            ft = p.get("fulltext", "")
                            if ft:
                                return ft
                except Exception:
                    pass
        return ""

    def _load_cross_paper_synthesis(self) -> dict:
        """
        加载跨论文对比综合数据。
        优先读取 _writing_synthesis.json，回退到 _cross_paper_summary.json。
        """
        # 当前工作区
        for fname in ["_writing_synthesis.json", "_cross_paper_summary.json"]:
            path = os.path.join(
                os.path.abspath("workspace/analysis"), "_cross_paper", fname
            )
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
        return {}

    def get_projects_summary(self) -> str:
        """获取所有已分析论文的摘要"""
        projects = self._collect_all_projects()
        lines = [f"共发现 {len(projects)} 个论文分析来源：", ""]
        for i, p in enumerate(projects):
            ad = p.get("analysis_dir")
            analysis_count = 0
            if ad and os.path.exists(ad):
                # 统计 per-paper 目录下的分析文件
                for subd in os.listdir(ad):
                    sub_path = os.path.join(ad, subd)
                    if os.path.isdir(sub_path) and not subd.startswith("_"):
                        analysis_count += len([
                            f for f in os.listdir(sub_path)
                            if f.endswith(".json") and f.startswith(("0", "1"))
                        ])
            lines.append(f"  {i+1}. {p['title'][:50]} ({p['folder']})")
            lines.append(f"     维度分析: {analysis_count} 个 JSON | 论文: {len(p.get('papers', []))} 篇")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    # 辅助
    # ═══════════════════════════════════════════════════════════

    def _save_legacy_report(self, papers: list, review_text: str, backend: str = None):
        """保留兼容的 review_analysis_report.json"""
        all_keywords = set()
        for p in papers:
            for k in (p.get("keywords") or []):
                all_keywords.add(k)

        overview = [
            {
                "id": i + 1,
                "title": p.get("title"),
                "authors": p.get("authors"),
                "source": p.get("source"),
                "abstract_len": len(p.get("abstract", "")),
                "keywords": p.get("keywords", []),
            }
            for i, p in enumerate(papers)
        ]

        report = {
            "total_papers": len(papers),
            "keywords_pool": list(all_keywords),
            "overview_list": overview,
            "llm_review_md_path": os.path.abspath("workspace/literature_review.md"),
            "backend_used": backend or os.environ.get("LLM_BACKEND", "openai"),
        }

        report_path = os.path.abspath("workspace/review_analysis_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=4)

    # ═══════════════════════════════════════════════════════════
    # 全流程流水线
    # ═══════════════════════════════════════════════════════════

    def run_pipeline(
        self,
        papers_dir: str = "workspace/papers",
        backend: str = None,
        model: str = None,
        sections: str = None,
        skip_presentation: bool = False,
    ) -> bool:
        """全流程流水线：导入 → 逐论文分析 → 合成 → 演示"""
        print("\n================== 启动全流程顺序流水线 ==================")

        already_collected = self.context.get("collect_completed", False)
        if not already_collected:
            success = self.collect_literature(papers_dir=papers_dir)
            if not success:
                print("[ResearchAgent] 流水线第一阶段(文献导入)中断。")
                return False
        else:
            cached_count = self.context.get("papers_count", 0)
            print(f"[ResearchAgent] 检测到已有 {cached_count} 篇导入文献，从断点恢复。")

        success = self.review_literature(
            backend=backend, model=model,
            sections=sections, skip_presentation=skip_presentation,
        )
        if not success:
            print("[ResearchAgent] 流水线第二阶段(分析综述)中断。")
            return False

        print("\n================== 全流程学术流水线完成 ==================")
        return True
