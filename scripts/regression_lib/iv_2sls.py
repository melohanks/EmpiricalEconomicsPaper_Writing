"""
工具变量法 (IV-2SLS)

依赖：statsmodels, linearmodels（推荐）

调用示例：
    result = run_model("iv_2sls", data_path="data.csv", y_var="Chain",
                       x_vars=["PCapital"], iv_vars=["iv_mean_peers"],
                       controls=["Age","ROA"])
"""
import numpy as np
import pandas as pd
from regression_lib.base import load_data, save_results, make_result


def run(data_path: str, y_var: str, x_vars: list,
        iv_vars: list, controls: list = None, **kwargs) -> dict:
    """
    IV-2SLS

    Args:
        data_path: CSV 数据路径
        y_var: 被解释变量
        x_vars: 内生解释变量列表
        iv_vars: 工具变量列表（必须 >= len(x_vars)）
        controls: 外生控制变量
    """
    df = load_data(data_path)

    if len(iv_vars) < len(x_vars):
        return make_result(False, "iv_2sls",
                           summary=f"工具变量不足: {len(iv_vars)} < {len(x_vars)} (内生变量数)")

    all_exog = (controls or []) + iv_vars
    all_vars = [y_var] + x_vars + all_exog
    missing = [c for c in all_vars if c not in df.columns]
    if missing:
        return make_result(False, "iv_2sls", summary=f"缺少列: {missing}")

    # 尝试 linearmodels（首选）
    try:
        from linearmodels.iv import IV2SLS

        subset = df[all_vars].dropna()
        formula = f"{y_var} ~ 1 + {' + '.join(controls or [])} + [{' + '.join(x_vars)} ~ {' + '.join(iv_vars)}]"
        model = IV2SLS.from_formula(formula, subset)
        result = model.fit()

        # 第一阶段F统计量
        f_stat = result.first_stage.diagnostics.get("f.stat", [np.nan])[0] \
            if hasattr(result, 'first_stage') and result.first_stage else np.nan

        coef_rows = []
        for v in (controls or []) + x_vars:
            if v in result.params.index:
                coef_rows.append({
                    "variable": v,
                    "coef": round(result.params[v], 6),
                    "std_err": round(result.std_errors[v], 6),
                    "p_value": round(result.pvalues[v], 4),
                    "significant": "***" if result.pvalues[v] < 0.01 else
                                   ("**" if result.pvalues[v] < 0.05 else
                                    ("*" if result.pvalues[v] < 0.1 else ""))
                })

        summary = f"""=== IV-2SLS ===
样本量: {int(result.nobs)}
R²: {result.rsquared:.4f}
第一阶段F统计量: {f_stat:.2f} {'(>10, 强工具变量)' if f_stat > 10 else '(<10, 弱工具变量⚠)'}

内生变量系数:
""" + "\n".join(f"  {r['variable']}: {r['coef']:.4f} ({r['significant']}) p={r['p_value']}"
               for r in coef_rows if r['variable'] in x_vars)

        coef_table = pd.DataFrame(coef_rows)

    except ImportError:
        # 备选：statsmodels 手动2SLS
        import statsmodels.api as sm

        subset = df[all_vars].dropna()
        y = subset[y_var]
        X_endo = subset[x_vars]
        Z = subset[iv_vars + (controls or [])]

        # 第一阶段：X_endo ~ Z
        stage1 = sm.OLS(X_endo, sm.add_constant(Z)).fit()
        X_hat = stage1.predict(sm.add_constant(Z))

        # 第二阶段：y ~ X_hat + controls
        X_stage2 = pd.concat([X_hat, subset[controls or []]], axis=1)
        X_stage2.columns = list(range(X_stage2.shape[1]))
        stage2 = sm.OLS(y, sm.add_constant(X_stage2)).fit()

        coef_rows = [{
            "variable": x_vars[0] if len(x_vars) == 1 else "X_hat",
            "coef": round(stage2.params.iloc[1], 6),
            "std_err": round(stage2.bse.iloc[1], 6),
            "p_value": round(stage2.pvalues.iloc[1], 4),
            "significant": "***" if stage2.pvalues.iloc[1] < 0.01 else "",
        }]
        f_stat = np.nan
        summary = f"""=== IV-2SLS (statsmodels 手动) ===
样本量: {int(stage2.nobs)}
⚠ 使用 statsmodels 手动2SLS，标准误需手动修正。推荐 pip install linearmodels
"""
        coef_table = pd.DataFrame(coef_rows)

    result = make_result(
        True, "iv_2sls", summary=summary, coef_table=coef_table,
        diagnostics={"first_stage_f": f_stat, "iv_count": len(iv_vars),
                     "endo_count": len(x_vars)}
    )
    result["path"] = save_results("iv_2sls", result)
    return result
