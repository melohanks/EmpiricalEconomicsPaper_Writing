"""
计量模型代码库 — 标准化、可插拔的计量回归模块

每个模块提供统一的 run() 函数：
    run(data_path, y_var, x_vars, **kwargs) -> dict

返回 dict 结构：
    {success, model_name, summary, tables, coef_table, diagnostics, path, figure_paths}
"""

# 模型注册表：模型名 → 模块
MODEL_REGISTRY = {
    "panel_fe":           "regression_lib.panel_fe",
    "sharp_rdd":          "regression_lib.sharp_rdd",
    "staggered_did":      "regression_lib.staggered_did",
    "iv_2sls":            "regression_lib.iv_2sls",
    "mediation":          "regression_lib.mediation",
    "heterogeneity":      "regression_lib.heterogeneity",
    "robustness":         "regression_lib.robustness",
    "diagnostics":        "regression_lib.diagnostics",
}

# 论文蓝图 → 默认模型映射
BLUEPRINT_TO_MODELS = {
    "baseline":   "panel_fe",
    "main":       "sharp_rdd",
    "mechanism":  "mediation",
    "robustness": "robustness",
    "heterogeneity": "heterogeneity",
    "diagnostics": "diagnostics",
}


def get_model(model_name: str):
    """根据模型名加载对应模块"""
    import importlib
    module_path = MODEL_REGISTRY.get(model_name)
    if not module_path:
        raise ValueError(f"未知模型: {model_name}。可选: {list(MODEL_REGISTRY.keys())}")
    return importlib.import_module(module_path)


def list_models():
    """列出所有可用模型"""
    return list(MODEL_REGISTRY.keys())


def run_model(model_name: str, data_path: str, y_var: str = None,
              x_vars: list = None, **kwargs) -> dict:
    """统一入口：按模型名运行回归。y_var/x_vars 可为 None（由模块自行处理默认值）"""
    mod = get_model(model_name)
    call_kwargs = {"data_path": data_path}
    if y_var is not None:
        call_kwargs["y_var"] = y_var
    if x_vars is not None:
        call_kwargs["x_vars"] = x_vars
    call_kwargs.update(kwargs)
    return mod.run(**call_kwargs)
