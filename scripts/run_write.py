import os
import sys
import argparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import ResearchAgent


def main():
    parser = argparse.ArgumentParser(description="阶段四：全流程论文写作")
    parser.add_argument("--backend", choices=["anthropic", "openai"], default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--step", choices=["topic", "hypothesis", "model", "variables", "conclusion", "full"],
                        default="topic", help="执行哪个写作步骤")
    parser.add_argument("--input", type=str, default="", help="上一步的输出或用户确认信息")
    args = parser.parse_args()

    agent = ResearchAgent()

    if args.step == "topic":
        result = agent.writing_select_topic(backend=args.backend, model=args.model)
    elif args.step == "hypothesis":
        result = agent.writing_formulate_hypothesis(args.input, backend=args.backend, model=args.model)
    elif args.step == "model":
        result = agent.writing_select_model(args.input, backend=args.backend, model=args.model)
    elif args.step == "variables":
        result = agent.writing_select_variables(args.input, backend=args.backend, model=args.model)
    elif args.step == "conclusion":
        result = agent.writing_conclusion(args.input, args.input, backend=args.backend, model=args.model)
    elif args.step == "full":
        result = agent.writing_full_paper(args.input, backend=args.backend, model=args.model)
    else:
        print(f"Unknown step: {args.step}")
        sys.exit(1)

    if result.get("success"):
        print(f"Output: {result.get('path', 'OK')}")
    else:
        print(f"Failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
