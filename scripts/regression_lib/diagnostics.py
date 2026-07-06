"""
模型诊断工具集

包含：
1. McCrary 密度检验（RDD 前提）
2. 平行趋势检验（DID 前提）
3. 安慰剂检验（Placebo Test）
4. VIF 多重共线性
5. 协变量平衡性检验（RDD 前提）

调用示例：
    result = run_model("diagnostics", data_path="data.csv",
                       diagnostic_type="mccrary", running_var="firm_age", cutoff=5.0)
"""
import numpy as np
import pandas as pd
from regression_lib.base import load_data, save_results, make_result


def run(data_path: str, diagnostic_type: str = "all",
        running_var: str = None, cutoff: float = None,
        treat_col: str = None, time_col: str = None,
        event_time_col: str = None, y_var: str = None,
        x_vars: list = None, x_var: str = None,
        controls: list = None,
        n_placebo: int = 500, **kwargs) -> dict:
    """
    模型诊断

    Args:
        data_path: CSV 数据路径
        diagnostic_type: "mccrary" | "parallel_trends" | "placebo" | "vif" | "covariate_balance" | "all"
        running_var: 驱动变量（McCrary/RDD）
        cutoff: 断点值（McCrary）
        treat_col: 处理组标识（平行趋势/安慰剂）
        time_col: 时间列（平行趋势）
        event_time_col: 事件时间列（平行趋势）
        y_var: 被解释变量（安慰剂/VIF）
        x_vars: 解释变量（VIF/协变量平衡）
        controls: 控制变量
        n_placebo: 安慰剂检验随机置换次数
    """
    df = load_data(data_path)
    all_results = {}
    lines = ["=== 模型诊断 ===\n"]

    # ─── McCrary 密度检验 ───
    if diagnostic_type in ("mccrary", "all") and running_var and cutoff is not None:
        lines.append("## 1. McCrary 密度检验 (RDD前提)")
        if running_var in df.columns:
            try:
                from rdrobust import rddensity
                dens = rddensity(X=df[running_var].dropna().values, c=cutoff)
                pval = dens.test.pvalue if hasattr(dens.test, 'pvalue') else dens.pv
                verdict = "通过 ✓ (p>0.05, 断点处无操纵)" if pval > 0.05 else \
                          "未通过 ✗ (p<0.05, 可能存在断点操纵)"
                all_results["mccrary"] = {"p_value": pval, "verdict": verdict}
                lines.append(f"  p={pval:.4f} → {verdict}")
            except ImportError:
                lines.append("  ⚠ rdrobust 未安装，回退到手动Bin检验")
                result = _mccrary_manual(df, running_var, cutoff)
                all_results["mccrary"] = result
                lines.append(f"  Bin差异 t={result.get('t_stat', np.nan):.3f} → {result.get('verdict', '?')}")
        else:
            lines.append(f"  ⚠ 驱动变量 {running_var} 不存在于数据中")
        lines.append("")

    # ─── 平行趋势检验 ───
    if diagnostic_type in ("parallel_trends", "all") and treat_col and time_col:
        lines.append("## 2. 平行趋势检验 (DID前提)")
        if treat_col in df.columns and time_col in df.columns:
            result = _parallel_trends_check(df, y_var, treat_col, time_col)
            all_results["parallel_trends"] = result
            lines.append(result.get("summary", ""))
        else:
            lines.append(f"  ⚠ 缺少 {treat_col} 或 {time_col}")
        lines.append("")

    # ─── 安慰剂检验 ───
    if diagnostic_type in ("placebo", "all") and y_var and x_vars:
        lines.append(f"## 3. 安慰剂检验 ({n_placebo}次随机置换)")
        result = _placebo_test(df, y_var, x_vars[0] if x_vars else None, controls, n_placebo)
        all_results["placebo"] = result
        lines.append(result.get("summary", ""))
        lines.append("")

    # ─── VIF ───
    if diagnostic_type in ("vif", "all") and x_vars:
        lines.append("## 4. VIF 多重共线性检验")
        result = _vif_check(df, x_vars + (controls or []))
        all_results["vif"] = result
        lines.append(str(result.get("table", "")))
        lines.append("")

    # ─── 协变量平衡性 ───
    if diagnostic_type in ("covariate_balance", "all") and running_var and cutoff is not None:
        lines.append("## 5. 协变量平衡性检验 (RDD前提)")
        if controls:
            result = _covariate_balance(df, running_var, cutoff, controls)
            all_results["covariate_balance"] = result
            lines.append(result.get("summary", ""))
        lines.append("")

    summary = "\n".join(lines)
    result = make_result(True, "diagnostics", summary=summary,
                         diagnostics=all_results)
    result["path"] = save_results("diagnostics", result)
    return result


def _mccrary_manual(df, running_var, cutoff, n_bins=20):
    """手动 McCrary 检验（不需要 rdrobust）"""
    df = df[[running_var]].dropna()
    x = df[running_var]
    bins = np.linspace(x.min(), x.max(), n_bins + 1)
    bin_counts = []
    for i in range(n_bins):
        cnt = ((x >= bins[i]) & (x < bins[i + 1])).sum()
        bin_counts.append(cnt)

    # 断点附近比较
    mid = np.digitize(cutoff, bins) - 1
    left = bin_counts[max(0, mid-3):mid]
    right = bin_counts[mid:min(n_bins, mid+3)]
    if len(left) > 0 and len(right) > 0:
        t_stat = (np.mean(left) - np.mean(right)) / (np.std(left + right) + 1e-10)
        import math as _math; pval = 2 * (1 - 0.5 * (1 + _math.erf(abs(t_stat) / np.sqrt(2))))
        verdict = "通过 ✓" if pval > 0.05 else "未通过 ✗"
    else:
        t_stat, pval, verdict = np.nan, np.nan, "无法判定"
    return {"t_stat": t_stat, "p_value": pval, "verdict": verdict}


def _parallel_trends_check(df, y_var, treat_col, time_col):
    """简单的平行趋势检查：比较处理前趋势斜率"""
    if y_var not in df.columns:
        return {"summary": f"  ⚠ Y变量 {y_var} 不存在"}
    df["_pre_treat"] = (df[treat_col] == 0).astype(int)
    # 简化：检查处理前两组的趋势是否平行
    summary = "  ⚠ 需要事件时间变量进行全面平行趋势检验。建议使用 event_study 模型绘图。\n"
    summary += "  快速检查：在处理前时期，处理组和对照组Y的增长率差异应不显著。"
    return {"summary": summary}


def _placebo_test(df, y_var, x_var, controls, n_iter):
    """安慰剂检验：随机置换处理组标签"""
    try:
        import statsmodels.api as sm
    except ImportError:
        return {"summary": "请安装 statsmodels"}

    all_x = [x_var] + (controls or [])
    subset = df[[y_var] + all_x].dropna()

    # 真实效应
    X = sm.add_constant(subset[all_x])
    true_model = sm.OLS(subset[y_var], X).fit()
    true_coef = true_model.params.get(x_var, 0)

    # 随机置换
    placebo_coefs = []
    rng = np.random.default_rng(42)
    for _ in range(n_iter):
        df_shuffled = subset.copy()
        df_shuffled[x_var] = rng.permutation(df_shuffled[x_var].values)
        try:
            Xp = sm.add_constant(df_shuffled[all_x])
            mp = sm.OLS(subset[y_var], Xp).fit()
            placebo_coefs.append(mp.params.get(x_var, 0))
        except Exception:
            pass

    placebo_coefs = np.array(placebo_coefs)
    p_value = (np.abs(placebo_coefs) >= np.abs(true_coef)).mean()
    verdict = f"通过 ✓ (安慰剂p={p_value:.3f})" if p_value < 0.05 else \
              f"未通过 ✗ (安慰剂p={p_value:.3f}，真实效应不显著异于随机)"

    summary = f"""  真实系数: {true_coef:.6f}
  安慰剂均值: {placebo_coefs.mean():.6f}
  安慰剂std: {placebo_coefs.std():.6f}
  经验p值: {p_value:.4f}
  判定: {verdict}"""

    return {"summary": summary, "true_coef": true_coef, "placebo_mean": placebo_coefs.mean(),
            "placebo_std": placebo_coefs.std(), "p_value": p_value, "verdict": verdict}


def _vif_check(df, cols):
    """VIF 多重共线性检验"""
    try:
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        import statsmodels.api as sm
        subset = df[[c for c in cols if c in df.columns]].dropna()
        X = sm.add_constant(subset)
        vif_data = pd.DataFrame({
            "variable": X.columns,
            "VIF": [variance_inflation_factor(X.values, i) for i in range(X.shape[1])]
        })
        high_vif = vif_data[vif_data["VIF"] > 10]
        table_str = vif_data.to_string(index=False)
        verdict = f"通过 ✓ (所有VIF<10)" if len(high_vif) == 0 else \
                  f"⚠ {len(high_vif)} 个变量VIF>10: {list(high_vif['variable'])}"
        return {"table": table_str, "verdict": verdict, "high_vif_count": len(high_vif)}
    except Exception as e:
        return {"table": f"VIF计算失败: {e}", "verdict": "无法判定"}


def _covariate_balance(df, running_var, cutoff, covars):
    """协变量平衡性：断点两侧协变量均值差异"""
    df["_above"] = (df[running_var] >= cutoff).astype(int)
    results = []
    for v in covars:
        if v not in df.columns:
            continue
        below = df[df["_above"] == 0][v].dropna()
        above = df[df["_above"] == 1][v].dropna()
        if len(below) > 1 and len(above) > 1:
            diff = above.mean() - below.mean()
            se = np.sqrt(below.var() / len(below) + above.var() / len(above))
            t_stat = diff / se if se > 0 else 0
            import math as _math; pval = 2 * (1 - 0.5 * (1 + _math.erf(abs(t_stat) / np.sqrt(2))))
            results.append({"covariate": v, "diff": diff, "t_stat": t_stat, "p_value": pval,
                            "balanced": pval > 0.05})

    n_unbalanced = sum(1 for r in results if not r["balanced"])
    summary = "\n".join(f"  {r['covariate']}: diff={r['diff']:.4f} p={r['p_value']:.4f} "
                        f"{'✓' if r['balanced'] else '✗'}" for r in results)
    summary += f"\n  {'全部平衡 ✓' if n_unbalanced == 0 else f'{n_unbalanced} 个变量不平衡 ✗'}"
    return {"summary": summary, "details": results, "n_unbalanced": n_unbalanced}
