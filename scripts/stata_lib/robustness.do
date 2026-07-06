/*===========================================================================
 * 稳健性检验套件
 * 用法: locals: y_var, x_var, controls, y_alt, x_alt, exclude_cond, winsor_pct
 *===========================================================================*/

local pct = cond("`winsor_pct'" == "", "1", "`winsor_pct'")

* 1. 基准回归
reg `y_var' `x_var' `controls', robust
estimates store base
display "基准: `x_var' coef = " _b[`x_var']

* 2. 缩尾处理
foreach v in `y_var' `x_var' `controls' {
    capture winsor2 `v', replace cuts(1 99)
}
reg `y_var' `x_var' `controls', robust
estimates store winsor
display "缩尾: `x_var' coef = " _b[`x_var']

* 3. 替换Y（如果有备选测度）
capture {
    reg `y_alt' `x_var' `controls', robust
    estimates store y_alt
    display "替换Y(`y_alt'): `x_var' coef = " _b[`x_var']
}

* 4. 替换X（如果有备选测度）
capture {
    reg `y_var' `x_alt' `controls', robust
    estimates store x_alt
    display "替换X(`x_alt'): `x_alt' coef = " _b[`x_alt']
}

* 5. 排除特定样本（如果有条件）
capture {
    preserve
    drop if `exclude_cond'
    reg `y_var' `x_var' `controls', robust
    estimates store exclude
    display "排除后: `x_var' coef = " _b[`x_var']
    restore
}

* 6. 增减控制变量
capture {
    reg `y_var' `x_var', robust
    estimates store no_ctrl
    display "无控制变量: `x_var' coef = " _b[`x_var']
}

* 汇总对比表
estimates table base winsor, star stats(N r2)
