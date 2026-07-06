"""
稳健性检验套件

包含：
1. 替换Y变量（备选测度）
2. 替换X变量（备选测度）
3. 缩尾处理对比
4. 剔除特定样本（如一线城市、金融危机期间）
5. 增减控制变量

调用示例：
    result = run_model("robustness", data_path="data.csv", y_var="Chain",
                       x_vars=["PCapital"], controls=["Age", "ROA"],
                       y_alt="Chain_alt", x_alt="PCapital_alt",
                       winsorize_pct=0.01, exclude_condition="year < 2012")
"""
import numpy as np
import pandas as pd
from regression_lib.base import load_data, save_results, make_result


def run(data_path: str, y_var: str, x_vars: list,
        controls: list = None, y_alt: str = None,
        x_alt: str = None, winsorize_pct: float = 0.01,
        exclude_condition: str = None, **kwargs) -> dict:
    """
    稳健性检验套件

    Args:
        data_path: CSV 数据路径
        y_var: 被解释变量（主测度）
        x_vars: 核心解释变量（主测度）
        controls: 控制变量
        y_alt: Y 的备选测度
        x_alt: X 的备选测度
        winsorize_pct: 缩尾比例
        exclude_condition: 排除条件（pandas query 字符串），如 "year < 2012"
    """
    try:
        import statsmodels.api as sm
    except ImportError:
        return make_result(False, "robustness", summary="请安装 statsmodels")

    df = load_data(data_path)
    results = []
    lines = [f"=== 稳健性检验套件 ===", f"基准 Y={y_var}, X={x_vars}", ""]

    # 基准回归
    baseline = _run_single(df, y_var, x_vars, controls)
    base_coef = baseline.get(x_vars[0], {}).get("coef", np.nan)
    lines.append(f"## 基准: coef={base_coef:.4f}")
    lines.append("")

    check_count = 0

    # 检验1: 缩尾处理
    if winsorize_pct > 0:
        df_w = df.copy()
        for v in [y_var] + x_vars + (controls or []):
            if v in df_w.columns:
                lo, hi = df_w[v].quantile(winsorize_pct), df_w[v].quantile(1 - winsorize_pct)
                df_w[v] = df_w[v].clip(lo, hi)
        r = _run_single(df_w, y_var, x_vars, controls)
        coef = r.get(x_vars[0], {}).get("coef", np.nan)
        stable = abs(base_coef - coef) < abs(base_coef) * 0.5 if not np.isnan(base_coef) else None
        results.append({"test": f"缩尾 {winsorize_pct*100:.0f}%", "coef": coef, "stable": stable})
        lines.append(f"  缩尾{winsorize_pct*100:.0f}%: coef={coef:.4f} {'✓' if stable else '✗'}")
        check_count += 1

    # 检验2: 替换Y
    if y_alt and y_alt in df.columns:
        r = _run_single(df, y_alt, x_vars, controls)
        coef = r.get(x_vars[0], {}).get("coef", np.nan)
        stable = np.sign(base_coef) == np.sign(coef) if not (np.isnan(base_coef) or np.isnan(coef)) else None
        results.append({"test": f"替换Y: {y_alt}", "coef": coef, "stable": stable})
        lines.append(f"  替换Y({y_alt}): coef={coef:.4f} {'✓' if stable else '✗'}")
        check_count += 1

    # 检验3: 替换X
    if x_alt and x_alt in df.columns:
        r = _run_single(df, y_var, [x_alt] + x_vars[1:], controls)
        coef = r.get(x_alt, {}).get("coef", np.nan)
        stable = np.sign(base_coef) == np.sign(coef) if not (np.isnan(base_coef) or np.isnan(coef)) else None
        results.append({"test": f"替换X: {x_alt}", "coef": coef, "stable": stable})
        lines.append(f"  替换X({x_alt}): coef={coef:.4f} {'✓' if stable else '✗'}")
        check_count += 1

    # 检验4: 排除子样本
    if exclude_condition:
        try:
            df_ex = df.query(f"not ({exclude_condition})")
            r = _run_single(df_ex, y_var, x_vars, controls)
            coef = r.get(x_vars[0], {}).get("coef", np.nan)
            stable = abs(base_coef - coef) < abs(base_coef) * 0.5 if not np.isnan(base_coef) else None
            results.append({
                "test": f"排除: {exclude_condition}",
                "coef": coef, "n": len(df_ex), "stable": stable
            })
            lines.append(f"  排除({exclude_condition}): coef={coef:.4f} N={len(df_ex)} {'✓' if stable else '✗'}")
            check_count += 1
        except Exception as e:
            lines.append(f"  排除条件执行失败: {e}")

    # 汇总判定
    stable_count = sum(1 for r in results if r.get("stable"))
    verdict = "全部通过 ✓✓" if stable_count == check_count else \
              f"{stable_count}/{check_count} 通过" if stable_count > 0 else "全部未通过 ✗"
    lines.append("")
    lines.append(f"### 稳健性判定: {verdict}")

    coef_table = pd.DataFrame(results)
    summary = "\n".join(lines)

    result = make_result(True, "robustness", summary=summary, coef_table=coef_table,
                         diagnostics={"n_tests": check_count, "n_passed": stable_count})
    result["path"] = save_results("robustness", result)
    return result


def _run_single(df, y_var, x_vars, controls):
    """单次回归辅助"""
    try:
        import statsmodels.api as sm
        all_x = x_vars + (controls or [])
        subset = df[[y_var] + all_x].dropna()
        if len(subset) < 30:
            return {}
        X = sm.add_constant(subset[all_x])
        y = subset[y_var]
        model = sm.OLS(y, X).fit()
        return {v: {"coef": model.params[v], "pval": model.pvalues[v]} for v in x_vars}
    except Exception:
        return {}
