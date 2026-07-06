/*===========================================================================
 * 面板双向固定效应模型
 * 用法: 在调用前设置 locals: y_var, x_vars, controls, entity_var, time_var
 *===========================================================================*/

* 数据加载（用户自定义）
* use "workspace/data/your_data.dta", clear

* 设定面板结构
xtset `entity_var' `time_var'

* 描述性统计
summarize `y_var' `x_vars' `controls'

* 基准回归：双向固定效应
xtreg `y_var' `x_vars' `controls', fe
estimates store baseline_fe

* 输出结果
esttab baseline_fe using "workspace/regression/panel_fe_results.csv", ///
    replace star(* 0.10 ** 0.05 *** 0.01) stats(N r2, fmt(%9.0f %9.3f))

* 备选：加入时间固定效应
reghdfe `y_var' `x_vars' `controls', absorb(`entity_var' `time_var') cluster(`entity_var')
estimates store twfe

* 对比
estimates table baseline_fe twfe, star stats(N r2)
