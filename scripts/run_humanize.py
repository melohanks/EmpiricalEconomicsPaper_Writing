"""
批量 humanizer-zh 去AI味处理脚本。
读取 workspace/analysis/ 和 workspace/literature_review.md，
对每份文本调用 LLM 去AI味后写回原文件。
"""
import os, sys, json, time

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills.llm_client import LlmClient

HUMANIZER_SYSTEM_PROMPT = """你是一位学术文本编辑。你的任务是对学术分析报告进行"去AI味"处理，使其读起来更像人类学者写的研究笔记。

## 需要修正的AI写作模式：

1. **删除开场白**：如"好的，请审阅以下..."、"以下是..."等机器人式开头。直接进入内容。
2. **减少粗体强调**：中文文本中过度使用 **粗体** 是AI的典型特征。只在必要时使用，大部分粗体改为普通文本。
3. **简化过度复杂的句式**：把"不仅...而且..."、"通过...从而..."等嵌套结构拆成更直接的表达。
4. **删除AI词汇**：删除或替换"至关重要"、"充当/作为/标志着"、"深入探讨"、"强调"（动词）、"彰显"、"展现了"、"凸显"等AI高频词。
5. **删除宣传性语言**：去掉"具有重要的现实意义"、"为...奠定了坚实基础"等空洞的宏大叙事。
6. **打破三段式**：AI倾向于用三个并列短语。改为两个或四个，或者拆成独立句子。
7. **减少破折号**：中文中过度使用破折号（——）是AI痕迹。改为逗号或句号。
8. **变化句子长度**：避免连续多个句子长度相近。穿插短句和长句。
9. **删除过度限定**：删掉"可能"、"或许"、"在一定程度上"等软化表达的堆砌。

## 必须保留的内容：

- 学术术语（DID、PSM、RDD、工具变量、中介效应等）
- 统计量、数字、百分比
- **表格格式完全不动**（Markdown表格保持原样）
- 文献引用标记（文献1、文献20等）
- 论文标题、作者名
- 整体结构和章节标题
- 中文引号内的内容

## 输出要求：

- 直接输出改写后的完整文本
- 不要加任何开头说明或结尾注释
- 不要改变 Markdown 格式（标题、列表、表格语法）"""


HUMANIZER_USER_PROMPT = """请对以下学术分析报告进行去AI味处理。保留所有学术术语、统计量、表格格式和文献引用标记不变。

---

{content}"""


def humanize_file(client: LlmClient, filepath: str, model: str) -> bool:
    """处理单个文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original = f.read()
    except Exception as e:
        print(f"  [ERROR] 读取失败: {e}")
        return False

    original_size = len(original)
    if original_size < 100:
        print(f"  [SKIP] 文件过小 ({original_size} bytes)")
        return True

    # 限制单次处理的长度（避免超出上下文）
    max_chars = 30000
    if original_size > max_chars:
        # 如果太长，分段处理
        print(f"  [WARN] 文件较大 ({original_size} chars)，将截取前 {max_chars} chars 处理")
        content = original[:max_chars]
        is_truncated = True
    else:
        content = original
        is_truncated = False

    prompt = HUMANIZER_USER_PROMPT.replace("{content}", content)

    try:
        result = client.execute(
            prompt=prompt,
            system_prompt=HUMANIZER_SYSTEM_PROMPT,
            backend="anthropic",
            model=model,
            max_tokens=8000
        )
    except Exception as e:
        print(f"  [ERROR] LLM调用失败: {e}")
        return False

    if not result or len(result) < 200:
        print(f"  [ERROR] 返回内容过短 ({len(result) if result else 0} chars)")
        return False

    # 如果原文被截断，拼接未处理的部分
    if is_truncated:
        result = result + "\n\n[以下为原始未处理内容]\n" + original[max_chars:]

    # 写回文件
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f"  [OK] {original_size} → {len(result)} chars")
        return True
    except Exception as e:
        print(f"  [ERROR] 写入失败: {e}")
        return False


def main():
    workspace = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")
    model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-pro")
    # 去除可能的 [1m] 后缀
    model = model.replace("[1m]", "").strip()

    client = LlmClient()

    # 收集需要处理的文件
    analysis_dir = os.path.join(workspace, "analysis")
    files = []

    if os.path.isdir(analysis_dir):
        for fname in sorted(os.listdir(analysis_dir)):
            if fname.endswith("_analysis.md"):
                files.append(os.path.join(analysis_dir, fname))

    lit_review = os.path.join(workspace, "literature_review.md")
    if os.path.exists(lit_review):
        files.append(lit_review)

    if not files:
        print("没有找到需要处理的文件")
        return

    print(f"共 {len(files)} 个文件待处理\n")

    success = 0
    for i, fpath in enumerate(files, 1):
        relpath = os.path.relpath(fpath, workspace)
        print(f"[{i}/{len(files)}] {relpath}")
        if humanize_file(client, fpath, model):
            success += 1
        # 请求间短暂间隔
        if i < len(files):
            time.sleep(0.5)

    print(f"\n完成: {success}/{len(files)} 个文件处理成功")


if __name__ == "__main__":
    main()
