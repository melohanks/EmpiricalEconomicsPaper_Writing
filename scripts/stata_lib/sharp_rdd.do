/*===========================================================================
 * Sharp RDD（精确断点回归）
 * 用法: locals: y_var, running_var, cutoff, [poly_order=1], [kernel=triangular]
 *===========================================================================*/

* 安装依赖包（首次运行）
* ssc install rdrobust, replace
* ssc install rddensity, replace

* 1. McCrary 密度检验（断点处无操纵）
rddensity `running_var', c(`cutoff') plot
graph export "workspace/regression/rdd_mccrary.png", replace

* 2. 协变量平衡性检验
* 此处需要列出前定协变量
* foreach v in age size roa { rddensity `v', c(`cutoff') }

* 3. 主回归：Sharp RDD
rdrobust `y_var' `running_var', c(`cutoff') p(`poly_order') kernel(`kernel')
estimates store rdd_main

* 4. 不同带宽稳健性检验
rdrobust `y_var' `running_var', c(`cutoff') p(`poly_order') h(0.5)
estimates store rdd_h05
rdrobust `y_var' `running_var', c(`cutoff') p(`poly_order') h(1.5)
estimates store rdd_h15

* 5. 图形展示
rdplot `y_var' `running_var', c(`cutoff') p(`poly_order') ///
    graph_options(title("RDD: `y_var' vs `running_var'") ///
    xtitle("`running_var'") ytitle("`y_var'"))
graph export "workspace/regression/rdd_plot.png", replace
