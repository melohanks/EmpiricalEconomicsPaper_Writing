"""
CLI 入口：标准化计量模型代码库调用

用法：
  # 列出所有可用模型
  python scripts/run_regression.py --list

  # 运行基准 FE 模型
  python scripts/run_regression.py --model panel_fe --data workspace/data/sample.csv \\
      --y Chain --x PCapital --controls Age,ROA,FA --entity firm_id --time year

  # 运行 Sharp RDD
  python scripts/run_regression.py --model sharp_rdd --data workspace/data/sample.csv \\
      --y Chain --running firm_age --cutoff 5.0

  # 运行 Staggered DID
  python scripts/run_regression.py --model staggered_did --data workspace/data/sample.csv \\
      --y Chain --treat treated --time year --first-treat first_treat_year --entity firm_id

  # 运行 IV-2SLS
  python scripts/run_regression.py --model iv_2sls --data workspace/data/sample.csv \\
      --y Chain --x PCapital --iv iv_mean_peers --controls Age,ROA

  # 运行中介效应
  python scripts/run_regression.py --model mediation --data workspace/data/sample.csv \\
      --y Chain --x PCapital --mediators RSI,Slack --controls Age,ROA

  # 运行异质性
  python scripts/run_regression.py --model heterogeneity --data workspace/data/sample.csv \\
      --y Chain --x PCapital --group ownership --mode group

  # 运行诊断
  python scripts/run_regression.py --model diagnostics --data workspace/data/sample.csv \\
      --type mccrary --running firm_age --cutoff 5.0

  # 批量运行（从蓝图文件读取）
  python scripts/run_regression.py --blueprint workspace/writing/paper_blueprint.md \\
      --data workspace/data/sample.csv
"""
import os
import sys
import argparse
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from regression_lib import run_model, list_models, BLUEPRINT_TO_MODELS


def main():
    parser = argparse.ArgumentParser(
        description="标准化计量模型代码库 — 一键运行回归分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_regression.py --model panel_fe --data data.csv --y Chain --x PCapital --entity firm_id --time year
  python run_regression.py --model sharp_rdd --data data.csv --y Chain --running firm_age --cutoff 5.0
  python run_regression.py --list
        """
    )

    # 模型选择
    parser.add_argument("--model", type=str, help="模型名 (panel_fe/sharp_rdd/staggered_did/iv_2sls/mediation/heterogeneity/robustness/diagnostics)")
    parser.add_argument("--list", action="store_true", help="列出所有可用模型")
    parser.add_argument("--blueprint", type=str, help="论文蓝图文件路径（自动解析模型→批量运行）")

    # 通用参数
    parser.add_argument("--data", type=str, default="workspace/data/sample.csv", help="数据文件路径")

    # 变量
    parser.add_argument("--y", type=str, help="被解释变量")
    parser.add_argument("--x", type=str, help="核心解释变量（逗号分隔多个）")
    parser.add_argument("--controls", type=str, default="", help="控制变量（逗号分隔）")
    parser.add_argument("--mediators", type=str, default="", help="中介变量（逗号分隔）")
    parser.add_argument("--iv", type=str, default="", help="工具变量（逗号分隔）")
    parser.add_argument("--group", type=str, help="分组变量")
    parser.add_argument("--interact", type=str, help="交互变量")

    # 面板/DID/RDD 专用
    parser.add_argument("--entity", type=str, default="firm_id", help="个体标识列")
    parser.add_argument("--time", type=str, default="year", help="时间列")
    parser.add_argument("--treat", type=str, default="treated", help="处理组标识列")
    parser.add_argument("--first-treat", type=str, default="first_treat", help="首次处理年份列")
    parser.add_argument("--running", type=str, help="RDD驱动变量")
    parser.add_argument("--cutoff", type=float, default=0.0, help="RDD断点值")

    # 选项
    parser.add_argument("--mode", type=str, default="group", help="异质性模式 (group/interaction/both)")
    parser.add_argument("--type", type=str, default="all", help="诊断类型 (mccrary/parallel_trends/placebo/vif/all)")
    parser.add_argument("--bootstrap", type=int, default=1000, help="Bootstrap 次数 (中介效应)")
    parser.add_argument("--exclude", type=str, help="稳健性排除条件")
    parser.add_argument("--y-alt", type=str, help="备选Y测度 (稳健性)")
    parser.add_argument("--x-alt", type=str, help="备选X测度 (稳健性)")
    parser.add_argument("--cluster", type=str, help="聚类标准误列")
    parser.add_argument("--output-dir", type=str, help="输出目录")

    args = parser.parse_args()

    # ── 列表模式 ──
    if args.list:
        print("可用模型:")
        for name in list_models():
            print(f"  {name}")
        print("\n蓝图→模型映射:")
        for k, v in BLUEPRINT_TO_MODELS.items():
            print(f"  {k} → {v}")
        return

    # ── 蓝图模式：自动解析 → 批量运行 ──
    if args.blueprint:
        if not os.path.exists(args.blueprint):
            print(f"蓝图文件不存在: {args.blueprint}")
            sys.exit(1)
        _run_from_blueprint(args)
        return

    # ── 单模型模式 ──
    if not args.model:
        print("请指定 --model 或 --blueprint。使用 --list 查看可用模型。")
        sys.exit(1)

    kwargs = _build_kwargs(args)
    result = run_model(args.model, data_path=args.data, **kwargs)

    if result.get("success"):
        print(result.get("summary", "OK"))
        print(f"\n输出文件: {result.get('path', 'N/A')}")
    else:
        print(f"失败: {result.get('summary', result.get('error', 'Unknown'))}")
        sys.exit(1)


def _build_kwargs(args):
    """根据 CLI 参数构建模型 kwargs"""
    kwargs = {}

    if args.y:
        kwargs["y_var"] = args.y
        kwargs["x_vars"] = [s.strip() for s in args.x.split(",") if s.strip()] if args.x else []
    if args.controls:
        kwargs["controls"] = [s.strip() for s in args.controls.split(",") if s.strip()]
    if args.mediators:
        kwargs["mediators"] = [s.strip() for s in args.mediators.split(",") if s.strip()]
    if args.iv:
        kwargs["iv_vars"] = [s.strip() for s in args.iv.split(",") if s.strip()]

    # 专用参数
    if args.running:
        kwargs["running_var"] = args.running
    if args.cutoff != 0.0 or args.running:
        kwargs["cutoff"] = args.cutoff
    if args.entity:
        kwargs["entity_col"] = args.entity
    if args.time:
        kwargs["time_col"] = args.time
    if args.treat:
        kwargs["treat_col"] = args.treat
    if args.first_treat:
        kwargs["first_treat_col"] = args.first_treat
    if args.group:
        kwargs["group_var"] = args.group
    if args.interact:
        kwargs["interact_var"] = args.interact
    if args.cluster:
        kwargs["cluster_col"] = args.cluster

    # 选项
    if args.mode:
        kwargs["mode"] = args.mode
    if args.type:
        kwargs["diagnostic_type"] = args.type
    if args.bootstrap:
        kwargs["bootstrap"] = args.bootstrap
    if args.exclude:
        kwargs["exclude_condition"] = args.exclude
    if args.y_alt:
        kwargs["y_alt"] = args.y_alt
    if args.x_alt:
        kwargs["x_alt"] = args.x_alt

    return kwargs


def _run_from_blueprint(args):
    """从论文蓝图自动解析模型并批量运行"""
    with open(args.blueprint, "r", encoding="utf-8") as f:
        blueprint = f.read()

    # 简单解析：从蓝图中提取变量名和模型类型
    import re

    # 提取 Y
    y_match = re.search(r'被解释变量.*?[（(](\w+)[）)]|Y[：:]\s*(\w+)', blueprint)
    y_var = y_match.group(1) or y_match.group(2) if y_match else "Chain"

    # 提取 X
    x_match = re.search(r'核心解释变量.*?[（(](\w+)[）)]|X[：:]\s*(\w+)', blueprint)
    x_vars = [(x_match.group(1) or x_match.group(2))] if x_match else ["PCapital"]

    # 确定核心模型
    if "RDD" in blueprint or "断点" in blueprint:
        core_model = "sharp_rdd"
    elif "DID" in blueprint or "双重差分" in blueprint:
        core_model = "staggered_did"
    else:
        core_model = "panel_fe"

    print(f"[蓝图解析] Y={y_var}, X={x_vars}, 核心模型={core_model}")
    print(f"[蓝图解析] 将按以下顺序运行:")
    print(f"  1. {core_model} (主效应)")
    print(f"  2. mediation (机制)")
    print(f"  3. heterogeneity (异质性)")
    print(f"  4. robustness (稳健性)")
    print(f"  5. diagnostics (诊断)")
    print()

    models_to_run = [core_model, "mediation", "heterogeneity", "robustness", "diagnostics"]
    for name in models_to_run:
        print(f"\n{'='*60}")
        print(f"运行: {name}")
        print(f"{'='*60}")
        try:
            kwargs = {"y_var": y_var, "x_vars": x_vars}
            if args.controls:
                kwargs["controls"] = [s.strip() for s in args.controls.split(",")]
            result = run_model(name, data_path=args.data, **kwargs)
            if result.get("success"):
                print(result.get("summary", "OK")[:500])
                print(f"→ {result.get('path', 'N/A')}")
            else:
                print(f"✗ {result.get('summary', 'Error')[:200]}")
        except Exception as e:
            print(f"✗ {name} 执行异常: {e}")


if __name__ == "__main__":
    main()
