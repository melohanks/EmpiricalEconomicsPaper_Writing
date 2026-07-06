import os
import sys
import argparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import ResearchAgent


def main():
    parser = argparse.ArgumentParser(
        description="阶段三：经济学实证方法论深度分析"
    )
    parser.add_argument(
        "--backend",
        choices=["anthropic", "openai"],
        default=None,
        help="LLM 后端选择",
    )
    parser.add_argument("--model", type=str, default=None, help="模型名")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="进行多篇论文横向比较和创新空间推断",
    )
    args = parser.parse_args()

    agent = ResearchAgent()
    success = agent.empirical_analysis(
        backend=args.backend,
        model=args.model,
        compare=args.compare,
    )
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
