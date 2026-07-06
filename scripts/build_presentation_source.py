"""Build comprehensive presentation source from all 5 materials."""
import json, os

lines = []

lines.append('# 组会汇报：异质性资本与关键核心技术创新——基于两篇前沿文献的对比分析')
lines.append('')
lines.append('> 论文 1: 吴超鹏, 严泽浩 (2023). 政府基金引导与企业核心技术突破：机制与效应. 经济研究.')
lines.append('> 论文 2: 胡海峰, 林丽瑾, 窦斌 (2025). 耐心资本对关键核心技术企业创新的影响效果和作用机制. 财贸经济.')
lines.append('')
lines.append('---')
lines.append('')

# === 板块一：共同开场 ===
lines.append('## 板块一：共同开场')
lines.append('')
lines.append('### 研究背景与核心问题')
lines.append('')
lines.append('- 国际科技博弈加剧，关键核心技术突破成为国家经济安全战略核心')
lines.append('- 传统风投因短视化与业绩压力，难以独立支撑高风险、长周期的基础性颠覆性创新')
lines.append('- 两类"非传统"资本进入视野：政府引导基金（有为政府+有效市场）vs 耐心资本（长期主义+价值投资）')
lines.append('- 核心追问：不同资本形态是否真正促进了关键核心技术创新？其差异化机制是什么？')
lines.append('')
lines.append('### 文献定位与两篇论文的切入')
lines.append('')
lines.append('- 已有研究局限：将VC视为同质金融资本，忽视不同类型VC的根本差异')
lines.append('- 论文1（吴超鹏&严泽浩）：政府引导基金→风险分担者→失败容忍度机制→靶向关键核心技术')
lines.append('- 论文2（胡海峰等）：耐心资本→功能补充者→融资+人才+供应链三维赋能→制度环境调节')
lines.append('- 互补关系：前者改变风险-收益分布，后者优化要素配置')
lines.append('')
lines.append('---')
lines.append('')

# === 板块二：论文1 ===
lines.append('## 板块二：论文1——政府基金引导与企业核心技术突破（吴超鹏 & 严泽浩, 2023, 经济研究）')
lines.append('')

# Find paper dirs
base = 'workspace/analysis'
dirs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)) and not d.startswith('_')]
paper1_dir = [d for d in dirs if '政府基金' in d][0]
paper2_dir = [d for d in dirs if '耐心资本对关键核心' in d][0]

emp1 = json.load(open(os.path.join(base, paper1_dir, 'empirical.json'), 'r', encoding='utf-8'))

lines.append('### 理论框架')
lines.append('- 政府战略引导的"风险分担"理论：政府作为市场无法胜任的风险吸收者')
lines.append('- 内嵌"失败容忍度"激励机制，与私人风投的财务回报最大化目标函数根本不同')
lines.append('- 可检验假说：效应集中于高风险的关键核心技术领域，非关键领域应消失')
lines.append('')

lines.append('### 研究假设')
lines.append('- H1: 政府引导基金对企业关键核心技术创新有正向影响')
lines.append('- H2: 通过"提升失败容忍度"机制传导')
lines.append('- H3: 通过"缓解融资约束"机制传导（发挥资金引导作用）')
lines.append('- 异质性：效应靶向关键核心技术领域，非关键领域无效')
lines.append('')

lines.append('### 识别策略')
lines.append('- 核心策略：PSM-DID（倾向得分匹配-双重差分法）')
lines.append('- 处理组：引入政府引导基金型风投的企业；对照组：引入其他风投机构投资的企业')
lines.append('- 比较维度：融资前 vs 融资后的关键核心技术领域创新绩效变化')
lines.append('- 识别挑战：自选择偏误——政府基金可能筛选了本身创新能力强的企业')
lines.append('')

lines.append('### 数据与变量')
lines.append('- 数据：2011-2022年中国A股上市公司 + 专利数据库')
lines.append('- 被解释变量Y：关键核心技术领域创新绩效的多维质量指标体系（发明专利+高被引+新技术+独创性）')
lines.append('- 核心解释变量X：政府引导基金投资（GVC虚拟变量）')
lines.append('- 中介变量：失败容忍度、外部融资约束')
lines.append('')

lines.append('### 基准计量模型')
lines.append('- 模型类型：多期双重差分模型（Staggered DID）+ 企业固定效应面板回归')
lines.append('- 回归方程：Innovation_it = beta(Treat_i x Post_it) + gamma Controls_it + alpha_i + lambda_t + epsilon_it')
lines.append('- alpha_i为企业固定效应，lambda_t为年份固定效应，beta为核心关心系数')
lines.append('')

lines.append('### 基准回归结果')
lines.append('- 核心交乘项 GVC x Post 系数为 0.0429，在1%水平上显著')
lines.append('- 经济显著性：关键核心技术专利基数小（样本均值仅0.12项），但4.29%的年度增幅差异意味着精准、可观的边际激励效果')
lines.append('- 专利数量、质量、高被引、新技术、独创性均有"较大幅度提升"')
lines.append('')

lines.append('### 机制检验')
lines.append('- 渠道一：提升失败容忍度——政府引导基金提升对企业创新失败风险的容忍度→激励高风险核心技术突破')
lines.append('- 渠道二：缓解融资约束——发挥资金引导作用，撬动更多社会资本→缓解企业外部融资压力')
lines.append('- 两条渠道均显著，失败容忍度渠道最具理论增量')
lines.append('')

lines.append('### 异质性分析')
lines.append('- 关键核心技术领域：效应显著——专利数量、质量、影响力、独创性系统性提升')
lines.append('- 非关键核心技术领域：无显著提升——"开关式"效应，精准靶向')
lines.append('- 有力佐证"失败容忍度"机制叙事，暗示该政策工具不具有普惠性')
lines.append('')

lines.append('### 稳健性检验与内生性处理')
lines.append('- 替换被解释变量测度、替换核心解释变量、替换计量方法、排除替代性解释')
lines.append('- PSM-DID设定本身即为核心内生性处理手段，需关注平行趋势检验等诊断信息')
lines.append('')

lines.append('---')
lines.append('')

# === 板块二：论文2 ===
lines.append('## 板块二：论文2——耐心资本对关键核心技术企业创新的影响（胡海峰 等, 2025, 财贸经济）')
lines.append('')

emp2 = json.load(open(os.path.join(base, paper2_dir, 'empirical.json'), 'r', encoding='utf-8'))

lines.append('### 理论框架')
lines.append('- 市场增进的"功能补充"理论：耐心资本的长期性和价值投资属性提供稳定资源支持')
lines.append('- 扮演市场功能的补充与增强角色（非风险分担者）')
lines.append('- 可检验假说：耐心资本通过融资、人才、供应链三维同步缓解约束→促进创新')
lines.append('- 效应受制度环境正向调节（市场竞争、法治、数字基建越好→效应越强）')
lines.append('')

lines.append('### 研究假设')
lines.append('- H1: 耐心资本对关键核心技术企业创新能力有正向影响')
lines.append('- H2a-H2c: 通过缓解融资约束、提升人力资本水平、增强供应链稳定性促进创新')
lines.append('- H3a-H3c: 地区市场竞争环境、法治环境、数字经济发展水平正向调节上述效应')
lines.append('')

lines.append('### 识别策略')
lines.append('- 核心策略：面板数据固定效应模型 + 交互项异质性分析')
lines.append('- 构建了反映耐心资本投资水平的连续型衡量指标（PC_Share1, PC_Share2）')
lines.append('- 识别挑战：反向因果、自选择偏误、遗漏变量')
lines.append('')

lines.append('### 数据与变量')
lines.append('- 数据：关键核心技术企业样本')
lines.append('- 被解释变量Y：创新能力——专利规模、专利质量、自主创新程度、知识宽度')
lines.append('- 核心解释变量X：耐心资本投资水平（PC_Share1, PC_Share2，均值仅0.5%-0.6%）')
lines.append('- 中介变量：融资约束、人力资本水平、供应链稳定性')
lines.append('- 调节变量：地区市场竞争环境、法治环境、数字经济发展水平')
lines.append('')

lines.append('### 基准计量模型')
lines.append('- 模型类型：面板数据双向固定效应模型')
lines.append('- 基准方程：Innovation_it = beta_PC_Share + gamma_Controls_it + mu_i + lambda_t + epsilon_it')
lines.append('- PC_Share一个标准差（0.011）的增加约提升企业创新1.4%-6.0%')
lines.append('')

lines.append('### 基准回归结果')
lines.append('- PC_Share1和PC_Share2的估计系数在所有创新维度下均显著为正（至少5%水平）')
lines.append('- 经济显著性突出：耐心资本持股均值极低（0.5%-0.6%），但边际创新促进效应非常可观')
lines.append('- 即使少量耐心资本的进入，也能对企业创新产生实质性拉动作用')
lines.append('')

lines.append('### 机制检验')
lines.append('- 渠道一：缓解融资约束→为企业长周期研发提供稳定资金')
lines.append('- 渠道二：提升人力资本水平→吸引和保留高端技术人才')
lines.append('- 渠道三：增强供应链稳定性→保障核心技术创新所需的产业链协同')
lines.append('- 三条渠道均显著，构成"融资-人才-供应链"三维赋能框架')
lines.append('')

lines.append('### 异质性分析')
lines.append('- 地区市场竞争环境越好→耐心资本效应越强')
lines.append('- 法治环境越完善→耐心资本效应越强')
lines.append('- 数字经济发展水平越高→耐心资本效应越强')
lines.append('- 核心含义：耐心资本与优越制度环境是互补关系，非替代关系')
lines.append('')

lines.append('### 稳健性检验与内生性处理')
lines.append('- 替换被解释变量和核心解释变量的测度方式、变更样本区间')
lines.append('- 内生性处理的具体方法和结果需查阅全文相关章节')
lines.append('')

lines.append('---')
lines.append('')

# === 板块三：跨论文对比 ===
lines.append('## 板块三：跨论文对比与总结')
lines.append('')

lines.append('### 实证方法横向对比矩阵')
lines.append('')
lines.append('| 维度 | 论文1 (吴超鹏) | 论文2 (胡海峰) |')
lines.append('|------|---------------|---------------|')
lines.append('| 理论逻辑 | 风险分担（政府介入） | 功能补充（市场增进） |')
lines.append('| 识别策略 | PSM-DID | 面板FE + 交互项 |')
lines.append('| 核心机制 | 失败容忍度 + 融资约束 | 融资 + 人力资本 + 供应链 |')
lines.append('| Y测度 | 多维专利质量指标 | 专利规模+质量+自主创新+知识宽度 |')
lines.append('| X测度 | GVC二元虚拟变量 | PC_Share连续型指标 |')
lines.append('| 异质性 | 领域靶向（关键 vs 非关键） | 制度互补（市场+法治+数字） |')
lines.append('| 共同短板 | 内生性处理不足、稳健性诊断信息缺失 | 同上 |')
lines.append('')

lines.append('### 共性模式与关键分歧')
lines.append('- 共性一：两类资本均与企业关键技术创新显著正相关——方向性一致')
lines.append('- 共性二：均超越"资本能否促进创新"的简单问答，致力于打开机制黑箱')
lines.append('- 共性三：识别策略均面临"可信度革命缺席"的挑战——重机制、轻识别')
lines.append('- 分歧一：机制逻辑互补——风险分担 vs 功能补充，非对立而是互补')
lines.append('- 分歧二：异质性逻辑不同——内部属性开关 vs 外部环境放大器')
lines.append('')

lines.append('### 集体方法论缺陷与创新空间')
lines.append('- 共同的识别挑战：自选择偏误未有效处理，因果推断可信度受限')
lines.append('- 共同的测度问题："失败容忍度""耐心""关键核心技术"缺乏公认操作化方案')
lines.append('- 共同的理论局限：均未构建形式化微观理论模型')
lines.append('- 创新空间一：寻找准自然实验（基金设立批次、政策试点扩张）做更干净的因果推断')
lines.append('- 创新空间二：构建动态生命周期评估框架——从单期静态到全过程分析')
lines.append('- 创新空间三：制度细节嵌入——形式化基金契约设计的激励效果')
lines.append('')

lines.append('### 综合结论与政策启示')
lines.append('- 结论一：异质性资本确实与关键技术创新正相关，但距"可信因果推断"还有显著距离')
lines.append('- 结论二：两类资本逻辑互补——政府"风险分担"+市场"功能补充"')
lines.append('- 结论三：制度环境是效能放大器——耐心资本需与优越制度协同推进')
lines.append('- 政策启示：政府引导基金向CVC倾斜、差异化施策匹配资本类型、方法论升级')
lines.append('')

lines.append('### 研究局限与未来方向')
lines.append('- 局限一：仅用上市公司数据→幸存者偏差，可能高估资本的正向效应')
lines.append('- 局限二：自选择问题未完全解决——筛选效应 vs 培育效应不可区分')
lines.append('- 局限三：核心变量测度效度存疑')
lines.append('- 未来方向：韧性多维指标重构、动态生命周期视角、跨文化比较')
lines.append('')

lines.append('---')
lines.append('')
lines.append('## 总结')
lines.append('')
lines.append('- 发现1：政府引导基金和耐心资本均与关键技术创新正相关（GVCxPost系数0.0429***；PC_Share显著为正）')
lines.append('- 发现2：两类资本通过差异化机制发挥作用——失败容忍度+融资约束 vs 融资+人才+供应链')
lines.append('- 发现3：效应依赖边界条件——领域靶向 + 制度互补')
lines.append('- 贡献：从资本异质性视角推进了"金融-创新"因果识别前沿')
lines.append('- 启示：培育多层次耐心资本市场，差异化施策，制度与资本需协同推进')

with open('workspace/presentation_source.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'Source file: {os.path.getsize("workspace/presentation_source.md"):,} bytes')
