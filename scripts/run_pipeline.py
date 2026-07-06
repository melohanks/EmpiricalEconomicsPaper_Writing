import os
import sys
import argparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import ResearchAgent


def main():
    parser = argparse.ArgumentParser(
        description="全流程学术论文写作流水线 (本地导入 + 逐结构分析 + 演示材料)"
    )
    parser.add_argument(
        "--papers-dir",
        type=str,
        default="workspace/papers",
        help="论文元数据文件所在目录（默认 workspace/papers）",
    )
    parser.add_argument(
        "--backend",
        choices=["anthropic", "openai"],
        default=None,
        help="LLM 后端选择",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="模型名",
    )
    parser.add_argument(
        "--sections", type=str, default=None,
        help="指定分析的结构编号，逗号分隔，如 '1,6,11'。默认分析全部 11 个维度",
    )
    parser.add_argument(
        "--skip-presentation", action="store_true",
        help="跳过演示材料生成",
    )
    args = parser.parse_args()

    agent = ResearchAgent()
    success = agent.run_pipeline(
        papers_dir=args.papers_dir,
        backend=args.backend,
        model=args.model,
        sections=args.sections,
        skip_presentation=args.skip_presentation,
    )
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
