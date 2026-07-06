/*===========================================================================
 * 工具变量法 (IV-2SLS)
 * 用法: locals: y_var, x_vars, iv_vars, [controls]
 *===========================================================================*/

* 第一阶段：X ~ IV + Controls
* 如 x_vars 只有一个内生变量 PCapital，iv_vars 有一个 iv_peer
foreach x of local x_vars {
    reg `x' `iv_vars' `controls', robust
    estimates store first_`x'
    test `iv_vars'  // 弱工具变量检验
    local f_stat = e(F)
    display "第一阶段F统计量: " `f_stat'
}

* 第二阶段：2SLS
ivregress 2sls `y_var' `controls' (`x_vars' = `iv_vars'), robust
estimates store iv_results

* 输出汇总表
estimates table first_* iv_results, star stats(N F)

* 弱工具变量诊断
* 如果安装了 weakiv：
* weakiv ivregress 2sls `y_var' `controls' (`x_vars' = `iv_vars')
