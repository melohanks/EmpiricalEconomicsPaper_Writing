/*===========================================================================
 * Staggered DID（渐进双重差分）/ Event Study
 * 用法: locals: y_var, treat_var, time_var, first_treat_var, [controls]
 *===========================================================================*/

* 安装依赖包
* ssc install eventstudyinteract, replace
* ssc install did_multiplegt, replace

* 1. 传统 TWFE
xtset `entity_var' `time_var'
xtreg `y_var' `treat_var' `controls' i.`time_var', fe cluster(`entity_var')
estimates store twfe_baseline

* 2. Event Study（动态处理效应）
* 构造相对时间变量
gen event_time = `time_var' - `first_treat_var'
replace event_time = -99 if missing(`first_treat_var')

* 设定事件窗口
local pre_min = -5
local post_max = 5

* 生成事件虚拟变量
forvalues t = `pre_min'/`post_max' {
    if `t' != -1 {
        gen event_`t' = (event_time == `t')
    }
}

* Event Study 回归（基准期 t=-1）
xtreg `y_var' event_* `controls' i.`time_var', fe cluster(`entity_var')
estimates store event_study

* 绘制动态效应图
coefplot event_study, drop(_cons `controls' *`time_var') ///
    vertical yline(0) xline(10.5) ///
    title("Event Study: Dynamic Treatment Effects") ///
    ytitle("Coefficient") xtitle("Periods Relative to Treatment")
graph export "workspace/regression/event_study.png", replace

* 3. Sun & Abraham (2021) 估计量（推荐）
* eventstudyinteract `y_var' event_*, ///
*     cohort(`first_treat_var') control_cohort(never) ///
*     absorb(`entity_var' `time_var') vce(cluster `entity_var')
