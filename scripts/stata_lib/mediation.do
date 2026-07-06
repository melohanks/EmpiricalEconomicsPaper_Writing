/*===========================================================================
 * 中介效应检验（三步法 + Sobel + Bootstrap）
 * 用法: locals: y_var, x_var, mediators (空格分隔), [controls]
 *===========================================================================*/

* 安装依赖
* ssc install sgmediation, replace
* ssc install boottest, replace

local med_count: word count `mediators'

foreach med of local mediators {
    display _n "========== 中介变量: `med' =========="

    * Step 1: X → Y（总效应 c）
    reg `y_var' `x_var' `controls', robust
    estimates store step1_`med'
    local c = _b[`x_var']
    local se_c = _se[`x_var']
    display "Step 1: 总效应 c = " `c' " (se=" `se_c' ")"

    * Step 2: X → M（路径 a）
    reg `med' `x_var' `controls', robust
    estimates store step2_`med'
    local a = _b[`x_var']
    local se_a = _se[`x_var']
    display "Step 2: 路径 a = " `a' " (se=" `se_a' ")"

    * Step 3: X + M → Y（路径 b, 直接效应 c'）
    reg `y_var' `x_var' `med' `controls', robust
    estimates store step3_`med'
    local b = _b[`med']
    local se_b = _se[`med']
    local c_prime = _b[`x_var']
    display "Step 3: 路径 b = " `b' " (se=" `se_b' ")"
    display "       直接效应 c' = " `c_prime'

    * 间接效应
    local ab = `a' * `b'
    display "间接效应 a*b = " `ab'

    * Sobel 检验
    local sobel_se = sqrt(`a'^2 * `se_b'^2 + `b'^2 * `se_a'^2)
    local sobel_z = `ab' / `sobel_se'
    local sobel_p = 2 * (1 - normal(abs(`sobel_z')))
    display "Sobel Z = " %9.4f `sobel_z' " (p = " %6.4f `sobel_p' ")"

    * 中介效应占比
    local ratio = `ab' / `c' * 100
    display "中介效应占比: " %5.1f `ratio' "%"
}

* 输出汇总表
estimates table step1_* step2_* step3_*, star stats(N r2)
