import os
import sys
import argparse

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import ResearchAgent


def main():
    parser = argparse.ArgumentParser(
        description="第一阶段：从本地目录导入论文元数据"
    )
    parser.add_argument(
        "--papers-dir",
        type=str,
        default="workspace/papers",
        help="论文元数据文件所在目录（默认 workspace/papers）",
    )
    args = parser.parse_args()

    agent = ResearchAgent()
    success = agent.collect_literature(papers_dir=args.papers_dir)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
