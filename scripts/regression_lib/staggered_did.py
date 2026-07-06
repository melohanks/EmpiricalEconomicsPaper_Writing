"""
Staggered DID（渐进双重差分 / 事件研究法）

依赖：statsmodels, pandas
可选：did / pyfixest (更完善的 DID 支持)

支持两种估计策略：
1. TWFE（传统双向固定效应DID）
2. 事件研究法 (Event Study) — 动态处理效应

调用示例：
    result = run_model("staggered_did", data_path="data.csv", y_var="Chain",
                       x_vars=[], treat_col="treated", time_col="year",
                       first_treat_col="first_treat_year",
                       entity_col="firm_id")
"""
import numpy as np
import pandas as pd
from regression_lib.base import load_data, save_results, make_result


def run(data_path: str, y_var: str, x_vars: list = None,
        treat_col: str = "treated", time_col: str = "year",
        first_treat_col: str = "first_treat", entity_col: str = "firm_id",
        controls: list = None, event_window: tuple = (-5, 5),
        base_period: int = -1, **kwargs) -> dict:
    """
    Staggered DID + Event Study

    Args:
        data_path: CSV 数据路径
        y_var: 被解释变量
        x_vars: 核心解释变量（除treat交互外）
        treat_col: 处理组标识列
        time_col: 时间列
        first_treat_col: 首次处理年份列
        entity_col: 个体标识列
        controls: 控制变量
        event_window: 事件窗口 (min, max)，如 (-5, 5)
        base_period: 基准期，默认 -1
    """
    try:
        import statsmodels.api as sm
    except ImportError:
        return make_result(False, "staggered_did",
                           summary="请安装 statsmodels: pip install statsmodels")

    df = load_data(data_path)

    # 必需列检查
    required = [y_var, treat_col, time_col, entity_col]
    if first_treat_col in df.columns:
        required.append(first_treat_col)
    missing = [c for c in required if c not in df.columns]
    if missing:
        return make_result(False, "staggered_did",
                           summary=f"缺少列: {missing}")

    n_total = len(df)

    # 如果只有 treat_col 而没有 first_treat_col，使用 TWFE
    if first_treat_col not in df.columns:
        return _run_twfe(df, y_var, x_vars, treat_col, time_col, entity_col, controls, n_total)

    # Event Study
    return _run_event_study(df, y_var, x_vars, treat_col, time_col,
                            first_treat_col, entity_col, controls,
                            event_window, base_period, n_total)


def _run_twfe(df, y_var, x_vars, treat_col, time_col, entity_col, controls, n_total):
    """传统 TWFE DID"""
    import statsmodels.api as sm

    all_x = (x_vars or []) + [treat_col] + (controls or [])
    subset = df[all_x + [y_var, entity_col, time_col]].dropna()

    X = sm.add_constant(subset[all_x])
    y = subset[y_var]

    # 加入FE
    entity_fe = pd.get_dummies(subset[entity_col], drop_first=True)
    time_fe = pd.get_dummies(subset[time_col], drop_first=True)
    X = pd.concat([X, entity_fe, time_fe], axis=1).astype(float)

    model = sm.OLS(y, X).fit()

    coef = model.params.get(treat_col, np.nan)
    pval = model.pvalues.get(treat_col, np.nan)
    se = model.bse.get(treat_col, np.nan)

    summary = f"""=== Staggered DID (TWFE) ===
样本量: {int(model.nobs)} / {n_total}
R²: {model.rsquared:.4f}

处理效应 (ATT):
  treat_col: {treat_col}
  coefficient: {coef:.6f}
  std_err: {se:.6f}
  p_value: {pval:.4f}
  significant: {'***' if pval < 0.01 else '**' if pval < 0.05 else '*' if pval < 0.1 else '不显著'}

⚠ 注意：当存在异质性处理效应时，TWFE估计可能有偏。建议使用 Sun & Abraham (2020) 或 Callaway & Sant'Anna (2020) 方法。
"""

    coef_table = pd.DataFrame([{
        "variable": treat_col, "coef": coef, "std_err": se,
        "p_value": pval, "significant": pval < 0.05
    }])

    result = make_result(True, "staggered_did", summary=summary,
                         coef_table=coef_table, diagnostics={"method": "TWFE"})
    result["path"] = save_results("staggered_did", result)
    return result


def _run_event_study(df, y_var, x_vars, treat_col, time_col,
                     first_treat_col, entity_col, controls,
                     event_window, base_period, n_total):
    """事件研究法"""
    import statsmodels.api as sm

    # 构造相对时间变量
    df["_event_time"] = df[time_col] - df[first_treat_col]
    df["_event_time"] = df["_event_time"].clip(event_window[0], event_window[1])

    # 生成事件时间虚拟变量
    event_times = range(event_window[0], event_window[1] + 1)
    event_dummies = {}
    for t in event_times:
        if t == base_period:
            continue  # 基准期
        col_name = f"event_{t:+d}"
        df[col_name] = ((df["_event_time"] == t) & (df[treat_col] == 1)).astype(int)
        event_dummies[t] = col_name

    dummy_cols = list(event_dummies.values())
    all_x = (x_vars or []) + dummy_cols + (controls or [])
    subset = df[all_x + [y_var, entity_col, time_col]].dropna()

    X = sm.add_constant(subset[all_x])
    y = subset[y_var]
    entity_fe = pd.get_dummies(subset[entity_col], drop_first=True)
    time_fe = pd.get_dummies(subset[time_col], drop_first=True)
    X = pd.concat([X, entity_fe, time_fe], axis=1).astype(float)

    model = sm.OLS(y, X).fit()

    # 提取动态效应
    dynamic_effects = []
    for t in sorted(event_dummies.keys()):
        col = event_dummies[t]
        if col in model.params.index:
            dynamic_effects.append({
                "event_time": t,
                "coef": round(model.params[col], 6),
                "std_err": round(model.bse[col], 6),
                "p_value": round(model.pvalues[col], 4),
                "ci_lower": round(model.params[col] - 1.96 * model.bse[col], 6),
                "ci_upper": round(model.params[col] + 1.96 * model.bse[col], 6),
            })

    coef_table = pd.DataFrame(dynamic_effects)

    summary = f"""=== Event Study ===
样本量: {int(model.nobs)} / {n_total}  |  事件窗口: [{event_window[0]}, {event_window[1]}]
基准期: t={base_period}

动态处理效应:
""" + "\n".join(f"  t={e['event_time']:+d}: {e['coef']:.4f} ({'***' if e['p_value']<0.01 else '**' if e['p_value']<0.05 else '*' if e['p_value']<0.1 else ''}) p={e['p_value']}"
               for e in dynamic_effects)

    result = make_result(True, "staggered_did", summary=summary,
                         coef_table=coef_table,
                         diagnostics={"method": "Event Study", "n_obs": int(model.nobs),
                                      "event_window": event_window, "base_period": base_period})
    result["path"] = save_results("staggered_did", result)
    return result
