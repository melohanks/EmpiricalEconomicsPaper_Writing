"""
Phase C: 计量回归代码生成与运行技能。
根据选定的模型和变量，生成标准化回归代码（statsmodels），
运行并解读结果。
"""
import os
import json
import subprocess
import pandas as pd
import numpy as np
from skills.base import BaseSkill


class RegressionRunner(BaseSkill):
    def __init__(self):
        super().__init__(
            name="RegressionRunner",
            description="计量回归代码生成、运行与结果解读"
        )
        self._data_dir = os.path.abspath("workspace/data")
        self._output_dir = os.path.abspath("workspace/regression")

    def execute(self, action: str, **kwargs):
        # 传统方法
        if action == "descriptive_stats":
            return self._descriptive_stats(**kwargs)
        elif action == "baseline_regression":
            return self._baseline_regression(**kwargs)
        elif action == "diagnose":
            return self._diagnose(**kwargs)
        elif action == "robustness":
            return self._robustness(**kwargs)
        elif action == "mechanism":
            return self._mechanism_test(**kwargs)
        elif action == "heterogeneity":
            return self._heterogeneity_test(**kwargs)
        # 代码库路由 (regression_lib)
        elif action in ("panel_fe", "sharp_rdd", "staggered_did", "iv_2sls",
                        "mediation_lib", "heterogeneity_lib", "robustness_lib",
                        "diagnostics_lib"):
            return self._run_from_lib(action, **kwargs)
        # 通用：按蓝图自动路由
        elif action == "auto":
            return self._auto_run(**kwargs)
        else:
            raise NotImplementedError(f"未实现: {action}。可用: {self.list_actions()}")

    @staticmethod
    def list_actions():
        return ["descriptive_stats", "baseline_regression", "diagnose",
                "robustness", "mechanism", "heterogeneity",
                "panel_fe", "sharp_rdd", "staggered_did", "iv_2sls",
                "mediation_lib", "heterogeneity_lib", "robustness_lib",
                "diagnostics_lib", "auto"]

    def _run_from_lib(self, action: str, **kwargs):
        """从标准化代码库加载并运行模型"""
        import importlib
        lib_map = {
            "panel_fe": "regression_lib.panel_fe",
            "sharp_rdd": "regression_lib.sharp_rdd",
            "staggered_did": "regression_lib.staggered_did",
            "iv_2sls": "regression_lib.iv_2sls",
            "mediation_lib": "regression_lib.mediation",
            "heterogeneity_lib": "regression_lib.heterogeneity",
            "robustness_lib": "regression_lib.robustness",
            "diagnostics_lib": "regression_lib.diagnostics",
        }
        mod = importlib.import_module(lib_map[action])
        result = mod.run(**kwargs)
        if result.get("success"):
            print(f"[{self.name}] {action} 完成 → {result.get('path', 'OK')}")
        else:
            print(f"[{self.name}] {action} 失败: {result.get('summary', '?')}")
        return result

    def _auto_run(self, data_path: str, y_var: str, x_vars: list,
                  blueprint_path: str = None, **kwargs):
        """根据蓝图自动路由模型"""
        models_to_run = ["panel_fe"]
        if blueprint_path and os.path.exists(blueprint_path):
            import re
            with open(blueprint_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "RDD" in content or "断点" in content:
                models_to_run.append("sharp_rdd")
            if "DID" in content or "双重差分" in content:
                models_to_run.append("staggered_did")
            if "IV" in content or "工具变量" in content:
                models_to_run.append("iv_2sls")
        models_to_run += ["mediation_lib", "heterogeneity_lib", "robustness_lib"]
        results = {}
        for m in models_to_run:
            try:
                results[m] = self._run_from_lib(m, data_path=data_path,
                                                y_var=y_var, x_vars=x_vars, **kwargs)
            except Exception as e:
                results[m] = {"success": False, "error": str(e)}
        return results

    def _descriptive_stats(self, data_path: str, variables: dict) -> dict:
        """描述性统计"""
        print(f"\n[{self.name}] 正在计算描述性统计...")

        if not os.path.exists(data_path):
            return {"success": False, "error": f"数据文件不存在: {data_path}"}

        try:
            df = pd.read_csv(data_path)
            stats = df.describe().to_string()
            print(f"[{self.name}] 样本量: {len(df)}, 变量数: {len(df.columns)}")

            os.makedirs(self._output_dir, exist_ok=True)
            path = os.path.join(self._output_dir, "descriptive_stats.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"样本量: {len(df)}\n")
                f.write(f"变量数: {len(df.columns)}\n\n")
                f.write(stats)

            return {"success": True, "n_obs": len(df), "n_vars": len(df.columns),
                    "summary": stats, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _baseline_regression(self, data_path: str, y_var: str, x_vars: list,
                             controls: list = None, fe_cols: list = None) -> dict:
        """基准回归（使用statsmodels）"""
        print(f"\n[{self.name}] 正在运行基准回归: {y_var} ~ {x_vars}")

        if not os.path.exists(data_path):
            return {"success": False, "error": f"数据文件不存在: {data_path}"}

        try:
            import statsmodels.api as sm
            df = pd.read_csv(data_path)

            # 构建回归变量
            all_x = x_vars + (controls or [])
            # 加入固定效应（如有）
            if fe_cols:
                for fe in fe_cols:
                    if fe in df.columns:
                        dummies = pd.get_dummies(df[fe], prefix=fe, drop_first=True)
                        df = pd.concat([df, dummies], axis=1)
                        all_x.extend([c for c in dummies.columns if c not in all_x])

            X = df[all_x].dropna()
            y = df[y_var].loc[X.index]
            X = sm.add_constant(X)

            model = sm.OLS(y, X).fit()
            summary = model.summary().as_text()

            os.makedirs(self._output_dir, exist_ok=True)
            path = os.path.join(self._output_dir, "baseline_regression.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(summary)

            # 提取关键指标
            key_stats = {
                "r_squared": model.rsquared,
                "n_obs": int(model.nobs),
                "f_statistic": model.fvalue,
                "f_pvalue": model.f_pvalue,
            }
            # 提取核心变量的系数和p值
            coef_info = {}
            for var in x_vars + ["const"]:
                if var in model.params.index:
                    coef_info[var] = {
                        "coef": model.params[var],
                        "pvalue": model.pvalues[var],
                        "significant": model.pvalues[var] < 0.05,
                    }

            print(f"[{self.name}] R²={model.rsquared:.3f}, N={int(model.nobs)}")
            for v, info in coef_info.items():
                sig = "***" if info["pvalue"] < 0.01 else ("**" if info["pvalue"] < 0.05 else ("*" if info["pvalue"] < 0.1 else ""))
                print(f"  {v}: {info['coef']:.4f} (p={info['pvalue']:.4f}) {sig}")

            return {
                "success": True, "summary": summary, "path": path,
                "key_stats": key_stats, "coef_info": coef_info,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _diagnose(self, data_path: str, y_var: str, x_vars: list) -> dict:
        """诊断不显著的可能原因"""
        print(f"\n[{self.name}] 正在诊断回归结果不显著的可能原因...")
        issues = []

        if not os.path.exists(data_path):
            return {"success": False, "error": f"数据不存在: {data_path}"}

        try:
            import statsmodels.api as sm
            from statsmodels.stats.outliers_influence import variance_inflation_factor

            df = pd.read_csv(data_path)
            X = df[x_vars].dropna()
            X = sm.add_constant(X)

            # 1. VIF多重共线性检查
            try:
                vif_data = pd.DataFrame({
                    "variable": X.columns,
                    "VIF": [variance_inflation_factor(X.values, i) for i in range(X.shape[1])]
                })
                high_vif = vif_data[vif_data["VIF"] > 10]
                if len(high_vif) > 0:
                    issues.append(f"多重共线性: {len(high_vif)} 个变量VIF>10 → {list(high_vif['variable'])}")
            except Exception:
                pass

            # 2. 异常值检查
            for v in x_vars:
                if v in df.columns:
                    q1, q3 = df[v].quantile([0.25, 0.75])
                    iqr = q3 - q1
                    outliers = ((df[v] < q1 - 3*iqr) | (df[v] > q3 + 3*iqr)).sum()
                    if outliers > len(df) * 0.05:
                        issues.append(f"异常值: {v} 有 {outliers} 个极端值 (>3IQR)，建议缩尾处理")

            # 3. 样本量检查
            if len(df) < 100:
                issues.append(f"样本量过小: 仅 {len(df)} 个观测")

            suggestions = [
                "1. 检查核心变量的测量误差（是否使用了合适的代理变量？）",
                "2. 尝试不同的固定效应组合",
                "3. 缩尾处理（winsorize 1%）",
                "4. 检查是否存在遗漏的重要控制变量",
                "5. 考虑非线性关系（对数变换/平方项）",
            ]

            return {"success": True, "issues": issues, "suggestions": suggestions}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _robustness(self, data_path: str, y_var: str, x_vars: list,
                    controls: list = None) -> dict:
        """稳健性检验"""
        print(f"\n[{self.name}] 正在运行稳健性检验...")

        results = []
        try:
            import statsmodels.api as sm
            df = pd.read_csv(data_path)

            all_x = x_vars + (controls or [])
            subset = df[all_x + [y_var]].dropna()
            X = sm.add_constant(subset[all_x])
            y = subset[y_var]
            m0 = sm.OLS(y, X).fit()

            # 检验1: 缩尾1%
            for v in all_x + [y_var]:
                if v in df.columns:
                    q1, q99 = df[v].quantile([0.01, 0.99])
                    df[v + "_w"] = df[v].clip(q1, q99)

            wx = [v + "_w" if v + "_w" in df.columns else v for v in all_x]
            wy = y_var + "_w" if y_var + "_w" in df.columns else y_var
            wdf = df[wx + [wy]].dropna()
            Xw = sm.add_constant(wdf[wx])
            yw = wdf[wy]
            m1 = sm.OLS(yw, Xw).fit()
            results.append({
                "test": "缩尾1%",
                "base_coef": m0.params.get(x_vars[0] if x_vars else "", None),
                "test_coef": m1.params.get(x_vars[0] + "_w" if x_vars[0] + "_w" in Xw.columns else x_vars[0], None),
                "stable": abs(m0.params.get(x_vars[0], 0) - m1.params.get(x_vars[0], 0)) < abs(m0.params.get(x_vars[0], 0)) * 0.5
            })

            return {"success": True, "results": results, "n_tests": len(results)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _mechanism_test(self, data_path: str, y_var: str, x_var: str,
                        mediators: list, controls: list = None) -> dict:
        """中介效应检验（三步法）"""
        results = []
        try:
            import statsmodels.api as sm
            df = pd.read_csv(data_path)

            for med in mediators:
                # Step 1: X→Y (total effect)
                Xy = df[[x_var] + (controls or []) + [y_var]].dropna()
                m1 = sm.OLS(Xy[y_var], sm.add_constant(Xy[[x_var] + (controls or [])])).fit()
                c = m1.params[x_var]

                # Step 2: X→M
                Xm = df[[x_var] + (controls or []) + [med]].dropna()
                m2 = sm.OLS(Xm[med], sm.add_constant(Xm[[x_var] + (controls or [])])).fit()
                a = m2.params[x_var]

                # Step 3: X+M→Y
                Xmy = df[[x_var, med] + (controls or []) + [y_var]].dropna()
                m3 = sm.OLS(Xmy[y_var], sm.add_constant(Xmy[[x_var, med] + (controls or [])])).fit()
                b = m3.params[med]
                c_prime = m3.params[x_var]

                # 简单Sobel检验（近似）
                mediation_ratio = (a * b) / c if c != 0 else 0

                results.append({
                    "mediator": med,
                    "total_effect_c": c,
                    "a_path": a,
                    "b_path": b,
                    "direct_effect_c_prime": c_prime,
                    "mediation_ratio": mediation_ratio,
                    "mediation_significant": abs(a * b / (c - c_prime + 1e-10)) > 1.96 if (c - c_prime) != 0 else False,
                })

            print(f"[{self.name}] 中介效应检验完成: {len(results)} 个中介变量")
            return {"success": True, "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _heterogeneity_test(self, data_path: str, y_var: str, x_var: str,
                            group_var: str, controls: list = None) -> dict:
        """异质性检验（分组回归）"""
        try:
            import statsmodels.api as sm
            df = pd.read_csv(data_path)

            results = []
            for gname, gdf in df.groupby(group_var):
                if len(gdf) < 30:
                    continue
                X = sm.add_constant(gdf[[x_var] + (controls or [])].dropna())
                y = gdf[y_var].loc[X.index]
                m = sm.OLS(y, X).fit()
                results.append({
                    "group": gname,
                    "n": len(gdf),
                    "coef": m.params.get(x_var, None),
                    "pvalue": m.pvalues.get(x_var, None),
                    "significant": m.pvalues.get(x_var, 1) < 0.05,
                })

            return {"success": True, "group_var": group_var, "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}
