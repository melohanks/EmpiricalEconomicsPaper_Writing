/*===========================================================================
 * 模型诊断套件
 * 用法: locals: y_var, x_vars, controls
 *===========================================================================*/

* 1. VIF 多重共线性
display _n "========== VIF 多重共线性检验 =========="
reg `y_var' `x_vars' `controls'
vif

* 2. 异方差检验 (Breusch-Pagan)
display _n "========== Breusch-Pagan 异方差检验 =========="
reg `y_var' `x_vars' `controls'
estat hettest

* 3. 自相关检验 (Wooldridge, 面板数据)
display _n "========== Wooldridge 自相关检验 =========="
capture {
    xtserial `y_var' `x_vars' `controls'
}

* 4. 描述性统计 + 相关系数矩阵
display _n "========== 描述性统计 =========="
summarize `y_var' `x_vars' `controls', detail

display _n "========== 相关系数矩阵 =========="
pwcorr `y_var' `x_vars' `controls', star(0.05)

* 5. 缩尾前诊断
foreach v in `y_var' `x_vars' `controls' {
    summarize `v', detail
    display "偏度: " r(skewness) "  峰度: " r(kurtosis)
}
