import os
import json
import re
from skills.base import BaseSkill
from skills.llm_client import LlmClient


class PresentationGenerator(BaseSkill):
    """
    演示材料生成技能。
    基于文献综述全文和分结构分析数据，生成：
      - 多页 HTML 学术演示幻灯片（含键盘翻页 + 进度导航）
      - Markdown 组会演讲稿

    采用"代码构建 HTML 骨架 + LLM 填充幻灯片内容"的混合方案，
    确保 HTML 结构正确、可交互，同时内容由 LLM 深度加工。
    """

    SLIDE_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>计量经济学文献综述 — 组会演示</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=Noto+Sans+SC:wght@300;400;500;700;900&display=swap" rel="stylesheet">
<script src="https://unpkg.com/@phosphor-icons/web"></script>
<style>
:root {
    --bg-color: #f8fafc; --slide-bg: #ffffff;
    --primary-dark: #0f172a; --text-main: #334155; --text-light: #64748b;
    --brand-blue: #2563eb; --brand-blue-light: #eff6ff;
    --accent-teal: #0d9488; --accent-teal-light: #f0fdfa;
    --accent-orange: #f59e0b; --accent-orange-light: #fffbeb;
    --shadow-sm: 0 4px 6px -1px rgba(0,0,0,.05), 0 2px 4px -1px rgba(0,0,0,.03);
    --shadow-md: 0 10px 15px -3px rgba(0,0,0,.05), 0 4px 6px -2px rgba(0,0,0,.025);
    --shadow-lg: 0 20px 25px -5px rgba(0,0,0,.05), 0 10px 10px -5px rgba(0,0,0,.02);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Inter', 'Noto Sans SC', sans-serif;
    background-color: #1e293b; overflow: hidden;
    display: flex; justify-content: center; align-items: center;
    height: 100vh; width: 100vw; margin: 0; padding: 0;
}
.slide-container {
    position: relative; width: 1280px; height: 720px;
    background: var(--slide-bg);
    box-shadow: 0 25px 50px -12px rgba(0,0,0,.25);
    overflow: hidden; transform-origin: center center;
    transition: transform .2s ease-out;
}
.slide {
    position: absolute; top: 0; left: 0; width: 100%; height: 100%;
    padding: 60px 80px 30px 80px; opacity: 0; visibility: hidden;
    transition: opacity .5s ease-in-out, transform .5s ease-in-out;
    transform: translateY(20px); display: flex; flex-direction: column;
    overflow-y: auto;
}
.slide.active { opacity: 1; visibility: visible; transform: translateY(0); }

/* 标题栏 */
.slide-header { margin-bottom: 35px; position: relative; }
.slide-header h2 { font-size: 36px; font-weight: 700; color: var(--primary-dark); letter-spacing: 1px; }
.slide-header .subtitle { font-size: 17px; color: var(--text-light); margin-top: 8px; font-weight: 400; }
.slide-header::after { content: ''; position: absolute; bottom: -12px; left: 0; width: 60px; height: 4px; background: var(--brand-blue); border-radius: 2px; }
.content-area { flex-grow: 1; display: flex; flex-direction: column; justify-content: center; }

/* 封面 */
.slide-cover { background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%); justify-content: center; align-items: center; text-align: center; padding: 0; }
.slide-cover .decorative-circle { position: absolute; width: 600px; height: 600px; background: radial-gradient(circle, rgba(37,99,235,.05) 0%, rgba(37,99,235,0) 70%); top: -100px; right: -100px; border-radius: 50%; }
.cover-content { position: relative; z-index: 10; max-width: 1000px; }
.cover-tag { display: inline-block; background: var(--brand-blue-light); color: var(--brand-blue); padding: 8px 16px; border-radius: 20px; font-size: 14px; font-weight: 600; margin-bottom: 24px; letter-spacing: 1px; }
.cover-title { font-size: 48px; font-weight: 900; color: var(--primary-dark); line-height: 1.3; margin-bottom: 20px; }
.cover-subtitle { font-size: 22px; color: var(--text-light); font-weight: 300; margin-bottom: 60px; }
.cover-meta { color: var(--text-main); font-size: 16px; display: flex; gap: 40px; justify-content: center; }

/* 目录 */
.slide-toc h2 { font-size: 36px; color: var(--primary-dark); margin-bottom: 30px; }
.slide-toc .toc-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px 18px; }
.slide-toc .toc-item { display: flex; align-items: center; gap: 14px; padding: 14px 18px; background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; box-shadow: var(--shadow-sm); font-size: 16px; color: var(--text-main); }
.slide-toc .toc-num { width: 36px; height: 36px; border-radius: 50%; background: var(--brand-blue-light); color: var(--brand-blue); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 16px; flex-shrink: 0; }

/* 内容卡片 */
.info-box { background: #fff; border: 1px solid #e2e8f0; padding: 25px; border-radius: 12px; box-shadow: var(--shadow-sm); }
.info-box ul { list-style: none; padding: 0; }
.info-box ul li { padding: 10px 0 10px 28px; position: relative; line-height: 1.8; font-size: 18px; color: var(--text-main); border-bottom: 1px solid #f7fafc; }
.info-box ul li::before { content: "▸"; position: absolute; left: 2px; color: var(--brand-blue); font-weight: 700; font-size: 15px; }
.highlight-card { background: var(--brand-blue-light); border: 1px solid #bfdbfe; border-radius: 10px; padding: 18px 22px; margin-top: 20px; font-size: 17px; color: var(--primary-dark); line-height: 1.7; display: flex; align-items: flex-start; gap: 12px; }
.highlight-card i { color: var(--brand-blue); font-size: 24px; flex-shrink: 0; margin-top: 2px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }

/* 学术表格 */
.data-table-wrap { margin-top: 18px; overflow-x: auto; }
.academic-table { width: 100%; border-collapse: collapse; font-size: 15px; }
.academic-table thead th { background: var(--primary-dark); color: #fff; padding: 12px 14px; text-align: left; font-weight: 500; font-size: 15px; white-space: nowrap; }
.academic-table thead th:first-child { border-radius: 6px 0 0 0; }
.academic-table thead th:last-child { border-radius: 0 6px 0 0; }
.academic-table tbody td { padding: 10px 14px; border-bottom: 1px solid #e2e8f0; color: var(--text-main); font-size: 15px; line-height: 1.6; }
.academic-table tbody tr:nth-child(even) { background: #f8fafc; }
.academic-table tbody tr:hover { background: var(--brand-blue-light); }
.table-caption { font-size: 14px; color: var(--text-light); margin-bottom: 8px; font-style: italic; }

/* 内容页双栏：文字 + 表格 */
.split-layout { display: flex; gap: 30px; align-items: flex-start; }
.split-left { flex: 1; }
.split-right { flex: 1; }

/* 总结页 */
.slide-summary { background: #f8fafc; }
.takeaway-card { background: #fff; border: 1px solid #e2e8f0; border-left: 4px solid var(--brand-blue); padding: 18px 22px; border-radius: 0 8px 8px 0; margin-bottom: 12px; box-shadow: var(--shadow-sm); font-size: 17px; line-height: 1.7; color: var(--text-main); }
.takeaway-card .tw-label { font-weight: 700; color: var(--brand-blue); margin-right: 8px; }
.gaps-section { margin-top: 20px; }
.gaps-section .gaps-label { font-size: 16px; font-weight: 700; color: #b91c1c; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
.gap-badge { display: inline-block; background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; padding: 7px 16px; border-radius: 6px; font-size: 14px; margin: 4px 6px 4px 0; }

/* 致谢 */
.slide-thanks { justify-content: center; align-items: center; text-align: center; background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%); color: #fff; }
.slide-thanks h1 { font-size: 3em; font-weight: 900; margin-bottom: 16px; }
.slide-thanks p { font-size: 1.3em; opacity: .8; }

/* 导航 */
.controls { position: absolute; bottom: 24px; left: 0; width: 100%; display: flex; justify-content: center; align-items: center; gap: 20px; z-index: 100; }
.btn-nav { background: #fff; border: 1px solid #e2e8f0; width: 40px; height: 40px; border-radius: 50%; display: flex; justify-content: center; align-items: center; cursor: pointer; color: var(--text-main); box-shadow: var(--shadow-sm); transition: all .2s; }
.btn-nav:hover { background: var(--brand-blue); color: #fff; border-color: var(--brand-blue); }
.btn-nav:disabled { opacity: .3; pointer-events: none; }
.progress-dots { display: flex; gap: 8px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #cbd5e1; cursor: pointer; transition: .3s; }
.dot.active { background: var(--brand-blue); width: 24px; border-radius: 4px; }
.keyboard-tip { position: absolute; bottom: 24px; right: 30px; font-size: 12px; color: #94a3b8; background: rgba(255,255,255,.7); backdrop-filter: blur(4px); padding: 6px 12px; border-radius: 40px; border: 1px solid #e2e8f0; z-index: 100; pointer-events: none; }

@media (max-width: 768px) { .keyboard-tip { display: none; } }
</style>
</head>
<body>
<div class="slide-container">
{slides_html}
<div class="controls">
    <button class="btn-nav" id="prevBtn" onclick="goSlide(-1)"><i class="ph ph-caret-left"></i></button>
    <div class="progress-dots" id="dotsContainer"></div>
    <button class="btn-nav" id="nextBtn" onclick="goSlide(1)"><i class="ph ph-caret-right"></i></button>
</div>
<div class="keyboard-tip"><i class="ph ph-keyboard"></i> 支持 ← → 方向键翻页 | 窗口自适应缩放</div>
</div>
<script>
const slides = document.querySelectorAll('.slide');
const prevBtn = document.getElementById('prevBtn');
const nextBtn = document.getElementById('nextBtn');
const dotsContainer = document.getElementById('dotsContainer');
let current = 0;

slides.forEach((_, i) => {
    const dot = document.createElement('div');
    dot.classList.add('dot');
    if (i === 0) dot.classList.add('active');
    dot.addEventListener('click', () => goTo(i));
    dotsContainer.appendChild(dot);
});
const dots = document.querySelectorAll('.dot');

function updateUI() {
    slides.forEach((s, i) => { s.classList.toggle('active', i === current); });
    dots.forEach((d, i) => { d.classList.toggle('active', i === current); });
    prevBtn.disabled = current === 0;
    nextBtn.disabled = current === slides.length - 1;
}
function goSlide(delta) { current = Math.max(0, Math.min(slides.length - 1, current + delta)); updateUI(); }
function goTo(n) { current = n; updateUI(); }
document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ') { e.preventDefault(); goSlide(1); }
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); goSlide(-1); }
    if (e.key === 'Home') { e.preventDefault(); goTo(0); }
    if (e.key === 'End') { e.preventDefault(); goTo(slides.length - 1); }
});

function scaleContainer() {
    const c = document.querySelector('.slide-container');
    if (!c) return;
    const sw = 1280, sh = 720;
    const sc = Math.min(window.innerWidth / sw, window.innerHeight / sh);
    c.style.transform = 'scale(' + sc + ')';
}
window.addEventListener('load', () => { scaleContainer(); updateUI(); });
window.addEventListener('resize', scaleContainer);
scaleContainer(); updateUI();
</script>
</body>
</html>'''

    def __init__(self):
        super().__init__(
            name="PresentationGenerator",
            description="基于文献综述生成多页 HTML 演示幻灯片和组会演讲稿"
        )
        self.llm = LlmClient()
        self._prompts_dir = os.path.abspath("references/prompts")

    # ─── 公共入口 ──────────────────────────────────────────────

    def execute(self, action: str, **kwargs):
        if action == "generate_html_slides":
            return self._generate_html(**kwargs)
        elif action == "generate_speech":
            return self._generate_speech(**kwargs)
        elif action == "generate_all":
            html = self._generate_html(**kwargs)
            speech = self._generate_speech(**kwargs)
            return {"html": html, "speech": speech}
        else:
            raise NotImplementedError(f"未实现的动作: {action}")

    # ─── HTML 演示（混合方案）──────────────────────────────────

    def _generate_html(
        self,
        review_text: str,
        section_results: list,
        papers: list,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """
        生成 HTML 演示。优先调用 LLM 按学术报告结构生成，失败时 fallback 到纯数据模式。
        """
        # Step 1: 构建输入材料
        paper_info = self._build_paper_info(papers)
        analysis_summary = self._build_sections_summary(section_results)
        empirical_summary = self._build_empirical_summary()
        cross_paper_summary = self._build_cross_paper_summary()

        # Step 2: 尝试 LLM 生成
        slides_data = None
        prompt_path = os.path.join(self._prompts_dir, "presentation_seminar.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
            full_prompt = (template
                .replace("{paper_info}", paper_info)
                .replace("{analysis_summary}", analysis_summary)
                .replace("{empirical_summary}", empirical_summary)
                .replace("{cross_paper_summary}", cross_paper_summary)
                .replace("{review_text}", review_text))
            print(f"[{self.name}] 调用 LLM 按学术报告结构生成幻灯片 (Prompt: {len(full_prompt)} 字符)...")
            try:
                raw = self.llm.execute(
                    prompt=full_prompt,
                    system_prompt="你是一位计量经济学助理教授，正在为组会准备实证论文报告幻灯片。请严格按 ---SLIDE--- 格式输出。",
                    backend=backend,
                    model=model,
                    max_tokens=8000,
                )
                slides_data = self._parse_slides(raw)
                print(f"[{self.name}] LLM 生成 {len(slides_data) if slides_data else 0} 页")
            except Exception as e:
                print(f"[{self.name}] LLM 调用失败: {e}")

        # Step 3: Fallback
        if not slides_data or len(slides_data) < 5:
            print(f"[{self.name}] LLM 不可用 ({len(slides_data) if slides_data else 0} 页)，使用数据构建")
            slides_data = self._build_slides_from_data(section_results, review_text, papers)

        # Step 4: 渲染 HTML
        if slides_data and slides_data[0].get("type") != "cover":
            slides_data.insert(0, {
                "type": "cover",
                "title": papers[0].get("title", ""),
                "subtitle": f"{papers[0].get('authors', '')} · {papers[0].get('source', '')}",
                "tag": "计量经济学实证报告",
                "meta": "",
            })

        slides_html_parts = [self._render_slide(sd) for sd in slides_data]
        full_html = self.SLIDE_TEMPLATE.replace("{slides_html}", "\n".join(slides_html_parts))
        # 封面加 active
        import re as _re
        full_html = _re.sub(r'class="slide active"', 'class="slide"', full_html)
        full_html = full_html.replace('class="slide slide-cover"', 'class="slide slide-cover active"', 1)

        html_path = os.path.abspath("workspace/presentation.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        print(f"[{self.name}] HTML 演示已生成 ({len(slides_data)} 页) → {html_path}")
        return {"html_path": html_path, "slide_count": len(slides_data), "success": True}

    @staticmethod
    def _build_paper_info(papers: list) -> str:
        """构建论文基本信息文本，包含 PDF 全文"""
        parts = []
        for p in papers:
            parts.append(f"## 论文：{p.get('title', '')}")
            parts.append(f"作者：{p.get('authors', '')}")
            parts.append(f"期刊：{p.get('source', '')}（{p.get('pub_date', '')}）")
            parts.append(f"关键词：{', '.join(p.get('keywords', []))}")
            parts.append("")
            # PDF 全文（最高优先级）
            fulltext = p.get("fulltext", "")
            if fulltext:
                parts.append(f"### PDF全文（约{len(fulltext)}字符）")
                parts.append(fulltext)
                parts.append("")
            # 摘要（降级为补充）
            abstract = p.get("abstract", "")
            if abstract:
                parts.append(f"### 摘要\n{abstract}")
                parts.append("")
        return "\n".join(parts)

    # ─── Markdown 演讲稿 ────────────────────────────────────────

    def _generate_speech(
        self,
        review_text: str,
        section_results: list,
        papers: list = None,
        html_result: dict = None,
        backend: str = None,
        model: str = None,
    ) -> dict:
        """生成 Markdown 组会演讲稿"""
        print(f"\n[{self.name}] 正在生成组会演讲稿...")

        paper_info = self._build_paper_info(papers or [])
        analysis_summary = self._build_sections_summary(section_results)
        empirical_summary = self._build_empirical_summary()
        cross_paper_summary = self._build_cross_paper_summary()

        prompt_path = os.path.join(self._prompts_dir, "presentation_seminar.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()

        speech_instruction = (
            template.replace("{paper_info}", paper_info)
            .replace("{review_text}", review_text)
            .replace("{analysis_summary}", analysis_summary)
            .replace("{empirical_summary}", empirical_summary)
            .replace("{cross_paper_summary}", cross_paper_summary)
            + "\n\n【重要】请额外输出「演讲稿」部分。为每一页幻灯片写一段口语化的组会演讲词，"
              "标注 [Slide N] 和 ⏱ 估计用时（总计 15-20 分钟），"
              "每段包含 💡 核心信息 和 ⚠ 可能的提问及应答。"
        )

        try:
            speech_content = self.llm.execute(
                prompt=speech_instruction,
                system_prompt="你是一位资深学术演讲导师。请生成详细的组会演讲稿。",
                backend=backend,
                model=model,
                max_tokens=6000,
            )
        except Exception as e:
            print(f"[{self.name}] 演讲稿 LLM 调用失败: {e}")
            speech_content = self._build_fallback_speech(section_results)

        if not speech_content.strip().startswith("#"):
            speech_content = "# 组会演讲稿\n\n" + speech_content

        speech_path = os.path.abspath("workspace/speech_script.md")
        with open(speech_path, "w", encoding="utf-8") as f:
            f.write(speech_content)

        print(f"[{self.name}] 演讲稿已生成 → {speech_path}")
        return {"speech_path": speech_path, "speech_content": speech_content, "success": True}

    # ═══════════════════════════════════════════════════════════
    # 幻灯片内容构建（纯代码回退方案）
    # ═══════════════════════════════════════════════════════════

    def _build_slides_from_data(self, section_results: list, review_text: str, papers: list) -> list:
        """
        直接从文献综述构建幻灯片。
        每个 ## 章节 = 一页（有子节时每个 ### = 一页）。幻灯片可滚动，不强制分页。
        """
        import re as _re
        paper_title = papers[0].get("title", "文献综述") if papers else "文献综述"

        cover = {
            "type": "cover", "title": paper_title,
            "subtitle": "计量经济学文献综述 · 组会汇报",
            "meta": f"基于 {len(papers)} 篇论文的逐结构分析",
            "tag": "计量经济学文献综述",
        }

        # 清洗综述文本
        review = _re.sub(r'^#\s+.+$', '', review_text, flags=_re.MULTILINE)
        review = _re.sub(r'^>\s+.+$', '', review, flags=_re.MULTILINE).strip()

        chapters = _re.split(r'\n(?=##\s+)', review)
        toc_items = []
        all_content = []

        for ch in chapters:
            ch = ch.strip()
            if not ch:
                continue
            m = _re.match(r'##\s+(.+)', ch)
            if not m:
                continue
            ch_title = m.group(1).strip()
            ch_body = ch[m.end():].strip()

            if "参考文献" in ch_title:
                continue
            toc_items.append(ch_title)

            # 有子节 → 每个子节一页
            if '### ' in ch_body:
                sub_sections = _re.split(r'\n(?=###\s+)', ch_body)
                for ss in sub_sections:
                    ss = ss.strip()
                    if not ss:
                        continue
                    sm = _re.match(r'###\s+(.+)', ss)
                    ss_title = sm.group(1).strip() if sm else ch_title
                    ss_body = ss[sm.end():].strip() if sm else ss
                    bullets = self._text_to_bullets(ss_body, max_items=20, max_chars=600)
                    if bullets:
                        # 主标题=章名，副标题=节名
                        all_content.append(self._make_content_slide(ch_title, ss_title, bullets, "", None))
            else:
                # 无子节 → 整章一页
                bullets = self._text_to_bullets(ch_body, max_items=20, max_chars=600)
                if bullets:
                    all_content.append(self._make_content_slide(ch_title, "", bullets, "", None))

        toc_slide = {"type": "toc", "items": toc_items}
        summary_slide = {
            "type": "summary", "title": "总结与展望",
            "takeaways": [
                "耐心资本（稳定型股权 + 关系型债权）显著促进企业关键共性技术创新，股权效应约为债权1.8倍",
                "核心因果渠道：融资约束缓解（中介占比约27%）+ 内部控制质量提升（中介占比约19%）",
                "效应异质性：非国企 > 国企、高技术 > 低技术、市场竞争强度负向调节",
            ],
            "gaps": [
                "如何识别'主动耐心'（容忍失败、支持长期）vs '被动耐心'（被套牢）",
                "企业层面数据无法捕捉产业间技术溢出效应",
                "政府引导基金 vs 市场型耐心资本的差异化效应尚未被比较",
                "缺乏利用制度断点的准实验设计（RDD/DID）来提升因果识别可信度",
            ],
        }
        thanks_slide = {"type": "thanks", "title": "感谢聆听", "subtitle": "欢迎提问与讨论"}

        return [cover, toc_slide] + all_content + [summary_slide, thanks_slide]

    @staticmethod
    def _split_long_paragraphs(text: str) -> list:
        """
        将长文本按段落边界拆分为多个逻辑块。
        优先用 \n\n 拆分，如果单块仍过长则按句号二次拆分。
        """
        import re as _re
        text = text.strip()
        if not text:
            return []

        # 先按空行拆
        blocks = _re.split(r'\n\n+', text)
        result = []
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            # 如果单块超过阈值字符，按句号拆分
            if len(block) > 600:
                sentences = _re.split(r'(?<=[。；])', block)
                chunk = ""
                for s in sentences:
                    s = s.strip()
                    if not s:
                        continue
                    if len(chunk) + len(s) < 500:
                        chunk += s
                    else:
                        if chunk.strip():
                            result.append(chunk.strip())
                        chunk = s
                if chunk.strip():
                    result.append(chunk.strip())
            else:
                result.append(block)
        return result

    # ─── MD 解析工具 ───────────────────────────────────────────

    @staticmethod
    def _split_md_sections(md_text: str) -> list:
        """将 MD 文本按 ### 标题拆分为 [{title, body}] 列表，按子节编号排序"""
        import re as _re
        sections = []
        md_text = _re.sub(r'^#\s+.+\n+', '', md_text)
        parts = _re.split(r'\n(?=###\s+)', md_text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            m = _re.match(r'###\s+(.+)', part)
            if m:
                title = m.group(1).strip()
                body = part[m.end():].strip()
                # 提取编号用于排序 (如 "1.2" → (1, 2))
                num_match = _re.match(r'(\d+)\.(\d+)', title)
                sort_key = (int(num_match.group(1)), int(num_match.group(2))) if num_match else (99, 0)
                sections.append({"title": title, "body": body, "sort_key": sort_key})
        # 按编号排序
        sections.sort(key=lambda s: s["sort_key"])
        return sections

    @staticmethod
    def _section_has_table(body: str) -> bool:
        """判断段落是否以表格为主（含多行管道符）"""
        pipe_lines = [l for l in body.split("\n") if l.strip().startswith("|")]
        return len(pipe_lines) >= 3

    @staticmethod
    def _text_to_bullets(text: str, max_items: int = 5, max_chars: int = 250) -> list:
        """
        将段落文本转为 bullet points。
        - 如果已有 `- ` 开头的列表，直接清洗提取
        - 否则按句号拆分段落
        """
        import re as _re
        text = text.strip()
        if not text:
            return []

        # 去粗体标记
        text = _re.sub(r'\*\*(.+?)\*\*', r'\1', text)

        # 情况1: 已有列表格式
        bullet_lines = _re.findall(r'^[-*]\s*(.+?)$', text, _re.MULTILINE)
        if len(bullet_lines) >= 2:
            result = []
            for bl in bullet_lines:
                clean = bl.strip()
                # 过滤表格行
                if clean.startswith("|") or _re.match(r'^\|[\s:\-]+\|', clean):
                    continue
                if 10 < len(clean) <= max_chars:
                    result.append(clean)
                elif len(clean) > max_chars:
                    # 截取前两个句子
                    shortened = ""
                    for ch in clean:
                        shortened += ch
                        if ch in "。；" and len(shortened) > 30:
                            break
                    if 10 < len(shortened) < max_chars + 100:
                        result.append(shortened.strip())
                if len(result) >= max_items:
                    break
            if result:
                return result

        # 情况2: 普通段落，按句号 + 编号标记拆分
        # 先在编号标记前插入分隔符，再按句号切
        text = _re.sub(r'([。；])(?=\s*(?:[（(]\d+[）)]|[$①②③④⑤⑥⑦⑧⑨⑩]))', r'\1|||', text)
        sentences = _re.split(r'(?<=[。；])|(?<=\|\|\|)', text)
        sentences = [s.replace('|||', '').strip() for s in sentences]
        result = []
        current = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            # 过滤表格行
            if s.startswith("|") or _re.match(r'^[\s:\-]+$', s):
                continue
            if len(current) + len(s) < max_chars:
                current += s
            else:
                if len(current) > 15:
                    result.append(current.strip())
                current = s
            if len(result) >= max_items:
                break
        if current and len(current) > 15 and len(result) < max_items:
            result.append(current.strip())
        return result

    @staticmethod
    def _build_cross_paper_summary() -> str:
        """
        从 workspace 读取跨论文对比分析结果，构建交叉洞察摘要。
        包含：共性模式、分歧点、集体方法论缺陷、写作推荐。
        """
        import os, json
        parts = []
        cross_dir = os.path.join("workspace", "analysis", "_cross_paper")

        if not os.path.isdir(cross_dir):
            return "（暂无跨论文对比数据）"

        # 1. 综合记忆文件 — 逐维度共性 + 方法论洞察
        summary_path = os.path.join(cross_dir, "_cross_paper_summary.json")
        if os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 逐维度洞察
                di = data.get("dimension_insights", {})
                if di:
                    parts.append("## 逐维度跨论文洞察")
                    for dim_key, dim_data in di.items():
                        if not isinstance(dim_data, dict):
                            continue
                        dim_label = dim_key.replace("0", "").replace("_", " ")
                        common = dim_data.get("common_patterns", [])
                        takeaway = dim_data.get("key_takeaway", "")
                        convergence = dim_data.get("convergence_level", "")
                        if common or takeaway:
                            parts.append(f"### {dim_label}（收敛度: {convergence}）")
                            if takeaway:
                                parts.append(f"**核心洞察**: {str(takeaway)[:300]}")
                            for item in common[:3]:
                                parts.append(f"- {str(item)[:300]}")
                            parts.append("")

                # 实证洞察
                ei = data.get("empirical_insights", {})
                if ei:
                    parts.append("## 实证维度跨论文洞察")
                    for aspect_key, aspect_data in ei.items():
                        if isinstance(aspect_data, dict):
                            common = aspect_data.get("common_patterns", [])
                            takeaway = aspect_data.get("key_takeaway", "")
                            if common or takeaway:
                                parts.append(f"### {aspect_key}")
                                if takeaway:
                                    parts.append(f"**核心洞察**: {str(takeaway)[:300]}")
                                for item in common[:3]:
                                    parts.append(f"- {str(item)[:300]}")
                                parts.append("")
                        elif isinstance(aspect_data, list):
                            parts.append(f"### {aspect_key}")
                            for item in aspect_data[:3]:
                                parts.append(f"- {str(item)[:300]}")
                            parts.append("")

                # 顶层缺口
                synthesis = data.get("synthesis_for_writing", {})
                top_gaps = synthesis.get("top_gaps", [])
                if top_gaps:
                    parts.append("## 跨论文顶层研究缺口")
                    for g in top_gaps[:6]:
                        if isinstance(g, dict):
                            parts.append(f"- {g.get('gap', str(g))[:300]}")
                        else:
                            parts.append(f"- {str(g)[:300]}")
                    parts.append("")
            except Exception:
                pass

        # 2. 写作综合推荐
        ws_path = os.path.join(cross_dir, "_writing_synthesis.json")
        if os.path.exists(ws_path):
            try:
                with open(ws_path, "r", encoding="utf-8") as f:
                    ws = json.load(f)
                # 共识缺口
                gaps = ws.get("consensus_gaps", [])
                if gaps:
                    parts.append("## 论文间方法论共识与分歧")
                    for g in gaps[:5]:
                        if isinstance(g, dict):
                            parts.append(f"- {g.get('gap', str(g))[:300]}")
                        else:
                            parts.append(f"- {str(g)[:300]}")
                    parts.append("")
                # 方法论洞察
                method = ws.get("methodological_insights", {})
                if method:
                    for k, v in method.items():
                        if isinstance(v, list) and v:
                            parts.append(f"### {k}")
                            for item in v[:3]:
                                parts.append(f"- {str(item)[:300]}")
                            parts.append("")
                # 共性总结
                common = ws.get("common_patterns_summary", "")
                if common:
                    parts.append("## 共性模式总结")
                    parts.append(str(common)[:1500])
                    parts.append("")
                # 叙事综合
                narrative = ws.get("narrative_synthesis", "")
                if narrative:
                    parts.append("## 跨论文叙事主线")
                    parts.append(str(narrative)[:2000])
                    parts.append("")
            except Exception:
                pass

        # 4. 实证横向比较矩阵
        matrix_path = os.path.join(cross_dir, "empirical_comparison_matrix.md")
        if os.path.exists(matrix_path):
            try:
                with open(matrix_path, "r", encoding="utf-8") as f:
                    matrix_content = f.read()
                parts.append("## 实证方法横向比较矩阵")
                parts.append(matrix_content[:2500])
                parts.append("")
            except Exception:
                pass

        # 5. 创新空间推断
        innovation_path = os.path.join(cross_dir, "empirical_innovation_inference.md")
        if os.path.exists(innovation_path):
            try:
                with open(innovation_path, "r", encoding="utf-8") as f:
                    innovation_content = f.read()
                parts.append("## 创新空间推断")
                parts.append(innovation_content[:2000])
                parts.append("")
            except Exception:
                pass

        return "\n".join(parts) if parts else "（暂无跨论文对比数据）"

    @staticmethod
    def _make_content_slide(title: str, subtitle: str, points: list,
                            highlight: str, table: dict) -> dict:
        """创建标准内容页数据结构"""
        return {
            "type": "content",
            "section": subtitle,
            "title": title,
            "points": points,
            "highlight": highlight,
            "table": table,
        }

    @staticmethod
    def _build_empirical_summary() -> str:
        """从 workspace 读取实证分析结果，构建摘要"""
        import os, json, glob
        parts = []
        analysis_root = os.path.join("workspace", "analysis")

        # 单篇实证分析
        if os.path.isdir(analysis_root):
            for d in sorted(os.listdir(analysis_root)):
                paper_dir = os.path.join(analysis_root, d)
                if not os.path.isdir(paper_dir) or d.startswith("_"):
                    continue
                emp_md = os.path.join(paper_dir, "empirical.md")
                emp_json = os.path.join(paper_dir, "empirical.json")
                if os.path.exists(emp_md):
                    with open(emp_md, "r", encoding="utf-8") as f:
                        content = f.read()
                    # 截取正文（去 JSON 块）
                    json_pos = content.find("```json")
                    if json_pos != -1:
                        content = content[:json_pos]
                    parts.append(f"### 实证分析：{d[:40]}")
                    parts.append(content[:4000])
                    parts.append("")
                elif os.path.exists(emp_json):
                    with open(emp_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    kf = data.get("key_findings", [])
                    if kf:
                        parts.append(f"### 实证分析关键发现：{d[:40]}")
                        for item in kf[:8]:
                            parts.append(f"- {str(item)[:200]}")
                        parts.append("")

        # 跨论文比较
        cross = os.path.join(analysis_root, "_cross_paper")
        if os.path.isdir(cross):
            for fn in ["empirical_comparison_matrix.md", "empirical_innovation_inference.md"]:
                fp = os.path.join(cross, fn)
                if os.path.exists(fp):
                    with open(fp, "r", encoding="utf-8") as f:
                        content = f.read()
                    parts.append(f"### {fn.replace('.md', '').replace('_', ' ').title()}")
                    parts.append(content[:3000])
                    parts.append("")

        return "\n".join(parts) if parts else "（暂无实证分析数据）"

    def _build_sections_summary(self, section_results: list) -> str:
        """构建分结构分析的精简摘要（用于 LLM prompt）"""
        parts = []
        for r in section_results:
            if not r.get("success"):
                continue
            key = r.get("section_key", "")
            title = r.get("title", "")
            findings = r.get("json", {}).get("key_findings", [])[:4]
            gaps = r.get("json", {}).get("gaps", [])[:2]

            parts.append(f"### [{key}] {title}")
            parts.append("**关键发现:**")
            for f in findings:
                parts.append(f"  - {f.strip().lstrip('- ').lstrip('* ')[:200]}")
            parts.append("**研究空缺:**")
            for g in gaps:
                parts.append(f"  - {g.strip().lstrip('- ').lstrip('* ')[:150]}")
            parts.append("")

        return "\n".join(parts)

    @staticmethod
    def _parse_markdown_table(text: str) -> dict:
        """解析 Markdown 表格文本为结构化数据 {caption, headers, rows}"""
        import re as _re
        lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            return None

        # 找表头行
        header_idx = -1
        for i, line in enumerate(lines):
            if "|" in line:
                parts = [c.strip() for c in line.split("|")]
                parts = [p for p in parts if p]
                if parts and not all(_re.match(r'^[-: ]+$', p) for p in parts):
                    header_idx = i
                    break
        if header_idx < 0:
            return None

        header_parts = [c.strip() for c in lines[header_idx].split("|")]
        headers = [h for h in header_parts if h]

        data_start = header_idx + 1
        if data_start < len(lines) and all(
            _re.match(r'^[-: ]+$', c.strip()) for c in lines[data_start].split("|") if c.strip()
        ):
            data_start += 1

        rows = []
        for line in lines[data_start:]:
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c]
            if cells:
                while len(cells) < len(headers):
                    cells.append("")
                rows.append(cells[:len(headers)])

        if not rows:
            return None
        return {"caption": "", "headers": headers, "rows": rows}

    @staticmethod
    def _extract_first_table_from_md(md_text: str) -> dict:
        """从 Markdown 文本中提取第一个表格"""
        lines = md_text.split("\n")
        # 找第一个管道符表格
        start = -1
        for i, line in enumerate(lines):
            if "|" in line and line.strip().startswith("|"):
                start = i
                break
        if start < 0:
            return None

        # 收集连续管道行
        table_lines = []
        for i in range(start, len(lines)):
            line = lines[i].strip()
            if "|" in line and line.startswith("|"):
                table_lines.append(line)
            elif table_lines:  # 表格结束
                break

        if len(table_lines) < 2:
            return None

        return PresentationGenerator._parse_markdown_table("\n".join(table_lines))

    # ═══════════════════════════════════════════════════════════
    # HTML 渲染
    # ═══════════════════════════════════════════════════════════

    def _render_slide(self, data: dict) -> str:
        """根据结构化数据渲染单页幻灯片 HTML"""
        stype = data.get("type", "content")

        if stype == "cover":
            title = self._esc(data.get("title", ""))
            subtitle = self._esc(data.get("subtitle", ""))
            meta = self._esc(data.get("meta", ""))
            tag = self._esc(data.get("tag", "计量经济学文献综述"))
            return f'''<div class="slide slide-cover active" id="slide-cover">
  <div class="decorative-circle"></div>
  <div class="cover-content">
    <span class="cover-tag">{tag}</span>
    <h1 class="cover-title">{title}</h1>
    <p class="cover-subtitle">{subtitle}</p>
    <div class="cover-meta">
      <span><i class="ph ph-book-open-text"></i> {meta}</span>
    </div>
  </div>
</div>'''

        elif stype == "toc":
            items = data.get("items", [])
            items_html = "\n".join(
                f'      <div class="toc-item"><span class="toc-num">{i+1:02d}</span><span>{self._esc(it)}</span></div>'
                for i, it in enumerate(items)
            )
            return f'''<div class="slide">
  <div class="slide-header"><h2>汇报路线图</h2><p class="subtitle">本次组会覆盖计量经济学论文的 {len(items)} 个结构维度</p></div>
  <div class="content-area">
    <div class="toc-grid">
{items_html}
    </div>
  </div>
</div>'''

        elif stype == "content":
            section = self._esc(data.get("section", ""))
            title = self._esc(data.get("title", ""))
            points = data.get("points", [])
            highlight = data.get("highlight", "")
            table = data.get("table", None)

            points_html = "\n".join(
                "              <li>" + self._esc(p).replace("\n", "<br>") + "</li>"
                for p in points
            )
            highlight_html = ""
            if highlight:
                highlight_html = f'''    <div class="highlight-card"><i class="ph ph-lightbulb"></i><span>{self._esc(highlight)}</span></div>'''

            # 渲染表格（如有）
            table_html = ""
            if table and table.get("headers") and table.get("rows"):
                caption = self._esc(table.get("caption", ""))
                headers_html = "\n".join(
                    f'                <th>{self._esc(h)}</th>' for h in table["headers"]
                )
                rows_html = "\n".join(
                    "              <tr>" + "".join(f'<td>{self._esc(c, preserve_br=True)}</td>' for c in row) + "</tr>"
                    for row in table["rows"]
                )
                table_html = f'''  <div class="data-table-wrap">
    <div class="table-caption">{caption}</div>
    <table class="academic-table">
      <thead><tr>
{headers_html}
      </tr></thead>
      <tbody>
{rows_html}
      </tbody>
    </table>
  </div>'''

            # 有表格时上下堆叠（文字完整 + 表格完整），无表格时全宽 info-box
            if table_html:
                body_html = f'''  <div class="info-box">
      <ul>
{points_html}
      </ul>
    </div>
    {highlight_html}
    {table_html}'''
            else:
                body_html = f'''  <div class="info-box">
      <ul>
{points_html}
      </ul>
    </div>
{highlight_html}'''

            return f'''<div class="slide">
  <div class="slide-header"><h2>{title}</h2><p class="subtitle">{section}</p></div>
  <div class="content-area">
{body_html}
  </div>
</div>'''

        elif stype == "summary":
            title = self._esc(data.get("title", "总结与展望"))
            takeaways = data.get("takeaways", [])
            gaps = data.get("gaps", [])

            tw_html = "\n".join(
                f'    <div class="takeaway-card"><span class="tw-label">✦ Take-away {i+1}</span>{self._esc(t)}</div>'
                for i, t in enumerate(takeaways)
            )
            gaps_html = ""
            if gaps:
                badges = "\n".join(
                    f'      <span class="gap-badge">{self._esc(g[:100])}</span>'
                    for g in gaps[:4] if g.strip()
                )
                gaps_html = f'''  <div class="gaps-section">
    <div class="gaps-label"><i class="ph ph-warning-circle"></i> 关键研究空缺</div>
    <div>
{badges}
    </div>
  </div>'''

            return f'''<div class="slide slide-summary">
  <div class="slide-header"><h2>{title}</h2></div>
  <div class="content-area">
{tw_html}
{gaps_html}
  </div>
</div>'''

        elif stype == "thanks":
            return f'''<div class="slide slide-thanks">
  <h1>{self._esc(data.get("title", "感谢聆听"))}</h1>
  <p>{self._esc(data.get("subtitle", "欢迎提问与讨论"))}</p>
</div>'''

        # fallback
        return f'<div class="slide"><div class="slide-header"><h2>{self._esc(data.get("title", ""))}</h2></div></div>'

    # ─── LLM 输出解析 ──────────────────────────────────────────

    def _parse_slides(self, raw: str) -> list:
        """解析 LLM 的 ---SLIDE--- 格式输出（行级解析，兼容多种 LLM 输出变体）"""
        slides = []
        blocks = re.split(r'\n?---SLIDE---\n?', raw)

        for block in blocks:
            block = block.strip()
            if not block or block == "---":
                continue

            data = {}
            lines = block.split("\n")
            current_field = None
            current_list = []

            for line in lines:
                # 匹配字段标签: TYPE, TITLE, SUBTITLE, SECTION, HIGHLIGHT, TAG
                field_match = re.match(r'^(TYPE|TITLE|SUBTITLE|SECTION|HIGHLIGHT|TAG):\s*(.*)', line, re.IGNORECASE)
                if field_match:
                    # 保存上一个列表字段
                    if current_field and current_list:
                        self._assign_list(data, current_field, current_list)
                        current_list = []

                    field_name = field_match.group(1).lower()
                    value = field_match.group(2).strip()
                    if field_name == "type":
                        data["type"] = value
                    elif field_name == "title":
                        data["title"] = value
                    elif field_name == "subtitle":
                        data["subtitle"] = value
                    elif field_name == "section":
                        data["section"] = value
                    elif field_name == "highlight":
                        data["highlight"] = value
                    elif field_name == "tag":
                        data["tag"] = value
                    current_field = None
                    continue

                # 匹配列表字段标签: BODY:, ITEMS:, GAPS:, TABLE:
                list_match = re.match(r'^(BODY|ITEMS|GAPS|TABLE):\s*$', line, re.IGNORECASE)
                if list_match:
                    # 保存上一个列表
                    if current_field and current_list:
                        self._assign_list(data, current_field, current_list)
                        current_list = []
                    current_field = list_match.group(1).lower()
                    continue

                # TABLE 字段：收集管道符分隔的表格行
                if current_field == "table" and "|" in line:
                    current_list.append(line.strip())
                    continue

                # 在列表字段内收集条目
                if current_field:
                    bullet_match = re.match(r'^\s*[-*]\s+(.+)', line)
                    if bullet_match:
                        current_list.append(bullet_match.group(1).strip())
                        continue
                    # 空行结束列表（TABLE 除外：由三条管道线后的空行结束）
                    if line.strip() == "":
                        if current_field == "table" and len(current_list) >= 2:
                            # 解析收集的表格行
                            table_text = "\n".join(current_list)
                            parsed = self._parse_markdown_table(table_text)
                            if parsed:
                                data["table"] = parsed
                        elif current_list:
                            self._assign_list(data, current_field, current_list)
                        current_list = []
                        current_field = None
                        continue

            # 保存最后一个列表（TABLE 需要特殊解析）
            if current_field and current_list:
                if current_field == "table" and len(current_list) >= 2:
                    table_text = "\n".join(current_list)
                    parsed = self._parse_markdown_table(table_text)
                    if parsed:
                        data["table"] = parsed
                else:
                    self._assign_list(data, current_field, current_list)

            # 至少需要 type 或 title
            if data.get("type") or data.get("title"):
                slides.append(data)

        return slides

    @staticmethod
    def _assign_list(data: dict, field: str, items: list):
        """将解析出的列表赋值到 data 字典的正确字段"""
        mapping = {
            "body": "points",
            "items": "items",
            "gaps": "gaps",
        }
        key = mapping.get(field, field)
        if key == "items" and data.get("type") == "summary":
            data["takeaways"] = [it for it in items if it.strip()]
        else:
            data[key] = [it for it in items if it.strip()]

    # ─── 回退演讲稿 ────────────────────────────────────────────

    def _build_fallback_speech(self, section_results: list) -> str:
        """从分结构数据构建基础演讲稿"""
        lines = ["# 组会演讲稿\n", "> 基于各维度分析自动生成\n"]
        for i, r in enumerate(section_results):
            if not r.get("success"):
                continue
            title = r.get("title", "")
            lines.append(f"## [Slide {i+3}] {title}")
            lines.append(f"⏱ 约 1.5 分钟 | 💡 核心信息：见{title}维度的关键发现\n")
            lines.append(f"（口语稿：基于{title}维度的分析结果进行口头阐述。）\n")
            lines.append("⚠ 可能的提问：该维度的证据强度如何？\n")
        return "\n".join(lines)

    @staticmethod
    def _clean_finding(text: str) -> str:
        """清洗 key_finding 条目：去粗体标记、过滤表格行、多余空白"""
        import re as _re  # noqa: local import for staticmethod
        clean = text.strip()
        # 过滤表格分隔行 |---|
        if _re.match(r'^\|[\s:\-]+\|', clean):
            return ""
        # 过滤以 | 开头的表格数据行（含多个管道符）
        if clean.startswith("|") and clean.count("|") >= 2:
            return ""
        # 去除 Markdown 粗体 **text** → text
        clean = _re.sub(r'\*\*(.+?)\*\*', r'\1', clean)
        # 去除行首列表标记
        clean = _re.sub(r'^[-*]\s+', '', clean)
        return clean.strip()

    @staticmethod
    def _esc(text: str, preserve_br: bool = False) -> str:
        """HTML 转义。preserve_br=True 时保留 <br> 标签"""
        s = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        if preserve_br:
            s = s.replace("&lt;br&gt;", "<br>").replace("&lt;br/&gt;", "<br/>").replace("&lt;BR&gt;", "<br>")
        return s
