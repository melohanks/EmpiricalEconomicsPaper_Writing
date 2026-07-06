"""Generate remaining SVGs for the 28-page deck."""
import os

OUT = "projects/dual_paper_seminar_ppt169_20260621/svg_output"
os.makedirs(OUT, exist_ok=True)

# Common header/footer template
HDR = '''  <defs><linearGradient id="hdr" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#1A365D"/><stop offset="100%" stop-color="#2D6A8F"/></linearGradient></defs>
  <rect width="1280" height="720" fill="#F5F6F8"/>
  <rect x="0" y="0" width="1280" height="60" fill="url(#hdr)"/>'''

FTR = '''
  <line x1="60" y1="630" x2="1220" y2="630" stroke="#DFE6E9" stroke-width="1"/>
  <text x="640" y="656" text-anchor="middle" font-family="&quot;Microsoft YaHei&quot;, Arial, sans-serif" font-size="10" fill="#B2BEC3">SOURCE</text>
  <text x="1220" y="656" text-anchor="end" font-family="&quot;Microsoft YaHei&quot;, Arial, sans-serif" font-size="10" fill="#B2BEC3">PNUM</text>
</svg>'''

def card(y, w, h, color, title, lines):
    """Generate a card rect + text block"""
    r = f'  <rect x="60" y="{y}" width="{w}" height="{h}" rx="8" fill="#FFFFFF" stroke="{color}" stroke-width="1.5"/>\n'
    r += f'  <rect x="60" y="{y}" width="{w}" height="40" rx="8" fill="{color}"/>\n'
    r += f'  <rect x="60" y="{y+30}" width="{w}" height="10" fill="{color}"/>\n'
    r += f'  <text x="80" y="{y+28}" font-family="&quot;Microsoft YaHei&quot;, Arial, sans-serif" font-size="14" fill="#FFFFFF" font-weight="bold">{title}</text>\n'
    y0 = y + 58
    for line in lines:
        r += f'  <text x="80" y="{y0}" font-family="&quot;Microsoft YaHei&quot;, Arial, sans-serif" font-size="13" fill="#2D3436">{line}</text>\n'
        y0 += 24
    return r

def content_page(fname, pnum, title, source, body_content):
    """Generate a standard content page."""
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">\n{HDR}\n'
    svg += f'  <text x="60" y="40" font-family="Georgia, KaiTi, serif" font-size="24" fill="#FFFFFF">{title}</text>\n'
    svg += f'  <text x="1220" y="40" text-anchor="end" font-family="&quot;Microsoft YaHei&quot;, Arial, sans-serif" font-size="10" fill="#B2BEC3">{pnum}</text>\n'
    svg += body_content
    svg += FTR.replace('SOURCE', source).replace('PNUM', pnum)
    with open(os.path.join(OUT, fname), 'w', encoding='utf-8') as f:
        f.write(svg)

def chapter_page(fname, pnum, title, subtitle):
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <defs><linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#1A365D"/><stop offset="100%" stop-color="#0F2440"/></linearGradient></defs>
  <rect width="1280" height="720" fill="url(#bg)"/>
  <rect x="120" y="240" width="4" height="200" fill="#C8963E" rx="2"/>
  <text x="160" y="320" font-family="Georgia, KaiTi, serif" font-size="36" fill="#FFFFFF">{title}</text>
  <text x="160" y="380" font-family="&quot;Microsoft YaHei&quot;, Arial, sans-serif" font-size="20" fill="#C8963E">{subtitle}</text>
  <text x="1220" y="690" text-anchor="end" font-family="&quot;Microsoft YaHei&quot;, Arial, sans-serif" font-size="10" fill="#636E72">{pnum}</text>
</svg>'''
    with open(os.path.join(OUT, fname), 'w', encoding='utf-8') as f:
        f.write(svg)

# === Paper 1 remaining: P07-P12 ===
# P07: Identification
content_page('07_p1_identification.svg', '07',
    '论文1 · 识别策略：PSM-DID',
    '吴超鹏 &amp; 严泽浩 (2023)',
    card(90, 1160, 200, '#1A365D', 'PSM-DID 策略设定', [
        '核心策略：倾向得分匹配-双重差分法（PSM-DID）',
        '处理组：引入政府引导基金型风投的企业',
        '对照组：引入其他风投机构投资的企业',
        '比较维度：融资前 vs 融资后的关键核心技术领域创新绩效变化',
        '识别假设：条件独立假定——匹配后在可观测特征上处理组与对照组可比',
    ]) +
    card(320, 560, 130, '#C8963E', '识别挑战与可信度', [
        '自选择偏误：政府基金可能筛选了本身创新能力强的企业',
        '需平行趋势检验和安慰剂检验来验证DID有效性',
        '可信度层级：中等——PSM缓解了可观测选择，无法处理不可观测选择',
    ]) +
    card(320, 560, 130, '#2D6A8F', '补充策略', [
        '替换被解释变量和核心解释变量的测度方式',
        '替换计量方法、排除替代性解释',
    ],) if False else '')  # skip duplicate positioning
)

# Actually let me just write these more carefully. The batch approach is getting complex.
# Let me write each SVG directly.

print("Batch generation script ready. Generating individual files...")

# Close the script - we'll generate SVG files directly
