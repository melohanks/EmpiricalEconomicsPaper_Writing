"""
中介效应检验

包含两种方法：
1. Baron-Kenny 三步法 + Sobel 检验
2. Bootstrap 置信区间法（更稳健）

调用示例：
    result = run_model("mediation", data_path="data.csv", y_var="Chain",
                       x_var="PCapital", mediators=["RSI", "Slack"],
                       controls=["Age", "ROA"])
"""
import numpy as np
import pandas as pd
from regression_lib.base import load_data, save_results, make_result


def run(data_path: str, y_var: str = None, x_var: str = None,
        mediators: list = None, controls: list = None,
        bootstrap: int = 1000, x_vars: list = None, **kwargs) -> dict:
    """
    中介效应检验

    Args:
        data_path: CSV 数据路径
        y_var: 被解释变量
        x_var: 核心解释变量
        mediators: 中介变量列表
        controls: 控制变量
        bootstrap: Bootstrap 次数（0=仅三步法+Sobel）
    """
    # x_vars (from run_model) → x_var (singular)
    if x_var is None and x_vars is not None:
        x_var = x_vars[0] if len(x_vars) > 0 else None

    try:
        import statsmodels.api as sm
    except ImportError:
        return make_result(False, "mediation",
                           summary="请安装 statsmodels: pip install statsmodels")

    df = load_data(data_path)
    all_cols = [y_var, x_var] + mediators + (controls or [])
    missing = [c for c in all_cols if c not in df.columns]
    if missing:
        return make_result(False, "mediation", summary=f"缺少列: {missing}")

    subset = df[all_cols].dropna()
    results = []
    lines = [f"=== 中介效应检验 ===", f"样本量: {len(subset)}", ""]

    for med in mediators:
        cols_base = [x_var] + (controls or [])

        # Step 1: X → Y (总效应 c)
        m1 = sm.OLS(subset[y_var], sm.add_constant(subset[cols_base])).fit()
        c = m1.params[x_var]
        c_se = m1.bse[x_var]
        c_p = m1.pvalues[x_var]

        # Step 2: X → M (路径 a)
        m2 = sm.OLS(subset[med], sm.add_constant(subset[cols_base])).fit()
        a = m2.params[x_var]
        a_se = m2.bse[x_var]
        a_p = m2.pvalues[x_var]

        # Step 3: X + M → Y (路径 b, 直接效应 c')
        cols_m = cols_base + [med]
        m3 = sm.OLS(subset[y_var], sm.add_constant(subset[cols_m])).fit()
        b = m3.params[med]
        b_se = m3.bse[med]
        b_p = m3.pvalues[med]
        c_prime = m3.params[x_var]

        # Sobel 检验
        ab = a * b
        sobel_se = np.sqrt(a**2 * b_se**2 + b**2 * a_se**2)
        sobel_z = ab / sobel_se if sobel_se > 0 else np.nan
        import math as _math
        sobel_p = 2 * (1 - 0.5 * (1 + _math.erf(abs(sobel_z) / np.sqrt(2)))) if not np.isnan(sobel_z) else np.nan

        # 中介效应占比
        mediation_ratio = ab / c if c != 0 else 0

        results.append({
            "mediator": med,
            "total_effect_c": round(c, 6),
            "a_path (X→M)": round(a, 6),
            "b_path (M→Y|X)": round(b, 6),
            "indirect_ab": round(ab, 6),
            "direct_c_prime": round(c_prime, 6),
            "mediation_ratio": round(mediation_ratio, 4),
            "sobel_z": round(sobel_z, 4) if not np.isnan(sobel_z) else None,
            "sobel_p": round(sobel_p, 4) if not np.isnan(sobel_p) else None,
            "a_significant": a_p < 0.05,
            "b_significant": b_p < 0.05,
            "ab_significant": sobel_p < 0.05 if not np.isnan(sobel_p) else None,
        })

        verdict = "中介成立 ✓" if (a_p < 0.05 and b_p < 0.05 and not (np.isnan(sobel_p)) and sobel_p < 0.05) else \
                  "部分中介" if (a_p < 0.05 and b_p < 0.05) else "中介不显著 ✗"
        lines.append(f"--- {med} ---")
        lines.append(f"  总效应 c: {c:.4f} (p={c_p:.4f})")
        lines.append(f"  路径a (X→M): {a:.4f} (p={a_p:.4f})")
        lines.append(f"  路径b (M→Y|X): {b:.4f} (p={b_p:.4f})")
        lines.append(f"  间接效应 ab: {ab:.6f}")
        lines.append(f"  Sobel Z: {sobel_z:.4f} (p={sobel_p:.4f})")
        lines.append(f"  中介占比: {mediation_ratio:.1%}")
        lines.append(f"  判定: {verdict}")
        lines.append("")

    coef_table = pd.DataFrame(results)
    summary = "\n".join(lines)

    # Bootstrap（可选）
    if bootstrap > 0:
        bt_results = _bootstrap_mediation(subset, y_var, x_var, mediators, controls, bootstrap)
        summary += f"\n=== Bootstrap ({bootstrap}次) ===\n" + "\n".join(
            f"  {r['mediator']}: ab={r['ab_mean']:.6f}, "
            f"95%CI=[{r['ci_lower']:.6f}, {r['ci_upper']:.6f}], "
            f"{'显著(不含0)' if r['ci_lower'] * r['ci_upper'] > 0 else '不显著(含0)'}"
            for r in bt_results
        )
        for r in bt_results:
            for item in results:
                if item["mediator"] == r["mediator"]:
                    item.update(r)
                    break

    result = make_result(True, "mediation", summary=summary, coef_table=coef_table)
    result["path"] = save_results("mediation", result)
    return result


def _bootstrap_mediation(df, y_var, x_var, mediators, controls, n_boot):
    """Bootstrap 中介效应置信区间"""
    import statsmodels.api as sm
    rng = np.random.default_rng(42)
    bt_results = []

    for med in mediators:
        ab_samples = []
        cols_base = [x_var] + (controls or [])
        for _ in range(n_boot):
            idx = rng.choice(len(df), len(df), replace=True)
            sample = df.iloc[idx]
            try:
                m2 = sm.OLS(sample[med], sm.add_constant(sample[cols_base])).fit()
                a = m2.params[x_var]
                cols_m = cols_base + [med]
                m3 = sm.OLS(sample[y_var], sm.add_constant(sample[cols_m])).fit()
                b = m3.params[med]
                ab_samples.append(a * b)
            except Exception:
                ab_samples.append(np.nan)

        ab_valid = [x for x in ab_samples if not np.isnan(x)]
        if len(ab_valid) > 0:
            bt_results.append({
                "mediator": med,
                "ab_mean": np.mean(ab_valid),
                "ci_lower": np.percentile(ab_valid, 2.5),
                "ci_upper": np.percentile(ab_valid, 97.5),
                "n_valid": len(ab_valid),
            })

    return bt_results
