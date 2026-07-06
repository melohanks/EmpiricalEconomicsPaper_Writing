"""
面板双向固定效应模型 (Two-way Fixed Effects)

依赖：statsmodels, pandas
可选：linearmodels（更完善的面板FE支持）

调用示例：
    from regression_lib import run_model
    result = run_model("panel_fe", data_path="data.csv", y_var="Chain",
                       x_vars=["PCapital"], controls=["Age","ROA"],
                       entity_col="firm_id", time_col="year",
                       cluster_col="firm_id")
"""
import numpy as np
import pandas as pd
from regression_lib.base import load_data, save_results, make_result, winsorize


def run(data_path: str, y_var: str, x_vars: list,
        controls: list = None, entity_col: str = "firm_id",
        time_col: str = "year", cluster_col: str = None,
        fe_entity: bool = True, fe_time: bool = True,
        winsorize_pct: float = 0.01, **kwargs) -> dict:
    """
    面板双向固定效应回归

    Args:
        data_path: CSV 数据路径
        y_var: 被解释变量
        x_vars: 核心解释变量列表
        controls: 控制变量列表
        entity_col: 个体标识列
        time_col: 时间标识列
        cluster_col: 聚类标准误的列（默认与 entity_col 相同）
        fe_entity: 是否控制个体固定效应
        fe_time: 是否控制时间固定效应
        winsorize_pct: 缩尾比例（0=不缩尾）
    """
    try:
        import statsmodels.api as sm
        import statsmodels.formula.api as smf
    except ImportError:
        return make_result(False, "panel_fe",
                           summary="请安装 statsmodels: pip install statsmodels")

    df = load_data(data_path)
    n_orig = len(df)

    # 缩尾处理核心变量
    all_model_vars = x_vars + (controls or []) + [y_var]
    for v in all_model_vars:
        if v in df.columns and winsorize_pct > 0:
            df[v] = winsorize(df[v], winsorize_pct)

    # 构建变量集
    all_x = x_vars + (controls or [])

    # 构建公式
    fe_parts = []
    if fe_entity and entity_col in df.columns:
        fe_parts.append(f"C({entity_col})")
    if fe_time and time_col in df.columns:
        fe_parts.append(f"C({time_col})")

    formula_rhs = " + ".join(all_x)
    if fe_parts:
        formula_rhs += " + " + " + ".join(fe_parts)
    formula = f"{y_var} ~ {formula_rhs}"

    # 使用 OLS（大N时比 MixedLM 快，且结果等价）
    subset = df[all_x + [y_var]].dropna()
    X = sm.add_constant(subset[all_x])
    y = subset[y_var]

    # 逐步加入固定效应
    if fe_entity and entity_col in df.columns:
        entity_dummies = pd.get_dummies(df.loc[X.index, entity_col], drop_first=True)
        X = pd.concat([X, entity_dummies], axis=1)
    if fe_time and time_col in df.columns:
        time_dummies = pd.get_dummies(df.loc[X.index, time_col], drop_first=True)
        X = pd.concat([X, time_dummies], axis=1)

    model = sm.OLS(y, X.astype(float)).fit()

    # 聚类标准误
    if cluster_col and cluster_col in df.columns:
        try:
            model = model.get_robustcov_results(
                cov_type='cluster',
                groups=df.loc[X.index, cluster_col]
            )
        except Exception:
            pass  # 聚类失败，使用默认标准误

    # 构建系数表（只展示核心变量 + 控制变量）
    coef_rows = []
    for v in ["const"] + all_x:
        if v in model.params.index:
            coef_rows.append({
                "variable": v,
                "coef": round(model.params[v], 6),
                "std_err": round(model.bse[v], 6) if v in model.bse.index else None,
                "t_stat": round(model.tvalues[v], 4) if v in model.tvalues.index else None,
                "p_value": round(model.pvalues[v], 4) if v in model.pvalues.index else None,
                "significant": "***" if model.pvalues[v] < 0.01 else
                               ("**" if model.pvalues[v] < 0.05 else
                                ("*" if model.pvalues[v] < 0.1 else ""))
            })
    coef_table = pd.DataFrame(coef_rows)

    summary = f"""=== 面板双向固定效应 ===
样本量: {int(model.nobs)} (原始: {n_orig})
R²: {model.rsquared:.4f}  R²_adjusted: {model.rsquared_adj:.4f}
F-statistic: {model.fvalue:.2f} (p={model.f_pvalue:.4f})

核心变量系数:
""" + "\n".join(f"  {r['variable']}: {r['coef']:.4f} ({r['significant']}) p={r['p_value']}"
               for r in coef_rows if r['variable'] in x_vars + ["const"])

    result = make_result(
        True, "panel_fe", summary=summary, coef_table=coef_table,
        diagnostics={"n_obs": int(model.nobs), "r_squared": model.rsquared,
                     "f_stat": model.fvalue, "f_pval": model.f_pvalue}
    )
    result["path"] = save_results("panel_fe", result)
    return result
