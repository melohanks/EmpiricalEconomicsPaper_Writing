"""
计量模型基类：数据加载、结果保存、格式化输出
"""
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "workspace/regression"))


def load_data(data_path: str) -> pd.DataFrame:
    """加载数据，自动检测编码和格式"""
    if data_path.endswith(".csv"):
        for enc in ["utf-8", "gbk", "gb2312", "utf-8-sig"]:
            try:
                return pd.read_csv(data_path, encoding=enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
        return pd.read_csv(data_path, encoding="utf-8", errors="replace")
    elif data_path.endswith((".xlsx", ".xls")):
        return pd.read_excel(data_path)
    elif data_path.endswith(".dta"):
        return pd.read_stata(data_path)
    else:
        raise ValueError(f"不支持的文件格式: {data_path}")


def save_results(model_name: str, result: dict) -> str:
    """保存结果为 JSON + TXT"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(OUTPUT_DIR, f"{model_name}_{ts}")

    # 保存 JSON（处理 numpy 类型）
    def _json_safe(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (pd.Timestamp,)):
            return str(obj)
        return str(obj)

    json_path = base + ".json"
    serializable = {}
    for k, v in result.items():
        if v is None or isinstance(v, (str, int, float, bool)):
            serializable[k] = v
        elif isinstance(v, (np.integer,)):
            serializable[k] = int(v)
        elif isinstance(v, (np.floating,)):
            serializable[k] = float(v)
        elif isinstance(v, np.ndarray):
            serializable[k] = v.tolist()
        elif isinstance(v, dict):
            serializable[k] = {sk: _json_safe(sv) for sk, sv in v.items()}
        elif isinstance(v, (list, tuple)):
            serializable[k] = [_json_safe(sv) for sv in v]
        elif isinstance(v, pd.DataFrame):
            serializable[k] = v.to_dict(orient="records")
        elif isinstance(v, (pd.Timestamp,)):
            serializable[k] = str(v)
        else:
            serializable[k] = str(v)[:500]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)

    # 保存文本摘要
    txt_path = base + ".txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"模型: {model_name}\n")
        f.write(f"时间: {ts}\n")
        f.write("=" * 60 + "\n")
        f.write(result.get("summary", ""))
        if result.get("coef_table"):
            f.write("\n\n" + str(result["coef_table"]))

    return base


def winsorize(series: pd.Series, pct: float = 0.01) -> pd.Series:
    """缩尾处理"""
    lo, hi = series.quantile(pct), series.quantile(1 - pct)
    return series.clip(lo, hi)


def make_result(success: bool, model_name: str, summary: str = "",
                coef_table: pd.DataFrame = None, tables: dict = None,
                diagnostics: dict = None, **kwargs) -> dict:
    """构造标准返回 dict"""
    r = {"success": success, "model_name": model_name, "summary": summary}
    if coef_table is not None:
        r["coef_table"] = coef_table.to_dict(orient="records") if hasattr(coef_table, "to_dict") else coef_table
    if tables:
        r["tables"] = tables
    if diagnostics:
        r["diagnostics"] = diagnostics
    r.update(kwargs)
    return r
