import os
import json
import re
from skills.base import BaseSkill
from skills.llm_client import LlmClient
from skills.schemas import (
    SECTION_SCHEMAS, SECTION_FIELD_MAP,
    PaperSummary, dataclass_to_dict, dict_to_dataclass,
    compute_quality_score, validate_paper_summary,
)


class LiteratureAnalyzer(BaseSkill):
    """
    计量经济学文献逐结构分析技能。
    对每篇论文独立进行 11 个维度的深度分析，保存在论文专属文件夹下，
    构建结构化 JSON 记忆文件（_paper_summary.json），支持后续跨论文合成。

    actions:
      - analyze_single_paper : 对单篇论文跑全部 11 维度
      - analyze_all_papers   : 循环所有论文跑全部分析
      - synthesize           : 跨论文汇总合成为完整文献综述
    """

    SECTIONS = [
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

    def __init__(self):
        super().__init__(
            name="LiteratureAnalyzer",
            description="计量经济学文献逐结构分析——每篇论文独立 11 维度深度分析 + JSON 记忆"
        )
        self.llm = LlmClient()
        self._prompts_dir = os.path.abspath("references/prompts")
        self._sections_dir = os.path.join(self._prompts_dir, "sections_single")  # 使用单篇 Prompt
        self._analysis_root = os.path.abspath("workspace/analysis")

    # ─── 公共入口 ──────────────────────────────────────────────

    def execute(self, action: str, **kwargs):
        if action == "analyze_single_paper":
            return self._analyze_single_paper(**kwargs)
        elif action == "analyze_all_papers":
            return self._analyze_all_papers(**kwargs)
        elif action == "synthesize":
            return self._synthesize(**kwargs)
        else:
            raise NotImplementedError(f"未实现的动作: {action}")

    # ─── 单篇论文全 11 维度分析 ────────────────────────────────

    def _analyze_single_paper(
        self,
        paper: dict,
        section_filter: list = None,
        backend: str = None,
        model: str = None,
        on_progress=None,
        skip_existing: bool = True,
    ) -> dict:
        """
        对单篇论文进行全部 11 维度深度分析。
        :param paper: 论文元数据 dict
        :param section_filter: 可选，仅分析指定编号列表
        :param skip_existing: 是否跳过已存在的分析文件
        :return: {"title": str, "sections": list, "summary_path": str, "success": bool}
        """
        title = paper.get("title", "未命名论文")
        paper_dir = self._get_paper_dir(title)
        os.makedirs(paper_dir, exist_ok=True)

        sections_to_run = self.SECTIONS
        if section_filter:
            sections_to_run = [s for s in self.SECTIONS if s[0] in section_filter]

        print(f"\n[{self.name}] ┌{'─'*50}")
        print(f"[{self.name}] │ 论文: {title[:60]}")
        print(f"[{self.name}] │ 待分析维度: {len(sections_to_run)} 个")
        print(f"[{self.name}] └{'─'*50}")

        section_results = []
        paper_text = self._format_single_paper(paper)

        for i, (num, slug, sec_title) in enumerate(sections_to_run):
            md_path = os.path.join(paper_dir, f"{num}_{slug}.md")
            json_path = os.path.join(paper_dir, f"{num}_{slug}.json")

            # 跳过已存在的
            if skip_existing and os.path.exists(md_path) and os.path.exists(json_path):
                print(f"  [{num}/11] {sec_title} ✓ (已有，跳过)")
                with open(json_path, "r", encoding="utf-8") as f:
                    existing_json = json.load(f)
                section_results.append({
                    "section_key": num, "section_slug": slug, "title": sec_title,
                    "json": existing_json, "md_path": md_path, "json_path": json_path,
                    "success": True, "skipped": True,
                })
                if on_progress:
                    on_progress(num, sec_title, {"success": True, "skipped": True})
                continue

            print(f"\n  [{num}/11] 正在分析: {sec_title} ...")
            result = self._analyze_one_section(
                paper=paper, paper_text=paper_text,
                section_num=num, section_slug=slug, section_title=sec_title,
                output_dir=paper_dir, backend=backend, model=model,
            )
            section_results.append(result)

            if on_progress:
                on_progress(num, sec_title, result)

        # 构建综合记忆文件
        summary_path = self._build_paper_summary(paper, section_results, paper_dir)

        # 更新总索引
        self._update_analysis_index()

        success_count = sum(1 for r in section_results if r.get("success"))
        print(f"\n[{self.name}] 论文分析完成: {success_count}/{len(section_results)} 维度成功")
        print(f"[{self.name}] 产出目录: {paper_dir}")
        print(f"[{self.name}] 记忆文件: {summary_path}")

        return {
            "title": title,
            "paper_dir": paper_dir,
            "sections": section_results,
            "summary_path": summary_path,
            "success": success_count > 0,
            "success_count": success_count,
            "total": len(section_results),
        }

    # ─── 单个维度分析 ──────────────────────────────────────────

    def _analyze_one_section(
        self,
        paper: dict,
        paper_text: str,
        section_num: str,
        section_slug: str,
        section_title: str,
        output_dir: str,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        对单篇论文的单个维度进行深度分析。

        ★ 新版：使用 structured_output() 替代手写正则提取。
        先获取 LLM 自由文本分析（保存为 .md），再通过结构化输出获取严格 Schema 化的 JSON。
        """
        prompt_path = os.path.join(self._sections_dir, f"{section_num}_{section_slug}.txt")

        if not os.path.exists(prompt_path):
            # 回退：尝试旧的 sections 目录
            fallback_path = os.path.join(self._prompts_dir, "sections", f"{section_num}_{section_slug}.txt")
            if os.path.exists(fallback_path):
                prompt_path = fallback_path
            else:
                raise FileNotFoundError(f"Prompt 模板不存在: {prompt_path} (fallback: {fallback_path})")

        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        full_prompt = prompt_template.replace("{paper_text}", paper_text).replace("{papers_text}", paper_text)

        # ── 第一步：获取自由文本分析（保存为 .md）──
        try:
            raw_output = self.llm.execute(
                prompt=full_prompt,
                system_prompt=f"你是一位计量经济学领域资深学者，正在对一篇论文的「{section_title}」维度进行深度分析。请严格遵循用户指定的输出格式。",
                backend=backend,
                model=model,
                max_tokens=5000,
            )
        except Exception as e:
            print(f"  [{section_num}] {section_title} 分析失败: {e}")
            return {
                "section_key": section_num,
                "section_slug": section_slug,
                "title": section_title,
                "markdown": f"# {section_num}. {section_title}\n\n**分析失败**: {e}",
                "json": {"error": str(e), "section_key": section_num, "section_title": section_title,
                         "paper_title": paper.get("title", ""), "key_findings": [], "gaps": [],
                         "information_sufficiency": "不足"},
                "success": False,
            }

        # ── 第二步：用 structured_output 获取严格 Schema 化的 JSON ──
        structured = None
        try:
            # 获取该维度的 Schema
            schema_cls = SECTION_SCHEMAS.get(section_num)
            if schema_cls:
                from skills.llm_client import dataclass_to_json_schema
                from skills.quality_gate import QualityGate

                output_schema = dataclass_to_json_schema(schema_cls)
                gate = QualityGate()

                # 基于 Markdown 分析内容进行结构化提取
                extraction_prompt = (
                    f"以下是一篇论文在「{section_title}」维度的深度分析文本。\n"
                    f"请从中提取结构化信息，严格按照要求的 JSON Schema 输出。\n\n"
                    f"【论文标题】{paper.get('title', '')}\n\n"
                    f"【分析文本】\n{raw_output[:8000]}\n\n"
                    f"请基于以上分析文本，输出结构化 JSON。所有字段必须填写，无法确定时请标注。"
                )

                structured = self.llm.structured_output(
                    prompt=extraction_prompt,
                    output_schema=output_schema,
                    system_prompt=f"你是一位计量经济学领域资深学者。请从分析文本中精确提取「{section_title}」维度的结构化数据。使用精确的计量术语。",
                    backend=backend,
                    model=model,
                    max_tokens=3000,
                    max_retries=2,
                    quality_validator=gate.make_validator(section_num),
                )
        except Exception as e:
            print(f"  [{section_num}] structured_output 失败: {e}，回退到正则提取")

        # 回退：如果 structured_output 失败，使用传统正则提取
        if structured is None or structured.get("_json_parse_error"):
            structured = self._extract_json_from_output(raw_output, section_num, section_title, paper)
        else:
            # 确保基础字段
            structured.setdefault("section_key", section_num)
            structured.setdefault("section_title", section_title)
            structured.setdefault("paper_title", paper.get("title", ""))
            structured.setdefault("key_findings", [])
            structured.setdefault("gaps", [])
            structured.setdefault("information_sufficiency", "未知")
            # 计算质量分
            try:
                from skills.schemas import compute_quality_score
                structured["quality_score"] = compute_quality_score(structured)
            except Exception:
                structured["quality_score"] = 0.0

        # 保存 Markdown
        md_path = os.path.join(output_dir, f"{section_num}_{section_slug}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {section_num}. {section_title} — {paper.get('title', '')}\n\n")
            f.write(raw_output)

        # 保存 JSON（使用 dataclass_to_dict 确保一致性）
        json_path = os.path.join(output_dir, f"{section_num}_{section_slug}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(structured, f, ensure_ascii=False, indent=2)

        quality_score = structured.get("quality_score", 0.0)
        score_indicator = "✓" if quality_score >= 0.35 else "⚠"
        print(f"  [{section_num}] {section_title} {score_indicator} (quality={quality_score:.2f}) → {md_path}")
        return {
            "section_key": section_num,
            "section_slug": section_slug,
            "title": section_title,
            "markdown": raw_output,
            "json": structured,
            "md_path": md_path,
            "json_path": json_path,
            "success": True,
        }

    # ─── 全部论文批量分析 ─────────────────────────────────────

    def _analyze_all_papers(
        self,
        papers: list,
        section_filter: list = None,
        backend: str = None,
        model: str = None,
        on_paper_progress=None,
        on_section_progress=None,
    ) -> list:
        """
        对所有论文逐一进行 11 维度分析。
        :return: 每篇论文的分析结果列表
        """
        results = []
        total_papers = len(papers)

        print(f"\n[{'='*60}]")
        print(f"[{self.name}] 启动全部论文分析: {total_papers} 篇论文 × 11 维度")
        print(f"[{'='*60}]")

        for i, paper in enumerate(papers):
            print(f"\n{'─'*60}")
            print(f"[{self.name}] 论文进度: [{i+1}/{total_papers}]")
            print(f"{'─'*60}")

            result = self._analyze_single_paper(
                paper=paper,
                section_filter=section_filter,
                backend=backend,
                model=model,
                on_progress=on_section_progress,
            )
            results.append(result)

            if on_paper_progress:
                on_paper_progress(i + 1, total_papers, result)

        # 更新总索引
        self._update_analysis_index()

        total_success = sum(1 for r in results if r.get("success"))
        print(f"\n[{self.name}] 全部论文分析完成: {total_success}/{total_papers} 篇成功")
        return results

    # ─── 跨论文汇总合成 ────────────────────────────────────────

    def _synthesize(
        self,
        papers: list = None,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        汇总所有论文的单篇分析，生成完整文献综述 + 跨论文对比矩阵。
        自动从 workspace/analysis/<各论文目录>/ 中读取分析结果。
        """
        print(f"\n[{self.name}] 正在汇总各论文分析报告...")

        # 扫描所有论文分析目录
        paper_analyses = self._load_all_paper_analyses()
        if not paper_analyses:
            print(f"[{self.name}] 未找到任何论文分析目录，无法合成。")
            return {"markdown": "无可用分析数据", "path": None, "success": False}

        print(f"[{self.name}] 发现 {len(paper_analyses)} 篇论文的分析数据")

        # ── 合成 A：跨论文对比矩阵 ──
        cross_dir = os.path.join(self._analysis_root, "_cross_paper")
        os.makedirs(cross_dir, exist_ok=True)

        for num, slug, sec_title in self.SECTIONS:
            self._build_cross_paper_comparison(
                num, slug, sec_title, paper_analyses, cross_dir, backend, model
            )

        # ── 合成 B：完整文献综述 ──
        review_text = self._generate_literature_review(
            paper_analyses, papers, cross_dir, backend, model
        )

        review_path = os.path.abspath("workspace/literature_review.md")
        with open(review_path, "w", encoding="utf-8") as f:
            f.write(f"# 文献综述（{len(paper_analyses)} 篇论文逐结构分析后汇总生成）\n\n")
            f.write(review_text)

        print(f"[{self.name}] 完整文献综述 → {review_path}")
        return {"markdown": review_text, "path": review_path, "success": True}

    # ─── 跨论文对比矩阵生成 ───────────────────────────────────

    def _build_cross_paper_comparison(
        self,
        section_num: str,
        section_slug: str,
        section_title: str,
        paper_analyses: list,
        output_dir: str,
        backend: str = None,
        model: str = None,
    ):
        """对单个维度，汇总各论文分析生成对比矩阵"""
        # 收集所有论文在该维度的关键发现
        parts = []
        for pa in paper_analyses:
            sections = pa.get("sections", [])
            for s in sections:
                if s.get("section_key") == section_num and s.get("success"):
                    jd = s.get("json", {})
                    parts.append(f"## {pa['title']}\n"
                                f"- 关键发现: {jd.get('key_findings', [])}\n"
                                f"- 空缺: {jd.get('gaps', [])}\n")
                    break

        if len(parts) < 2:
            return  # 少于2篇无需对比

        all_text = "\n".join(parts)
        compare_prompt = f"""你是一位计量经济学领域资深学者。请基于以下 {len(parts)} 篇论文在「{section_title}」维度的分析摘要，生成横向对比矩阵。

{all_text}

【输出格式】
### {section_num}. {section_title} — 跨论文对比矩阵
| 论文标题 | 核心发现 | 方法论亮点 | 缺口/局限 |
（逐论文填写，至少包含 {len(parts)} 行）

### 共性模式
- 该维度下各论文的共同做法或发现

### 差异与分歧
- 该维度下各论文的显著差异或矛盾

### 研究空缺汇总
- 跨论文视角下的研究空缺
"""

        try:
            raw = self.llm.execute(
                prompt=compare_prompt,
                system_prompt=f"你是一位计量经济学领域资深学者，正在撰写「{section_title}」维度的跨论文对比分析。",
                backend=backend, model=model, max_tokens=3000,
            )
        except Exception:
            raw = f"对比分析生成失败。共 {len(parts)} 篇论文参与对比。\n\n{all_text}"

        cmp_path = os.path.join(output_dir, f"{section_num}_{section_slug}_comparison.md")
        with open(cmp_path, "w", encoding="utf-8") as f:
            f.write(f"# {section_num}. {section_title} — 跨论文对比矩阵\n\n")
            f.write(raw)

        # 更新对比索引
        idx_path = os.path.join(output_dir, "_comparison_index.json")
        idx = {}
        if os.path.exists(idx_path):
            with open(idx_path, "r", encoding="utf-8") as f:
                idx = json.load(f)
        idx[section_num] = {
            "title": section_title,
            "slug": section_slug,
            "paper_count": len(parts),
            "path": cmp_path,
        }
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)

    # ─── 完整文献综述生成 ─────────────────────────────────────

    def _generate_literature_review(
        self,
        paper_analyses: list,
        papers: list = None,
        cross_dir: str = None,
        backend: str = None,
        model: str = None,
    ) -> str:
        """基于所有单篇分析 + 跨论文对比，生成完整文献综述"""
        # 汇总每篇论文的 summary
        summaries = []
        for pa in paper_analyses:
            summary_path = pa.get("summary_path")
            if summary_path and os.path.exists(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f:
                    summaries.append(f.read()[:3000])

        summaries_text = "\n\n---\n\n".join(summaries)

        # 加载跨论文对比
        cross_text = ""
        if cross_dir and os.path.exists(cross_dir):
            for fname in sorted(os.listdir(cross_dir)):
                if fname.endswith("_comparison.md"):
                    with open(os.path.join(cross_dir, fname), "r", encoding="utf-8") as f:
                        cross_text += f.read()[:2000] + "\n\n---\n\n"

        # 加载 synthesis prompt
        synthesis_path = os.path.join(self._prompts_dir, "synthesis.txt")
        if os.path.exists(synthesis_path):
            with open(synthesis_path, "r", encoding="utf-8") as f:
                template = f.read()
            full_prompt = template.replace("{sections_text}", cross_text or summaries_text)\
                                  .replace("{papers_text}", summaries_text[:5000])
        else:
            full_prompt = f"""请基于以下 {len(paper_analyses)} 篇论文的分析摘要和跨论文对比，撰写一篇完整的文献综述。

【论文分析摘要】
{summaries_text[:6000]}

【跨论文对比矩阵】
{cross_text[:4000]}

请输出一篇完整的文献综述，包含：研究背景与意义、理论框架梳理、实证方法与识别策略评述、核心发现汇总、研究空缺与未来方向。
"""

        try:
            review_text = self.llm.execute(
                prompt=full_prompt,
                system_prompt=f"你是一位计量经济学资深教授，正在撰写基于 {len(paper_analyses)} 篇论文的完整文献综述。请综合所有分析数据，生成学术期刊级别的综述。",
                backend=backend,
                model=model,
                max_tokens=8000,
            )
        except Exception as e:
            review_text = f"文献综述生成失败: {e}\n\n请检查各论文分析目录中的产出。"

        return review_text

    # ─── 综合记忆文件构建 ──────────────────────────────────────

    def _build_paper_summary(self, paper: dict, section_results: list, paper_dir: str) -> str:
        """
        从 11 个维度的分析 JSON 中汇总生成 _paper_summary.json。

        ★ 新版：使用 PaperSummary Schema 构建，保存为完整结构化 JSON。
        后续所有步骤（写作、回归、综述）都将直接读取此文件。
        """
        # 构建 PaperSummary 实例
        summary = PaperSummary(
            paper_title=paper.get("title", ""),
            authors=paper.get("authors", ""),
            source=paper.get("source", ""),
            pub_date=paper.get("pub_date", ""),
            keywords=paper.get("keywords", []),
            abstract=paper.get("abstract", ""),
            doi=paper.get("doi", ""),
            fulltext=paper.get("fulltext", ""),
            fulltext_length=len(paper.get("fulltext", "")),
        )

        # 逐维度填充
        for r in section_results:
            if not r.get("success"):
                continue
            section_key = r.get("section_key", "")
            jd = r.get("json", {})

            # 使用 dict_to_dataclass 将 JSON dict 转换为 Schema 实例
            field_name = SECTION_FIELD_MAP.get(section_key)
            schema_cls = SECTION_SCHEMAS.get(section_key)

            if field_name and schema_cls:
                try:
                    section_instance = dict_to_dataclass(jd, schema_cls)
                    section_instance.quality_score = jd.get("quality_score", compute_quality_score(jd))
                    setattr(summary, field_name, section_instance)
                except Exception as e:
                    print(f"    ⚠ 维度 {section_key} Schema 转换失败: {e}，使用原始 dict")
                    # 回退：直接设置 dict
                    setattr(summary, field_name, jd)

        # 汇总总体评估
        all_gaps = []
        all_findings = []
        for r in section_results:
            if r.get("success"):
                jd = r.get("json", {})
                gaps = jd.get("gaps", [])
                findings = jd.get("key_findings", [])
                if isinstance(gaps, list):
                    all_gaps.extend(gaps[:5])
                if isinstance(findings, list):
                    all_findings.extend(findings[:5])

        summary.overall_assessment = {
            "strengths": all_findings[:10],
            "weaknesses": all_gaps[:10],
            "relevance_to_my_research": "",
        }

        # 验证并计算质量分
        validation = validate_paper_summary(summary)
        summary.overall_quality_score = validation["quality_score"]
        summary.sections_completed = validation["completed_sections"]
        summary.last_updated = __import__('datetime').datetime.now().isoformat()

        # 转换为 dict 并保存
        summary_dict = dataclass_to_dict(summary)

        summary_path = os.path.join(paper_dir, "_paper_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_dict, f, ensure_ascii=False, indent=2)

        # 同时保存旧格式兼容字段（sections dict）
        self._save_legacy_sections(summary_dict, paper_dir)

        print(f"    [Summary] quality={summary.overall_quality_score:.2f} | "
              f"completed={summary.sections_completed} | "
              f"issues={len(validation.get('issues', []))}")

        return summary_path

    def _save_legacy_sections(self, summary_dict: dict, paper_dir: str):
        """保存向后兼容的 sections 字段（非 Schema 化的 key-value 对）"""
        legacy_sections = {}
        section_keys_map = {
            "section_01_introduction": "01_introduction",
            "section_02_theoretical": "02_theoretical_framework",
            "section_03_identification": "03_identification",
            "section_04_data": "04_data_variables",
            "section_05_methodology": "05_empirical_methodology",
            "section_06_baseline": "06_baseline_results",
            "section_07_robustness": "07_robustness",
            "section_08_mechanism": "08_mechanism",
            "section_09_heterogeneity": "09_heterogeneity",
            "section_10_endogeneity": "10_endogeneity",
            "section_11_conclusion": "11_conclusion",
        }
        for field_key, legacy_key in section_keys_map.items():
            section_data = summary_dict.get(field_key)
            if section_data:
                legacy_sections[legacy_key] = section_data

        # 保存原始 dict（其他依赖 _paper_summary.json 的代码使用 sections dict）
        legacy_path = os.path.join(paper_dir, "_paper_summary_legacy.json")
        try:
            legacy = {**summary_dict, "sections": legacy_sections}
            with open(legacy_path, "w", encoding="utf-8") as f:
                json.dump(legacy, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 非关键

    # ─── 总索引维护 ────────────────────────────────────────────

    def _update_analysis_index(self):
        """扫描所有论文目录，重建 _analysis_index.json"""
        index = {"papers": {}, "total_papers": 0, "total_sections_completed": 0}

        if not os.path.exists(self._analysis_root):
            return

        total_sections = 0
        for dname in sorted(os.listdir(self._analysis_root)):
            paper_dir = os.path.join(self._analysis_root, dname)
            if not os.path.isdir(paper_dir) or dname.startswith("_"):
                continue

            summary_path = os.path.join(paper_dir, "_paper_summary.json")
            if not os.path.exists(summary_path):
                continue

            # 统计完成维度
            sections_done = []
            for num, slug, _ in self.SECTIONS:
                md_path = os.path.join(paper_dir, f"{num}_{slug}.md")
                json_path = os.path.join(paper_dir, f"{num}_{slug}.json")
                if os.path.exists(md_path) or os.path.exists(json_path):
                    sections_done.append(num)

            # 读取 summary 获取标题
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)
                title = summary.get("paper_title", dname)
            except Exception:
                title = dname

            index["papers"][dname] = {
                "title": title,
                "directory": paper_dir,
                "sections_completed": sections_done,
                "sections_count": len(sections_done),
                "has_empirical": os.path.exists(os.path.join(paper_dir, "empirical.json")),
                "summary_path": summary_path,
            }
            total_sections += len(sections_done)

        index["total_papers"] = len(index["papers"])
        index["total_sections_completed"] = total_sections

        index_path = os.path.join(self._analysis_root, "_analysis_index.json")
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    # ─── 加载所有论文分析 ─────────────────────────────────────

    def _load_all_paper_analyses(self) -> list:
        """从 workspace/analysis/ 加载所有论文的分析数据"""
        results = []
        if not os.path.exists(self._analysis_root):
            return results

        for dname in sorted(os.listdir(self._analysis_root)):
            paper_dir = os.path.join(self._analysis_root, dname)
            if not os.path.isdir(paper_dir) or dname.startswith("_"):
                continue

            summary_path = os.path.join(paper_dir, "_paper_summary.json")
            if not os.path.exists(summary_path):
                continue

            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)
            except Exception:
                continue

            # 加载各维度 JSON
            sections = []
            for num, slug, _ in self.SECTIONS:
                json_path = os.path.join(paper_dir, f"{num}_{slug}.json")
                if os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            sections.append({
                                "section_key": num,
                                "section_slug": slug,
                                "json": json.load(f),
                                "success": True,
                            })
                    except Exception:
                        pass

            results.append({
                "title": summary.get("paper_title", dname),
                "directory": paper_dir,
                "summary": summary,
                "sections": sections,
                "summary_path": summary_path,
            })

        return results

    # ─── JSON 提取（从 LLM 输出中解析） ─────────────────────────

    def _extract_json_from_output(self, markdown_text: str, section_key: str,
                                   section_title: str, paper: dict) -> dict:
        """
        从 LLM 输出的 Markdown 中提取 JSON 结构化信息。
        优先查找 ```json ... ``` 代码块，回退到传统正则提取。
        """
        structured = {
            "section_key": section_key,
            "section_title": section_title,
            "paper_title": paper.get("title", ""),
            "key_findings": [],
            "gaps": [],
            "information_sufficiency": "未知",
        }

        # 1. 尝试提取 ```json ... ``` 代码块
        json_match = re.search(r'```json\s*\n(.*?)\n```', markdown_text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1).strip())
                structured.update(parsed)
                return structured
            except json.JSONDecodeError:
                pass  # 回退到传统提取

        # 2. 回退：传统正则提取
        # 提取表格
        tables = []
        lines = markdown_text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("|") and "|" in line[1:]:
                if i + 1 < len(lines) and re.match(r'^\|[\s\-:]+\|', lines[i + 1].strip()):
                    table_lines = [line, lines[i + 1].strip()]
                    j = i + 2
                    while j < len(lines) and lines[j].strip().startswith("|"):
                        table_lines.append(lines[j].strip())
                        j += 1
                    tables.append("\n".join(table_lines))
                    i = j
                    continue
            i += 1
        structured["_tables"] = tables

        # 提取关键发现
        findings = re.findall(r'[-*]\s*(.*?)(?=\n[-*]|\n\n|\Z)', markdown_text, re.DOTALL)
        structured["key_findings"] = [f.strip() for f in findings[:15] if len(f.strip()) > 10]

        # 提取 gaps
        gap_patterns = [
            r'(?:研究空缺|Research Gap|理论空缺|Theoretical Gap|识别策略空缺|Identification Gap|'
            r'数据空缺|Data Gap|方法论空缺|Methodological Gap|实证发现空缺|Empirical Gap|'
            r'机制研究空缺|异质性研究空缺|内生性处理空缺|政策研究空缺).*?\n+(.*?)(?=\n###|\Z)',
        ]
        for pattern in gap_patterns:
            gap_match = re.search(pattern, markdown_text, re.DOTALL | re.IGNORECASE)
            if gap_match:
                gap_items = re.findall(r'[-*]\s*(.*?)(?=\n[-*]|\n\n|\Z)', gap_match.group(1), re.DOTALL)
                structured["gaps"] = [g.strip() for g in gap_items if len(g.strip()) > 10]
                break

        # 信息充分性
        if "不足" in markdown_text or "未提供" in markdown_text or "无法判断" in markdown_text:
            structured["information_sufficiency"] = "不足"

        return structured

    # ─── 辅助方法 ──────────────────────────────────────────────

    def _get_paper_dir(self, title: str) -> str:
        """获取论文专属分析目录"""
        safe_name = re.sub(r'[<>:"/\\|?*]', '', title.strip())
        if len(safe_name) > 50:
            safe_name = safe_name[:50]
        return os.path.join(self._analysis_root, safe_name or "未命名论文")

    @staticmethod
    def _format_single_paper(paper: dict) -> str:
        """
        将单篇论文的全部可用元数据格式化为 Prompt 文本。

        优先传入所有可用字段（摘要、Extra 字段、关键词等），
        让 LLM 自行判断哪些部分包含方法论信息，
        而不是人为截断或限定数据源范围。
        """
        title = paper.get("title", "未知标题")
        authors = paper.get("authors", "未知作者")
        source = paper.get("source", "未知来源")
        pub_date = paper.get("pub_date", "未知日期")
        abstract = paper.get("abstract", "")
        keywords = ", ".join(paper.get("keywords", [])) if isinstance(paper.get("keywords"), list) else str(paper.get("keywords", ""))
        extra = paper.get("extra", "")
        doi = paper.get("doi", "")
        has_pdf = bool(paper.get("attachments"))

        # 数据源声明（放在最前面，防止 LLM 锚定"摘要"）
        has_fulltext = bool(paper.get("fulltext", ""))
        if has_fulltext:
            data_notice = (
                "## ⚠️ 数据源声明（分析前必读）\n"
                "你收到的材料包含以下全部内容：\n"
                f"1. **PDF全文**（约{len(paper['fulltext'])}字符，包含完整引言、理论框架、研究设计、"
                "实证结果、稳健性检验和结论）——这是你的主要数据源。\n"
                "2. 论文摘要（简短概括）。\n"
                "3. 元数据（作者、期刊、关键词等）。\n\n"
                "**重要规则**：\n"
                "- 分析时必须基于 PDF 全文中的具体信息，引用论文中的实际方法、数据和结论。\n"
                "- **禁止使用\"基于摘要\"\"摘要中\"\"从摘要来看\"等措辞**——你拥有远超摘要的完整信息。\n"
                "- 如某项信息在 PDF 全文中确实找不到，应标注\"论文未明确说明\"而非\"摘要未提供\"。\n"
                "- PDF 全文可能因提取原因有少量 OCR 噪声，请忽略乱码或格式碎片。\n\n"
                "---\n\n"
            )
        else:
            data_notice = (
                "## ⚠️ 数据源声明\n"
                "当前仅有论文摘要和元数据，无 PDF 全文。"
                "请基于现有信息分析，缺失处标注\"需查阅全文确认\"。\n\n"
                "---\n\n"
            )

        parts = [
            data_notice,
            f"## 论文标题\n{title}\n",
            f"## 作者\n{authors}\n",
            f"## 来源/期刊\n{source}\n",
            f"## 发表时间\n{pub_date}\n",
            f"## DOI\n{doi}\n",
            f"## 关键词\n{keywords}\n",
        ]

        if abstract:
            parts.append(f"## 摘要（全文未截断）\n{abstract}\n")

        # PDF 全文（最高优先级数据源）
        fulltext = paper.get("fulltext", "")
        if fulltext:
            parts.append(f"## PDF 全文（已提取，共 {len(fulltext)} 字符）\n{fulltext}\n")

        if extra:
            # Extra 字段可能包含引用键、注释、补充说明等
            parts.append(f"## Zotero Extra 字段（补充信息）\n{extra}\n")

        if has_pdf and not has_fulltext:
            parts.append(
                "## 注\n该论文在 Zotero 库中有 PDF 全文附件，但本次未能成功提取全文。"
                "请基于现有材料进行分析，缺失处标注\"需查阅全文确认\"。\n"
            )
        else:
            parts.append(
                "## 注\n当前仅有摘要和元数据。分析时请基于现有信息尽可能详细地报告，"
                "同时标注哪些信息需要查阅全文才能确认。\n"
            )

        return "\n".join(parts)
