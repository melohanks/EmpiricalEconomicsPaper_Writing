"""
异质性分析：分组回归 + 交互项

支持两种模式：
1. 分组回归 (group)：按分组变量拆分子样本回归
2. 交互项 (interaction)：X × 调节变量 交互项

调用示例：
    result = run_model("heterogeneity", data_path="data.csv", y_var="Chain",
                       x_vars=["PCapital"], group_var="ownership",
                       controls=["Age", "ROA"], mode="group")
"""
import numpy as np
import pandas as pd
from regression_lib.base import load_data, save_results, make_result


def run(data_path: str, y_var: str, x_vars: list,
        group_var: str = None, interact_var: str = None,
        controls: list = None, mode: str = "group",
        min_group_size: int = 30, **kwargs) -> dict:
    """
    异质性分析

    Args:
        data_path: CSV 数据路径
        y_var: 被解释变量
        x_vars: 核心解释变量
        group_var: 分组变量（mode="group" 时使用）
        interact_var: 交互变量（mode="interaction" 时使用）
        controls: 控制变量
        mode: "group" | "interaction" | "both"
        min_group_size: 最小分组样本量
    """
    try:
        import statsmodels.api as sm
    except ImportError:
        return make_result(False, "heterogeneity",
                           summary="请安装 statsmodels: pip install statsmodels")

    df = load_data(data_path)
    results = []
    lines = [f"=== 异质性分析 ===", f"模式: {mode}", ""]

    all_x = x_vars + (controls or [])
    all_cols = [y_var] + all_x
    missing = [c for c in all_cols if c not in df.columns]
    if missing:
        return make_result(False, "heterogeneity", summary=f"缺少列: {missing}")

    # ─── 分组回归 ───
    if mode in ("group", "both") and group_var:
        if group_var not in df.columns:
            return make_result(False, "heterogeneity",
                               summary=f"分组变量不存在: {group_var}")

        lines.append(f"## 分组回归 (group_var={group_var})")
        lines.append("")

        for gname, gdf in df.groupby(group_var):
            if len(gdf) < min_group_size:
                continue
            subset = gdf[all_cols].dropna()
            if len(subset) < min_group_size:
                continue

            X = sm.add_constant(subset[all_x])
            y = subset[y_var]
            model = sm.OLS(y, X).fit()

            group_results = {
                "group": str(gname), "n": len(subset),
                "r_squared": round(model.rsquared, 4),
            }
            for v in x_vars:
                if v in model.params.index:
                    group_results[f"coef_{v}"] = round(model.params[v], 6)
                    group_results[f"p_{v}"] = round(model.pvalues[v], 4)
                    group_results[f"sig_{v}"] = "***" if model.pvalues[v] < 0.01 else \
                                                "**" if model.pvalues[v] < 0.05 else \
                                                "*" if model.pvalues[v] < 0.1 else ""
            results.append(group_results)

            sig_mark = group_results.get(f"sig_{x_vars[0]}", "") if x_vars else ""
            lines.append(f"  {gname} (N={len(subset)}): "
                         f"coef={group_results.get(f'coef_{x_vars[0]}', np.nan):.4f}{sig_mark}")

    # ─── 交互项 ───
    if mode in ("interaction", "both") and interact_var:
        if interact_var not in df.columns:
            return make_result(False, "heterogeneity",
                               summary=f"交互变量不存在: {interact_var}")

        lines.append("")
        lines.append(f"## 交互项 (X × {interact_var})")
        lines.append("")

        df["_interact"] = df[x_vars[0]] * df[interact_var]
        all_x_with_int = all_x + ["_interact"]
        subset = df[all_x_with_int + [y_var]].dropna()

        X = sm.add_constant(subset[all_x_with_int])
        y = subset[y_var]
        model = sm.OLS(y, X).fit()

        interact_coef = model.params.get("_interact", np.nan)
        interact_p = model.pvalues.get("_interact", np.nan)

        results.append({
            "type": "interaction",
            "interact_term": f"{x_vars[0]} × {interact_var}",
            "coef": round(interact_coef, 6),
            "p_value": round(interact_p, 4),
            "significant": interact_p < 0.05,
            "n": int(model.nobs),
            "r_squared": round(model.rsquared, 4),
        })

        lines.append(f"  交互项: {x_vars[0]} × {interact_var}")
        lines.append(f"  coef: {interact_coef:.4f} (p={interact_p:.4f})")
        lines.append(f"  {'交互效应显著 ✓' if interact_p < 0.05 else '交互效应不显著'}")

    coef_table = pd.DataFrame(results) if results else pd.DataFrame()
    summary = "\n".join(lines)

    result = make_result(True, "heterogeneity", summary=summary,
                         coef_table=coef_table, diagnostics={"mode": mode})
    result["path"] = save_results("heterogeneity", result)
    return result
