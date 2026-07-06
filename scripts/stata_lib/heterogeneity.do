/*===========================================================================
 * 异质性分析（分组回归 + 交互项）
 * 用法: locals: y_var, x_var, group_var, [controls]
 *===========================================================================*/

* === 方法一：分组回归 ===
display _n "========== 分组回归: `group_var' =========="

levelsof `group_var', local(groups)
foreach g of local groups {
    display _n "--- 组: `group_var' = `g' ---"
    reg `y_var' `x_var' `controls' if `group_var' == `g', robust
    estimates store group_`g'
}

* 组间系数差异检验（Chow test / 似无相关检验）
* suest group_0 group_1
* test [group_0_mean]`x_var' = [group_1_mean]`x_var'

* === 方法二：交互项 ===
display _n "========== 交互项模型 =========="
gen interact_`x_var'_`group_var' = `x_var' * `group_var'
reg `y_var' `x_var' `group_var' interact_`x_var'_`group_var' `controls', robust
estimates store interact_model

* 输出汇总表
estimates table group_* interact_model, star stats(N r2)
