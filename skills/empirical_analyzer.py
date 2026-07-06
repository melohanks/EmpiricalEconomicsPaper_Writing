import os
import json
import re
from skills.base import BaseSkill
from skills.llm_client import LlmClient, dataclass_to_json_schema
from skills.schemas import (
    EmpiricalAnalysis, compute_quality_score, dataclass_to_dict,
)
from skills.quality_gate import QualityGate


class EmpiricalAnalyzer(BaseSkill):
    """
    经济学实证方法论深度分析技能。
    对论文按四维度（假设、方法、变量、结果）进行结构化实证分析，
    输出到论文专属分析目录下，并更新 _paper_summary.json 的 empirical 字段。

    actions:
      - analyze_single  : 单篇论文四维分析
      - compare_multi   : 多篇论文横向比较 + 创新推断
    """

    def __init__(self):
        super().__init__(
            name="EmpiricalAnalyzer",
            description="经济学实证方法论深度分析——四维度结构化剖析与多论文比较"
        )
        self.llm = LlmClient()
        self._prompts_dir = os.path.abspath("references/prompts")
        self._analysis_root = os.path.abspath("workspace/analysis")

    # ─── 公共入口 ──────────────────────────────────────────────

    def execute(self, action: str, **kwargs):
        if action == "analyze_single":
            return self._analyze_single(**kwargs)
        elif action == "compare_multi":
            return self._compare_multi(**kwargs)
        else:
            raise NotImplementedError(f"未实现的动作: {action}")

    # ─── 单篇分析 ──────────────────────────────────────────────

    def _analyze_single(
        self,
        paper: dict,
        paper_text: str = "",
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        对单篇论文进行四维实证分析，输出到论文专属目录。
        :param paper: 论文元数据
        :param paper_text: 论文全文或摘要（用于 LLM 分析）
        """
        title = paper.get("title", "未知标题")
        print(f"\n[{self.name}] 正在对论文进行四维实证分析: {title[:60]}")

        # 确定输出目录（与 LiteratureAnalyzer 一致）
        safe_name = re.sub(r'[<>:"/\\|?*]', '', title.strip())
        if len(safe_name) > 50:
            safe_name = safe_name[:50]
        paper_dir = os.path.join(self._analysis_root, safe_name or "未命名论文")
        os.makedirs(paper_dir, exist_ok=True)

        # 加载 prompt
        prompt_path = os.path.join(self._prompts_dir, "empirical_analysis.txt")
        if not os.path.exists(prompt_path):
            raise FileNotFoundError(f"Prompt 模板不存在: {prompt_path}")

        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()

        # 构建论文文本
        if not paper_text:
            paper_text = self._format_paper(paper, paper_dir=paper_dir)

        full_prompt = template.replace("{paper_text}", paper_text)
        print(f"[{self.name}] Prompt 长度: {len(full_prompt)} 字符")

        try:
            raw_output = self.llm.execute(
                prompt=full_prompt,
                system_prompt="你是一位经济学实证研究方法论专家。请严格按照用户要求的四维度结构输出结构化实证分析报告。",
                backend=backend,
                model=model,
                max_tokens=6000,
            )
        except Exception as e:
            print(f"[{self.name}] 实证分析失败: {e}")
            return {"title": title, "markdown": f"分析失败: {e}", "success": False}

        # ── 保存 Markdown 分析 ──
        md_path = os.path.join(paper_dir, "empirical.md")
        json_path = os.path.join(paper_dir, "empirical.json")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# 实证分析报告: {title}\n\n")
            f.write(raw_output)

        # ── 增强的结构化提取：使用 structured_output ──
        structured = self._extract_structured_v2(raw_output, title, paper, backend, model)

        # 回退：如果新方法失败，使用传统正则
        if structured.get("_json_parse_error") or structured.get("quality_score", 0) < 0.2:
            print(f"[{self.name}] structured_output 质量不足，回退到正则提取")
            fallback = self._extract_structured(raw_output, title)
            if fallback.get("y_var") or fallback.get("x_var"):
                structured = fallback

        structured["quality_score"] = compute_quality_score(structured)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(structured, f, ensure_ascii=False, indent=2)

        # 更新 _paper_summary.json 的 empirical 字段
        self._update_paper_summary_empirical(paper_dir, structured)

        print(f"[{self.name}] 实证分析完成 → {md_path}")
        return {
            "title": title,
            "markdown": raw_output,
            "json": structured,
            "md_path": md_path,
            "json_path": json_path,
            "paper_dir": paper_dir,
            "success": True,
        }

    # ─── 多篇比较 ──────────────────────────────────────────────

    def _compare_multi(
        self,
        single_results: list,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        基于多篇单篇分析结果，生成横向比较矩阵和创新空间推断。
        输出到 _cross_paper 目录。
        """
        print(f"\n[{self.name}] 正在对 {len(single_results)} 篇论文进行横向比较...")

        parts = []
        for i, r in enumerate(single_results):
            if not r.get("success"):
                continue
            parts.append(f"### 论文 {i+1}: {r.get('title', '')}\n\n{r.get('markdown', '')}")

        if len(parts) < 2:
            print(f"[{self.name}] 需要至少 2 篇有效分析才能比较，当前: {len(parts)}")
            return {"success": False, "reason": "not_enough_papers"}

        all_text = "\n\n---\n\n".join(parts)

        compare_prompt = f"""你是一位经济学实证研究方法论专家。请基于以下 {len(parts)} 篇论文的实证分析报告，生成横向比较矩阵和创新空间推断。

{all_text}

【输出要求】

### 比较矩阵一：核心要素概览
（Markdown表格）论文 | 被解释变量 | 核心解释变量测度 | 基准模型 | 内生性策略 | 核心机制 | 核心发现

### 比较矩阵二：共同做法
（Markdown表格）维度 | 共同做法

### 比较矩阵三：差异化特征
（Markdown表格）维度 | 论文1 | ... | 差异分析

### 比较矩阵四：传导机制路径汇总
（Markdown表格）机制路径 | 论文1 | ... | 路径优先级

### 创新空间推断
（Markdown表格）推断维度 | 分析方法 | 输出（测度/方法/机制/情境/视角/连接六个维度）
"""

        try:
            raw_output = self.llm.execute(
                prompt=compare_prompt,
                system_prompt="你是一位经济学实证研究方法论专家。请生成横向比较矩阵和创新空间推断。",
                backend=backend,
                model=model,
                max_tokens=6000,
            )
        except Exception as e:
            print(f"[{self.name}] 比较分析失败: {e}")
            return {"success": False, "reason": str(e)}

        # 输出到 _cross_paper 目录
        output_dir = os.path.join(self._analysis_root, "_cross_paper")
        os.makedirs(output_dir, exist_ok=True)

        cmp_path = os.path.join(output_dir, "empirical_comparison_matrix.md")
        inv_path = os.path.join(output_dir, "empirical_innovation_inference.md")

        # 分割比较矩阵和创新推断
        split_marker = "### 创新空间推断"
        if split_marker in raw_output:
            idx = raw_output.index(split_marker)
            cmp_text = raw_output[:idx].strip()
            inv_text = raw_output[idx:].strip()
        else:
            cmp_text = raw_output
            inv_text = ""

        with open(cmp_path, "w", encoding="utf-8") as f:
            f.write("# 实证方法论横向比较矩阵\n\n")
            f.write(cmp_text)

        with open(inv_path, "w", encoding="utf-8") as f:
            f.write("# 实证创新空间推断\n\n")
            f.write(inv_text)

        print(f"[{self.name}] 比较矩阵 → {cmp_path}")
        print(f"[{self.name}] 创新推断 → {inv_path}")

        return {
            "comparison_matrix": cmp_text,
            "innovation_inference": inv_text,
            "cmp_path": cmp_path,
            "inv_path": inv_path,
            "success": True,
        }

    # ─── 更新 _paper_summary ───────────────────────────────────

    def _update_paper_summary_empirical(self, paper_dir: str, empirical_data: dict):
        """将实证分析结果写入 _paper_summary.json 的 empirical 字段"""
        summary_path = os.path.join(paper_dir, "_paper_summary.json")

        # 读取现有 summary（如果存在）
        summary = {}
        if os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)
            except Exception:
                pass

        # 确保 sections 存在
        if "sections" not in summary:
            summary["sections"] = {}

        # 写入 empirical 数据
        summary["sections"]["empirical"] = {
            "hypotheses": empirical_data.get("hypotheses", {}),
            "model_type": empirical_data.get("model_type", ""),
            "estimation_method": empirical_data.get("estimation_method", ""),
            "y_var": empirical_data.get("y_var", ""),
            "x_var": empirical_data.get("x_var", ""),
            "mechanism_vars": empirical_data.get("mechanism_vars", []),
            "heterogeneity_dims": empirical_data.get("heterogeneity_dims", []),
            "endogeneity_strategy": empirical_data.get("endogeneity_strategy", ""),
            "robustness_checks": empirical_data.get("robustness_checks", []),
            "key_results": empirical_data.get("key_results", []),
            "key_findings": empirical_data.get("key_findings", []),
            "gaps": empirical_data.get("gaps", []),
        }

        # 如果 summary 还没有 paper_title，从 empirical data 补充
        if not summary.get("paper_title") and empirical_data.get("title"):
            summary["paper_title"] = empirical_data["title"]

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    # ─── 辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _format_paper(paper: dict, paper_dir: str = None) -> str:
        """
        格式化论文信息为文本。优先使用 11 维度分析结果中的结构化信息，
        其次使用摘要，最后才降级为"信息不足"。

        :param paper: 论文元数据字典
        :param paper_dir: 论文专属分析目录（包含已完成 11 维度分析的 .md 文件）
        """
        parts = [
            f"标题：{paper.get('title', '未知')}",
            f"作者：{paper.get('authors', '未知')}",
            f"期刊：{paper.get('source', '未知')}（{paper.get('pub_date', '')}）",
            f"关键词：{', '.join(paper.get('keywords', [])) if isinstance(paper.get('keywords'), list) else paper.get('keywords', '')}",
            "",
        ]

        # ── 第〇优先级：PDF 全文 + 数据源声明 ──
        fulltext = paper.get("fulltext", "")
        if fulltext:
            parts.append(
                "## ⚠️ 数据源声明（分析前必读）\n"
                "你收到的材料包含以下全部内容：\n"
                f"1. **PDF全文**（约{len(fulltext)}字符，包含完整引言、理论框架、研究设计、"
                "实证结果、稳健性检验和结论）——这是你的主要数据源。\n"
                "2. 前期11维度分析笔记（已从全文中提取的结构化分析）。\n"
                "3. 论文摘要（简短概括）。\n"
                "4. 元数据（作者、期刊、关键词等）。\n\n"
                "**重要规则**：\n"
                "- 分析时必须基于 PDF 全文中的具体信息，引用论文中的实际方法、数据和结论。\n"
                "- **禁止使用\"基于摘要\"\"摘要中\"\"摘要未提供\"等措辞**——你拥有远超摘要的完整信息。\n"
                "- 如某项信息在所有材料中确实找不到，应标注\"论文未明确说明\"。\n"
                "- PDF 全文可能因提取原因有少量 OCR 噪声，请忽略乱码或格式碎片。\n\n"
                "---\n\n"
            )
            parts.append("【PDF 全文（完整论文文本）】")
            parts.append(fulltext)
            parts.append("")

        # ── 第一优先级：11 维度分析文件中的结构化信息 ──
        if paper_dir and os.path.isdir(paper_dir):
            # 与实证分析相关的维度文件
            dimension_files = {
                "03_identification": "识别策略",
                "04_data_variables": "数据与变量",
                "05_empirical_methodology": "实证方法与模型设定",
                "06_baseline_results": "基准结果",
                "10_endogeneity": "内生性处理",
            }
            collected = []
            for prefix, label in dimension_files.items():
                for fn in os.listdir(paper_dir):
                    if fn.startswith(prefix) and fn.endswith(".md"):
                        path = os.path.join(paper_dir, fn)
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                content = f.read()
                            # 截取正文（去除 JSON 代码块）
                            json_pos = content.find("```json")
                            if json_pos != -1:
                                content = content[:json_pos]
                            if len(content) > 300:
                                collected.append(f"【从 {label} 分析中提取】\n{content[:3000]}")
                        except Exception:
                            pass
                        break
            if collected:
                parts.append("【从 11 维度分析中提取的方法论信息（已由前期文献综述阶段深度分析）】")
                parts.extend(collected)
                parts.append("")

        # ── 第二优先级：论文摘要 ──
        abstract = paper.get("abstract", "")
        if abstract and abstract != "（无摘要）":
            parts.append("【论文摘要】")
            parts.append(abstract)
        elif not (paper_dir and os.path.isdir(paper_dir)):
            parts.append("【论文摘要】")
            parts.append("（无摘要，且无 11 维度分析数据）")

        return "\n".join(parts)

    @staticmethod
    def _extract_structured(markdown: str, title: str) -> dict:
        """
        从 LLM 输出中提取结构化数据。增强版：尝试提取更多可机器处理的信息。
        """
        structured = {
            "title": title,
            "hypotheses": {},
            "model_type": "",
            "estimation_method": "",
            "y_var": "",
            "x_var": "",
            "mechanism_vars": [],
            "heterogeneity_dims": [],
            "endogeneity_strategy": "",
            "robustness_checks": [],
            "key_results": [],
            "key_findings": [],
            "gaps": [],
        }

        # ── 提取假设 ──
        h_matches = re.findall(r'[Hh](\d)[:：]\s*(.+?)(?=\n|$)', markdown)
        for h_num, h_text in h_matches:
            structured["hypotheses"][f"H{h_num}"] = h_text.strip()[:200]

        # ── 提取模型类型 ──
        model_patterns = [
            (r'模型类型.*?[:：]\s*(.+?)(?=\n|$)', 1),
            (r'(固定效应|随机效应|系统GMM|差分GMM|Tobit|Probit|Logit|泊松|Cox|分位数回归)', 1),
            (r'(双重差分|DID|DDD|断点回归|RDD|工具变量|IV|2SLS|PSM|匹配|合成控制|SCM|Heckman)', 1),
        ]
        for pattern, group in model_patterns:
            m = re.search(pattern, markdown, re.IGNORECASE)
            if m:
                structured["model_type"] = m.group(group).strip()[:100]
                break

        # ── 提取 Y/X 变量 ──
        y_patterns = [
            r'被解释变量.*?[:：]\s*(.+?)(?=\n|$)',
            r'[Yy]\s*(?:变量)?[:：=]\s*(.+?)(?=\n|$)',
        ]
        for pattern in y_patterns:
            m = re.search(pattern, markdown)
            if m:
                structured["y_var"] = m.group(1).strip()[:100]
                break

        x_patterns = [
            r'(?:核心[解释]变量|解释变量).*?[:：]\s*(.+?)(?=\n|$)',
            r'[Xx]\s*(?:变量)?[:：=]\s*(.+?)(?=\n|$)',
        ]
        for pattern in x_patterns:
            m = re.search(pattern, markdown)
            if m:
                structured["x_var"] = m.group(1).strip()[:100]
                break

        # ── 提取机制变量（优先从表格，回退到列表）──
        mech_section = re.search(
            r'(?:机制|中介).*?[:：]\n?(.*?)(?=\n###|\n##|\Z)',
            markdown, re.DOTALL | re.IGNORECASE
        )
        if mech_section:
            mech_text = mech_section.group(1)
            # 先尝试表格提取
            mech_vars = re.findall(r'\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|', mech_text)
            if mech_vars:
                structured["mechanism_vars"] = [
                    f"{m[0].strip()}: {m[1].strip()}"[:100]
                    for m in mech_vars[:5]
                    if m[0].strip() not in ('分析项', '--------')
                ]
            else:
                # 回退：限定在当前子节内的 bullet
                mech_sub = re.search(
                    r'(?:中介变量|传导路径|检验方法).*',
                    mech_text, re.DOTALL | re.IGNORECASE
                )
                target = mech_sub.group(0) if mech_sub else mech_text
                mech_list = re.findall(r'[-*]\s*(.+?)(?=\n[-*]|\n\n|\Z)', target, re.DOTALL)
                structured["mechanism_vars"] = [v.strip()[:100] for v in mech_list[:5] if len(v.strip()) > 5]

        # ── 提取异质性维度（优先从表格，回退到列表）──
        het_section = re.search(
            r'(?:异质性|调节).*?[:：]\n?(.*?)(?=\n###|\n##|\Z)',
            markdown, re.DOTALL | re.IGNORECASE
        )
        if het_section:
            het_text = het_section.group(1)
            # 先尝试表格提取
            het_dims = re.findall(r'\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|', het_text)
            if het_dims:
                structured["heterogeneity_dims"] = [
                    f"{h[0].strip()}: {h[1].strip()}"[:100]
                    for h in het_dims[:5]
                    if h[0].strip() not in ('分析项', '--------')
                ]
            else:
                # 回退：限定在当前子节内的 bullet
                het_sub = re.search(
                    r'(?:调节变量|分组标准|关键发现).*',
                    het_text, re.DOTALL | re.IGNORECASE
                )
                target = het_sub.group(0) if het_sub else het_text
                het_list = re.findall(r'[-*]\s*(.+?)(?=\n[-*]|\n\n|\Z)', target, re.DOTALL)
                structured["heterogeneity_dims"] = [h.strip()[:100] for h in het_list[:5] if len(h.strip()) > 5]

        # ── 提取内生性策略 ──
        endo_patterns = [
            r'内生性策略.*?[:：]\s*(.+?)(?=\n|$)',
            r'内生性处理.*?[:：]\s*(.+?)(?=\n|$)',
        ]
        for pattern in endo_patterns:
            m = re.search(pattern, markdown, re.IGNORECASE)
            if m:
                structured["endogeneity_strategy"] = m.group(1).strip()[:200]
                break

        # ── 提取稳健性检验（优先从表格，回退到列表，过滤缺省标注）──
        rob_section = re.search(
            r'(?:稳健性).*?[:：]\n?(.*?)(?=\n###|\n##|\Z)',
            markdown, re.DOTALL | re.IGNORECASE
        )
        if rob_section:
            rob_text = rob_section.group(1)
            # 先尝试表格提取
            rob_rows = re.findall(r'\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|', rob_text)
            if rob_rows:
                structured["robustness_checks"] = [
                    f"{r[0].strip()}: {r[1].strip()}"[:100]
                    for r in rob_rows[:8]
                    if r[0].strip() not in ('分析项', '--------')
                    and not any(p in r[1] for p in ['未明确说明', '未提供', '信息不足'])
                ]
            else:
                rob_items = re.findall(r'[-*]\s*(.+?)(?=\n[-*]|\n\n|\Z)', rob_text, re.DOTALL)
                structured["robustness_checks"] = [
                    r.strip()[:100] for r in rob_items[:8]
                    if len(r.strip()) > 5
                    and not any(p in r for p in ['未明确说明', '未提供', '信息不足'])
                ]

        # ── 提取关键发现（仅从"实证结果"或"四、"章节提取）──
        findings_section = ""
        for header in [r'###?\s*四[、，\s]*实证结果', r'###?\s*实证结果', r'###?\s*4[\.\s]*实证']:
            m = re.search(
                header + r'.*?(?=\n###|\n##|\Z)',
                markdown, re.DOTALL | re.IGNORECASE
            )
            if m:
                findings_section = m.group(0)
                break
        if findings_section:
            findings = []
            # 先尝试从 markdown 表格中提取（| **标签** | 内容 |）
            table_rows = re.findall(
                r'\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|',
                findings_section
            )
            for label, value in table_rows:
                label = label.strip()
                value = value.strip()
                # 跳过表头行和纯标记行
                if label in ('分析项', '--------'):
                    continue
                # 跳过"未明确说明"等纯缺省标注
                skip_phrases = ['未明确说明', '未提供', '信息不足', '信息缺失', '未提及', '未报告']
                if any(p in value for p in skip_phrases) and len(value) < 50:
                    continue
                combined = f"{label}: {value}"[:250]
                if len(combined) > 15:
                    findings.append(combined)
            # 回退：也提取列表项
            if not findings:
                for line in findings_section.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('#') or line.startswith('|'):
                        continue
                    if set(line.strip()) <= {'-', '|', ' '}:
                        continue
                    if line.startswith('- ') or line.startswith('* '):
                        text = line[2:].strip()
                        if len(text) > 15:
                            skip_phrases = ['未明确说明', '未提供', '信息不足', '信息缺失']
                            if not any(p in text for p in skip_phrases):
                                findings.append(text[:200])
            structured["key_findings"] = findings[:10]
        else:
            structured["key_findings"] = []

        # ── 提取估计方法 ──
        est_match = re.search(r'估计方法.*?[:：]\s*(.+?)(?=\n|$)', markdown, re.IGNORECASE)
        if est_match:
            structured["estimation_method"] = est_match.group(1).strip()[:100]

        return structured

    def _extract_structured_v2(
        self,
        markdown: str,
        title: str,
        paper: dict = None,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        使用 structured_output() 进行增强的结构化提取。

        与传统的 _extract_structured (纯正则) 相比，此方法：
        - 强制 LLM 输出符合 EmpiricalAnalysis Schema 的 JSON
        - 自动重试（最多 2 次）
        - 质量验证（关键字段非空检查）
        """
        output_schema = dataclass_to_json_schema(EmpiricalAnalysis)
        gate = QualityGate(threshold=0.3)

        extraction_prompt = (
            f"以下是一篇论文的「实证方法论四维分析」报告。\n"
            f"请从中提取结构化信息，严格按照要求的 JSON Schema 输出。\n\n"
            f"【论文标题】{title}\n\n"
            f"【分析报告】\n{markdown[:10000]}\n\n"
            f"请基于以上分析报告，输出结构化 JSON。\n"
            f"关键要求：\n"
            f"1. hypotheses 字段必须是一个数组，每个假设包含 id/content/direction/theory_basis 字段\n"
            f"2. y_var 和 x_var 必须填写具体的变量名（不能为空字符串）\n"
            f"3. model_type 和 estimation_method 必须使用计量经济学术语\n"
            f"4. 所有字段必须填写，无法确定时标注\"论文未明确说明\""
        )

        try:
            structured = self.llm.structured_output(
                prompt=extraction_prompt,
                output_schema=output_schema,
                system_prompt="你是一位经济学实证研究方法论专家。请精确提取实证方法论的结构化数据，使用精确的计量术语。",
                backend=backend,
                model=model,
                max_tokens=4000,
                max_retries=2,
                quality_validator=gate.make_validator("empirical"),
            )
            structured["title"] = title
            structured["quality_score"] = compute_quality_score(structured)
            return structured
        except Exception as e:
            print(f"  [EmpiricalAnalyzer] structured_output_v2 失败: {e}")
            return {"title": title, "_json_parse_error": str(e), "quality_score": 0.0}
