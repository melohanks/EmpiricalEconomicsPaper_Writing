"""
Stata 实证分析桥接器：从论文蓝图生成 .do 文件，通过 Stata MCP 执行，回收结果

用法：
  # 从蓝图生成完整的 .do 文件
  python scripts/run_stata.py --blueprint workspace/writing/paper_blueprint.md --output workspace/regression/

  # 生成并列出需要运行的模型
  python scripts/run_stata.py --blueprint workspace/writing/paper_blueprint.md --dry-run

  # 运行单个模型
  python scripts/run_stata.py --data workspace/data/sample.dta --model panel_fe \
      --y Chain --x PCapital --controls "Age ROA" --entity firm_id --time year
"""
import os
import sys
import json
import re
import argparse
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

STATA_LIB = os.path.join(os.path.dirname(__file__), "stata_lib")

# 蓝图关键词 → Stata 模型映射
BLUEPRINT_TO_STATA = {
    "面板固定效应": "panel_fe",
    "双向固定": "panel_fe",
    "FE": "panel_fe",
    "RDD": "sharp_rdd",
    "断点": "sharp_rdd",
    "DID": "staggered_did",
    "双重差分": "staggered_did",
    "事件研究": "staggered_did",
    "Event Study": "staggered_did",
    "IV": "iv_2sls",
    "工具变量": "iv_2sls",
    "2SLS": "iv_2sls",
    "中介": "mediation",
    "机制检验": "mediation",
    "三步法": "mediation",
    "异质性": "heterogeneity",
    "分组回归": "heterogeneity",
    "交互项": "heterogeneity",
    "稳健性": "robustness",
    "缩尾": "robustness",
    "替换变量": "robustness",
    "诊断": "diagnostics",
    "VIF": "diagnostics",
    "共线性": "diagnostics",
}


def parse_blueprint(blueprint_path: str) -> dict:
    """从论文蓝图解析模型和变量规格"""
    if not os.path.exists(blueprint_path):
        return {}

    with open(blueprint_path, "r", encoding="utf-8") as f:
        content = f.read()

    spec = {
        "title": "",
        "models": [],
        "y_var": None,
        "x_var": None,
        "mediators": [],
        "controls": [],
        "entity_var": "firm_id",
        "time_var": "year",
        "data_path": "workspace/data/sample.dta",
    }

    # 提取 Y
    m = re.search(r"被解释变量.*?[（(](\w+)[）)]|Y[：:]\s*`?(\w+)`?", content)
    if m:
        spec["y_var"] = m.group(1) or m.group(2)
    else:
        spec["y_var"] = "Chain"

    # 提取 X
    m = re.search(r"核心解释变量.*?[（(](\w+)[）)]|X[：:]\s*`?(\w+)`?", content)
    if m:
        spec["x_var"] = m.group(1) or m.group(2)
    else:
        spec["x_var"] = "PCapital"

    # 提取中介变量
    med_match = re.search(r"中介.*?[：:]\s*(.+?)(?:\n|$)", content)
    if med_match:
        spec["mediators"] = [m.strip() for m in re.split(r"[,、/]", med_match.group(1))
                             if m.strip() and len(m.strip()) < 20]

    # 提取控制变量
    ctrl_match = re.search(r"控制变量", content)
    if ctrl_match:
        # 找后续的列表
        ctrl_section = content[ctrl_match.start():ctrl_match.start() + 500]
        vars_found = re.findall(r"`(\w+)`", ctrl_section)
        spec["controls"] = list(dict.fromkeys(vars_found))[:10]

    # 识别需要的模型
    for keyword, model_name in BLUEPRINT_TO_STATA.items():
        if keyword.lower() in content.lower() and model_name not in spec["models"]:
            spec["models"].append(model_name)

    # 确保有序：基准 → 核心识别 → 机制 → 异质性 → 稳健性 → 诊断
    model_order = ["panel_fe", "sharp_rdd", "staggered_did", "iv_2sls",
                   "mediation", "heterogeneity", "robustness", "diagnostics"]
    spec["models"] = [m for m in model_order if m in spec["models"]]

    # 如果没有识别到任何模型，默认用 panel_fe
    if not spec["models"]:
        spec["models"] = ["panel_fe"]

    return spec


def generate_do_file(model_name: str, spec: dict, data_path: str) -> str:
    """为指定模型生成完整的 .do 文件"""
    template_path = os.path.join(STATA_LIB, f"{model_name}.do")
    if not os.path.exists(template_path):
        return f"* Template not found: {model_name}.do\n"
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # 变量替换
    y = spec.get("y_var", "Chain")
    x = spec.get("x_var", "PCapital")
    controls = " ".join(spec.get("controls", ["Age", "ROA"]))
    entity = spec.get("entity_var", "firm_id")
    time = spec.get("time_var", "year")
    mediators = " ".join(spec.get("mediators", ["RSI", "Slack"]))

    # 提取 x_vars 列表（多个时逗号分隔）
    x_vars_list = [x]
    if "," in x:
        x_vars_list = [v.strip() for v in x.split(",")]

    header = f"""/*===========================================================================
 * 自动生成: {model_name}
 * 日期: {datetime.now().strftime("%Y-%m-%d %H:%M")}
 * 数据: {data_path}
 * Y = {y}, X = {x}, Controls = {controls}
 *===========================================================================*/

clear all
set more off
set matsize 800
capture log close

* 创建工作目录
capture mkdir "workspace/regression"

* 打开日志
log using "workspace/regression/{model_name}_{{datetime.now().strftime('%Y%m%d_%H%M%S')}}.log", text replace

* 加载数据
use "{data_path}", clear
display "数据加载完成: " _N " 观测值, " c(k) " 变量"

* ========== 设定 locals ==========
local y_var "{y}"
local x_vars "{x}"
local controls "{controls}"
local entity_var "{entity}"
local time_var "{time}"
local mediators "{mediators}"
local x_var "{x}"

"""

    footer = """
* ========== 保存结果 ==========
log close
display "分析完成。结果已保存至 workspace/regression/"
"""

    return header + template + footer


def main():
    parser = argparse.ArgumentParser(description="Stata 实证分析桥接器")
    parser.add_argument("--blueprint", type=str, help="论文蓝图路径")
    parser.add_argument("--data", type=str, default="workspace/data/sample.dta",
                        help="数据文件路径 (.dta)")
    parser.add_argument("--model", type=str, help="指定单个模型 (覆盖蓝图解析)")
    parser.add_argument("--y", type=str, help="被解释变量")
    parser.add_argument("--x", type=str, help="核心解释变量")
    parser.add_argument("--controls", type=str, default="", help="控制变量（空格分隔）")
    parser.add_argument("--mediators", type=str, default="", help="中介变量（空格分隔）")
    parser.add_argument("--entity", type=str, default="firm_id")
    parser.add_argument("--time", type=str, default="year")
    parser.add_argument("--output", type=str, default="workspace/regression",
                        help="输出目录")
    parser.add_argument("--dry-run", action="store_true", help="仅生成 .do 不运行")
    parser.add_argument("--list-models", action="store_true", help="列出所有可用 Stata 模型")
    args = parser.parse_args()

    if args.list_models:
        do_files = [f.replace(".do", "") for f in os.listdir(STATA_LIB)
                    if f.endswith(".do")]
        print("可用 Stata 模型模板:")
        for m in sorted(do_files):
            desc = {v: k for k, v in BLUEPRINT_TO_STATA.items()}.get(m, "")
            print(f"  {m:20s} {desc}")
        return

    # 确定模型和变量
    if args.blueprint:
        spec = parse_blueprint(args.blueprint)
        models = [args.model] if args.model else spec["models"]
    else:
        spec = {}
        models = [args.model] if args.model else ["panel_fe"]

    # 命令行参数覆盖蓝图解析
    if args.y:
        spec["y_var"] = args.y
    if args.x:
        spec["x_var"] = args.x
    if args.controls:
        spec["controls"] = args.controls.split()
    if args.mediators:
        spec["mediators"] = args.mediators.split()
    if args.entity:
        spec["entity_var"] = args.entity
    if args.time:
        spec["time_var"] = args.time

    # 确保基本变量存在
    spec.setdefault("y_var", "Chain")
    spec.setdefault("x_var", "PCapital")
    spec.setdefault("controls", ["Age", "ROA"])
    spec.setdefault("entity_var", "firm_id")
    spec.setdefault("time_var", "year")
    spec.setdefault("mediators", ["RSI", "Slack"])

    data_path = os.path.abspath(args.data)
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    print(f"数据: {data_path}")
    print(f"变量: Y={spec['y_var']}, X={spec['x_var']}")
    print(f"模型: {models}")
    print()

    for model_name in models:
        print(f"{'='*60}")
        print(f"生成: {model_name}.do")
        print(f"{'='*60}")

        do_content = generate_do_file(model_name, spec, data_path)
        do_path = os.path.join(output_dir, f"{model_name}.do")
        with open(do_path, "w", encoding="utf-8") as f:
            f.write(do_content)

        print(f"  .do 文件: {do_path}")
        print(f"  大小: {len(do_content)} 字符")
        print()

        if not args.dry_run:
            print(f"  [提示] 使用 stata_run_file 运行此 .do 文件")
            print(f"  [提示] 或直接让 Agent 读此文件后通过 stata_run_selection 交互式执行")

    # 生成汇总
    plan_path = os.path.join(output_dir, "_run_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump({
            "data_path": data_path,
            "spec": {k: v for k, v in spec.items() if isinstance(v, (str, list))},
            "models": models,
            "generated_at": datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)

    print(f"运行计划: {plan_path}")
    print(f"\n共 {len(models)} 个模型待运行。使用 Stata MCP 逐模型执行。")


if __name__ == "__main__":
    main()
