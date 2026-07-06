"""
工具函数：聚类标准误、缩尾、VIF、标准化
"""
import numpy as np
import pandas as pd
from typing import Optional


def cluster_se(model, df: pd.DataFrame, cluster_col: str):
    """
    计算聚类稳健标准误（在已有 statsmodels OLS 结果上）
    需要已安装 statsmodels
    """
    try:
        from statsmodels.iolib.summary2 import summary_col
    except ImportError:
        return model  # 回退：不聚类
    # 简单实现：使用 statsmodels 的 cov_type
    # 实际使用时调用 model.get_robustcov_results(cov_type='cluster', groups=df[cluster_col])
    try:
        return model.get_robustcov_results(cov_type='cluster', groups=df.loc[model.model.endog.index, cluster_col])
    except Exception:
        return model


def compute_vif(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    """计算 VIF 多重共线性"""
    try:
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        import statsmodels.api as sm
        X = sm.add_constant(df[cols].dropna())
        vif_data = pd.DataFrame({
            "variable": X.columns,
            "VIF": [variance_inflation_factor(X.values, i) for i in range(X.shape[1])]
        })
        return vif_data
    except Exception as e:
        return pd.DataFrame({"error": [str(e)]})


def standardize(series: pd.Series) -> pd.Series:
    """标准化 (z-score)"""
    return (series - series.mean()) / series.std()


def iqr_outliers(series: pd.Series, multiplier: float = 3.0) -> pd.Series:
    """标记 IQR 异常值"""
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    return (series < q1 - multiplier * iqr) | (series > q3 + multiplier * iqr)
