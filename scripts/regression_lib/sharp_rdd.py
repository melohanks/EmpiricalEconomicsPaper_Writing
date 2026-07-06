"""
Sharp RDD（精确断点回归）

依赖：rdrobust (pip install rdrobust)
或备选：statsmodels 手动实现

调用示例：
    from regression_lib import run_model
    result = run_model("sharp_rdd", data_path="data.csv", y_var="Chain",
                       x_vars=["Treat"], running_var="firm_age",
                       cutoff=5.0, bandwidth="mserd")
"""
import numpy as np
import pandas as pd
from regression_lib.base import load_data, save_results, make_result


def run(data_path: str, y_var: str = None, x_vars: list = None,
        running_var: str = None, cutoff: float = 0.0,
        bandwidth: str = "mserd", kernel: str = "triangular",
        polynomial_order: int = 1, **kwargs) -> dict:
    """
    Sharp RDD

    Args:
        data_path: CSV 数据路径
        y_var: 被解释变量
        x_vars: （可选）额外的协变量列表
        running_var: 驱动变量（running variable / forcing variable）
        cutoff: 断点值
        bandwidth: 带宽选择方法 — "mserd", "msetwo", "cerrd", 或手动数值
        kernel: 核函数 — "triangular", "uniform", "epanechnikov"
        polynomial_order: 局部多项式阶数，默认1（局部线性回归）
    """
    df = load_data(data_path)

    if running_var is None:
        return make_result(False, "sharp_rdd",
                           summary="请指定 running_var（驱动变量列名）")

    if running_var not in df.columns or (y_var and y_var not in df.columns):
        return make_result(False, "sharp_rdd",
                           summary=f"列不存在。需要: {running_var}, {y_var}")

    # 构造处理变量
    df["_rd_treat"] = (df[running_var] >= cutoff).astype(int)
    df["_rd_centered"] = df[running_var] - cutoff

    n_total = len(df)
    n_treat = df["_rd_treat"].sum()
    n_control = n_total - n_treat

    # 尝试使用 rdrobust 包（首选）
    try:
        import rdrobust
        y = df[y_var].values
        x = df[running_var].values

        if isinstance(bandwidth, str):
            result_rd = rdrobust.rdrobust(y=y, x=x, c=cutoff,
                                          kernel=kernel, p=polynomial_order,
                                          bwselect=bandwidth)
        else:
            result_rd = rdrobust.rdrobust(y=y, x=x, c=cutoff,
                                          kernel=kernel, p=polynomial_order,
                                          h=bandwidth)

        # 提取结果（numpy 数组 → Python 标量）
        def _scalar(val, default=np.nan):
            if val is None:
                return default
            try:
                if hasattr(val, 'ndim') and val.ndim == 0:
                    return float(val)
                if hasattr(val, '__len__') and len(val) == 1:
                    return float(val[0])
                return float(val)
            except (TypeError, ValueError, IndexError):
                return default

        coef = _scalar(result_rd.coef[0] if len(result_rd.coef) > 0 else None)
        se = _scalar(result_rd.se[0] if len(result_rd.se) > 0 else None)
        pval = _scalar(result_rd.pv[0] if len(result_rd.pv) > 0 else None)
        bw_left = _scalar(result_rd.bws[0, 0] if hasattr(result_rd.bws, 'shape') else result_rd.bws[0])
        bw_right = _scalar(result_rd.bws[0, 1] if hasattr(result_rd.bws, 'shape') and result_rd.bws.shape[1] > 1 else bw_left)
        n_eff_val = _scalar((result_rd.N_h[0] + result_rd.N_h[1]) if len(result_rd.N_h) >= 2 else n_total, 0)
        n_eff = int(n_eff_val) if not np.isnan(n_eff_val) else 0
        method = "rdrobust"
    except ImportError:
        # 备选：带宽内局部线性 OLS（无需 rdrobust）
        method = "OLS (带宽内局部线性)"
        h = bandwidth if isinstance(bandwidth, (int, float)) else _estimate_bandwidth(df, running_var)
        bw_left = bw_right = float(h)

        # 断点附近样本（带宽内）
        near = df[df["_rd_centered"].abs() <= h]
        if len(near) > 30:
            # 简单 OLS: Y ~ treat + centered + treat*centered
            import statsmodels.api as sm
            X_near = sm.add_constant(near[["_rd_treat", "_rd_centered"]].assign(
                _interact=near["_rd_treat"] * near["_rd_centered"]
            ))
            y_near = near[y_var]
            model_near = sm.OLS(y_near, X_near).fit()
            coef = float(model_near.params.get("_rd_treat", np.nan))
            se = float(model_near.bse.get("_rd_treat", np.nan))
            pval = float(model_near.pvalues.get("_rd_treat", np.nan))
            n_eff = len(near)
        else:
            coef = np.nan
            se = np.nan
            pval = np.nan
            n_eff = 0
        method = "statsmodels.KernelReg (备选，无统计推断)"

    # 构建系数表（_scalar 已在上面定义，确保所有值为 Python 标量）
    coef_table = pd.DataFrame([{
        "variable": running_var,
        "coef (LATE)": round(coef, 6) if not np.isnan(coef) else None,
        "std_err": round(se, 6) if not np.isnan(se) else None,
        "p_value": round(pval, 4) if not np.isnan(pval) else None,
        "bandwidth_left": round(bw_left, 4) if not np.isnan(bw_left) else None,
        "bandwidth_right": round(bw_right, 4) if not np.isnan(bw_right) else None,
        "N_effective": n_eff,
    }])

    summary = f"""=== Sharp RDD ===
驱动变量: {running_var} | 断点: {cutoff}
方法: {method} | 核: {kernel} | 多项式阶: {polynomial_order}
总样本: {n_total} (处理组: {n_treat}, 对照组: {n_control})
有效样本: {n_eff} | 带宽: [{bw_left:.4f}, {bw_right:.4f}]
LATE (局部平均处理效应): {coef:.4f} (p={pval:.4f})
"""

    result = make_result(
        True, "sharp_rdd", summary=summary, coef_table=coef_table,
        diagnostics={
            "method": method, "n_total": n_total, "n_treat": n_treat,
            "n_control": n_control, "n_effective": n_eff,
            "bandwidth_left": bw_left, "bandwidth_right": bw_right,
            "late": coef if not np.isnan(coef) else None,
        }
    )
    result["path"] = save_results("sharp_rdd", result)
    return result


def _estimate_bandwidth(df: pd.DataFrame, running_var: str) -> float:
    """估计最优带宽（Silverman's rule of thumb）"""
    std = df[running_var].std()
    n = len(df)
    return 1.06 * std * n ** (-1.0 / 5)
