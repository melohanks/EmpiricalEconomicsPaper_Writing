import os
import sys
import argparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import ResearchAgent


def main():
    parser = argparse.ArgumentParser(
        description="第二阶段：计量经济学文献综述逐结构分析"
    )
    parser.add_argument(
        "--backend",
        choices=["anthropic", "openai"],
        default=None,
        help="LLM 后端选择 (默认读取环境变量 LLM_BACKEND，其次为 openai)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="模型名 (anthropic 默认 claude-sonnet-4-6；openai 默认读取 LLM_MODEL 环境变量)",
    )
    parser.add_argument(
        "--sections", type=str, default=None,
        help="指定分析的结构编号，逗号分隔，如 '1,6,11'。默认分析全部 11 个维度。"
             "可选: 1=introduction 2=theoretical 3=identification 4=data "
             "5=methodology 6=baseline 7=robustness 8=mechanism "
             "9=heterogeneity 10=endogeneity 11=conclusion",
    )
    parser.add_argument(
        "--skip-presentation", action="store_true",
        help="跳过演示材料生成（HTML 幻灯片 + 演讲稿）",
    )
    args = parser.parse_args()

    agent = ResearchAgent()
    success = agent.review_literature(
        backend=args.backend,
        model=args.model,
        sections=args.sections,
        skip_presentation=args.skip_presentation,
    )
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
