"""生成智慧城市试点 .do 文件"""
b1 = ['北京市','天津市','上海市','石家庄市','秦皇岛市','廊坊市','邯郸市',
      '太原市','长治市','阳泉市','晋城市','乌海市','沈阳市','大连市',
      '辽源市','哈尔滨市','齐齐哈尔市','牡丹江市','南京市','无锡市',
      '常州市','苏州市','镇江市','扬州市','泰州市','南通市','杭州市',
      '宁波市','温州市','嘉兴市','绍兴市','金华市','合肥市','芜湖市',
      '蚌埠市','淮南市','福州市','厦门市','南昌市','济南市','青岛市',
      '烟台市','潍坊市','威海市','郑州市','武汉市','长沙市','株洲市',
      '广州市','深圳市','珠海市','佛山市','南宁市','柳州市','桂林市',
      '重庆市','成都市','绵阳市','贵阳市','遵义市','昆明市','西安市',
      '咸阳市','宝鸡市','兰州市','银川市','乌鲁木齐市','克拉玛依市']

b2 = ['武清区','迁安市','保定市','朔州市','怀仁县','呼伦贝尔市','鄂尔多斯市',
      '包头市','营口市','庄河市','磐石市','四平市','榆树市','肇东市',
      '肇源县','桦南县','安达市','丹阳市','昆山市','徐州市','连云港市',
      '诸暨市','临安市','铜陵市','阜阳市','黄山市','淮北市','亳州市',
      '南平市','莆田市','萍乡市','新余市','樟树市','共青城市','东营市',
      '德州市','新泰市','临沂市','寿光市','昌邑市','肥城市','曲阜市',
      '鹤壁市','漯河市','济源市','新郑市','许昌市','舞钢市','灵宝市',
      '黄冈市','咸宁市','宜昌市','襄阳市','仙桃市','韶山市','浏阳市',
      '贵港市','万宁市','雅安市','遂宁市','崇州市','铜仁市','六盘水市',
      '毕节市','凯里市','渭南市','延安市','金昌市','白银市','陇南市',
      '敦煌市','吴忠市','石嘴山市','库尔勒市','奎屯市','伊宁市',
      '石河子市','大理市']

b3 = ['忻州市','呼和浩特市','新民市','通化市','临江市','佳木斯市','尚志市',
      '东台市','常熟市','温岭市','富阳市','宿州市','滁州市','长乐市',
      '泉州市','鹰潭市','吉安市','莱芜市','章丘市','诸城市','莱西市',
      '开封市','南阳市','荆州市','常德市','沅江市','钦州市','玉林市',
      '广安市','泸州市','乐山市','文山市','玉溪市','汉中市','张掖市',
      '天水市','格尔木市','中卫市','昌吉市','五家渠市','大兴区',
      '门头沟','唐山市','大同市','吕梁市','白山市']

lines = []
lines.append('/* 智慧城市试点 → 企业长期投资 */')
lines.append('clear all')
lines.append('set more off')
lines.append('capture log close')
lines.append('log using "workspace/regression/log/master_smartcity.log", text replace')
lines.append('use "D:\\\\Download\\\\中国上市公司企业面板数据1350+变量1990-2022年.dta", clear')
lines.append('keep if year >= 2007 & year <= 2021')
lines.append('keep if Aonly_13 == 1')
lines.append('drop if Sicmen_str == "J"')
lines.append('drop if IsSTPT == 1')
lines.append('drop if missing(invt) | missing(size) | missing(roa) | missing(city_reg)')
lines.append('display "样本: " _N')
lines.append('encode city_reg, gen(city_id)')
lines.append('xtset id year')
lines.append('gen treat_city = 0')
lines.append('gen first_batch = .')

for c in b1:
    lines.append(f'replace treat_city = 1 if strpos(city_reg, "{c}") > 0')
    lines.append(f'replace first_batch = 2012 if strpos(city_reg, "{c}") > 0 & missing(first_batch)')

for c in b2:
    lines.append(f'replace treat_city = 1 if strpos(city_reg, "{c}") > 0')
    lines.append(f'replace first_batch = 2013 if strpos(city_reg, "{c}") > 0 & missing(first_batch)')

for c in b3:
    lines.append(f'replace treat_city = 1 if strpos(city_reg, "{c}") > 0')
    lines.append(f'replace first_batch = 2014 if strpos(city_reg, "{c}") > 0 & missing(first_batch)')

lines.append('gen post = (year >= first_batch) if !missing(first_batch)')
lines.append('replace post = 0 if missing(post)')
lines.append('gen SmartCity = treat_city * post')
lines.append('tab first_batch')
lines.append('count if SmartCity == 1')
lines.append('display "SmartCity=1: " r(N)')
lines.append('gen LongInvest = invt')
lines.append('gen RD_ratio = RDSpendSumRatio / 100')
lines.append('replace RD_ratio = 0 if missing(RD_ratio)')
lines.append('gen ln_patent = ln(1 + Invention_sum)')
lines.append('gen fin_constraint = banklev')
lines.append('gen manage_cost = F051801B')
lines.append('gen lt_debt = F011301A')
lines.append('gen lev = F011201A')
lines.append('gen growth = F081601B')
lines.append('replace growth = 0 if missing(growth)')
lines.append('gen cash_ratio = cash')
lines.append('gen fixed_asset = F030801A')
lines.append('gen firm_age = age')
lines.append('gen ln_age = lnage')
lines.append('gen SOE = (govcon1 == 1)')
lines.append('gen high_tech = 0')
lines.append('replace high_tech = 1 if Sicmen_str == "C" & inrange(substr(Sicda_str,1,2), "27", "40")')
lines.append('replace high_tech = 1 if Sicmen_str == "I"')
lines.append('gen region = 1')
lines.append('replace region = 2 if inlist(prov_reg, "山西省","吉林省","黑龙江省","安徽省","江西省","河南省","湖北省","湖南省")')
lines.append('replace region = 3 if inlist(prov_reg, "内蒙古自治区","广西壮族自治区","重庆市","四川省","贵州省","云南省","西藏自治区","陕西省","甘肃省","青海省","宁夏回族自治区","新疆维吾尔自治区")')
lines.append('foreach v in LongInvest RD_ratio ln_patent fin_constraint manage_cost lt_debt lev growth cash_ratio fixed_asset size roa tobin {')
lines.append('  capture { _pctile `v\', p(1 99) }')
lines.append('  capture { replace `v\' = r(r1) if `v\' < r(r1) & !missing(`v\') }')
lines.append('  capture { replace `v\' = r(r2) if `v\' > r(r2) & !missing(`v\') }')
lines.append('}')
lines.append('save "workspace/data/smartcity_analysis.dta", replace')
lines.append('log close')

with open('workspace/regression/do/01_master_smartcity.do', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f'Done: {len(lines)} lines')
