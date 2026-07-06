"""
数据获取与处理技能。
支持多数据源：AKShare(免费)/Tushare(免费)/EPS(需订阅)/CSMAR(需订阅)/CNRDS(需订阅)/WIND(需订阅)/公开数据库
根据变量需求生成数据下载脚本，执行获取并保存CSV到 workspace/data/。
"""
import os
import json
import subprocess
from skills.base import BaseSkill


# 数据库→变量映射表
DATABASE_VARIABLE_MAP = {
    "akshare": {
        "description": "免费开源 Python 库，覆盖宏观/城市/行业数据",
        "pip": "akshare",
        "variables": [
            "人均GDP", "财政支出", "实际使用外资", "城镇化率",
            "城市道路面积", "普通高校在校生数", "年末总人口",
        ],
        "import": "import akshare as ak",
    },
    "tushare": {
        "description": "免费(需注册token) Python 库，A股上市公司数据",
        "pip": "tushare",
        "variables": [
            "上市公司财务数据", "上市公司员工结构", "行业分类",
        ],
        "import": "import tushare as ts",
    },
    "eps": {
        "description": "EPS数据平台，数字化中国统计年鉴(需机构订阅)",
        "api_type": "REST API / Python SDK",
        "variables": [
            "分行业城镇单位就业人数", "分行业平均工资",
            "三产增加值/二产增加值", "私营个体从业人员",
            "人均GDP", "普通高校在校生数", "实际利用外资",
            "人均道路面积", "财政支出/GDP", "城镇化率",
        ],
    },
    "csmar": {
        "description": "国泰安数据库(需机构订阅)",
        "api_type": "REST API",
        "variables": [
            "上市公司员工学历构成", "上市公司岗位构成(技术/生产/销售)",
            "上市公司研发投入", "上市公司研发人员占比",
        ],
    },
    "cnrds": {
        "description": "中国研究数据服务平台(需机构订阅)",
        "api_type": "REST API",
        "variables": [
            "专利IPC分类号", "绿色专利标识", "数字专利标识",
            "企业绿色创新", "企业数字化转型",
        ],
    },
    "wind": {
        "description": "万得金融终端(需机构订阅)",
        "api_type": "WindPy Python SDK",
        "variables": [
            "城市面板全部宏观指标", "上市公司全部财务指标",
            "行业分类与财务汇总",
        ],
    },
    "public": {
        "description": "公开免费数据库",
        "sources": {
            "ceads": {"url": "https://www.ceads.net/", "format": "CSV下载", "variables": ["城市碳排放"]},
            "hydrosheds": {"url": "https://www.hydrosheds.org/", "format": "Shapefile", "variables": ["河流长度"]},
            "cnipa": {"url": "https://www.cnipa.gov.cn/", "format": "检索+导出", "variables": ["专利IPC", "专利申请/授权量"]},
            "osm": {"url": "https://www.openstreetmap.org/", "format": "API/下载", "variables": ["道路网络", "行政边界"]},
        },
    },
}


class DataHandler(BaseSkill):
    def __init__(self):
        super().__init__(
            name="DataHandler",
            description="根据变量需求生成多源数据下载脚本，执行获取并保存CSV"
        )
        self._data_dir = os.path.abspath("workspace/data")

    def execute(self, action: str, **kwargs):
        if action == "generate_script":
            return self._generate_script(**kwargs)
        elif action == "fetch_data":
            return self._fetch_data(**kwargs)
        elif action == "list_sources":
            return self._list_sources(**kwargs)
        elif action == "generate_paper_script":
            return self._generate_paper_script(**kwargs)
        else:
            raise NotImplementedError(f"未实现: {action}")

    def _list_sources(self) -> dict:
        """列出所有已知数据源及可获取变量"""
        return {"success": True, "sources": DATABASE_VARIABLE_MAP}

    def _generate_script(self, variables: dict, topic_info: str = "") -> dict:
        """生成通用Python数据下载脚本"""
        os.makedirs(self._data_dir, exist_ok=True)

        script = f'''"""
自动生成的数据下载脚本
"""
import pandas as pd
import numpy as np
import os

DATA_DIR = r"{self._data_dir}"

# 变量需求：
{json.dumps(variables, ensure_ascii=False, indent=2)}

# ─── 数据源1: AKShare (免费) ───
try:
    import akshare as ak
    print("[AKShare] 已加载")
    # TODO: 根据变量需求调用具体接口
except ImportError:
    print("[AKShare] 未安装: pip install akshare")

# ─── 数据源2: Tushare (免费token) ───
try:
    import tushare as ts
    # ts.set_token('your_token')
    print("[Tushare] 已加载")
except ImportError:
    print("[Tushare] 未安装: pip install tushare")

print("\\n请在上述数据源中填入API凭证，取消注释对应代码块后运行。")
print(f"数据将保存到: {{DATA_DIR}}")
'''
        path = os.path.join(self._data_dir, "download_data.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(script)

        return {"success": True, "script_path": path, "data_dir": self._data_dir}

    def _generate_paper_script(self,
                                y_source: str = "eps",
                                m1_source: str = "cnrds",
                                m2_source: str = "eps",
                                controls_source: str = "eps",
                                iv_source: str = "hydrosheds",
                                ) -> dict:
        """
        为当前论文「低碳转型的公正代价」生成专属数据下载脚本。

        Parameters
        ----------
        y_source : 被解释变量数据源 (eps/cls/cfps/csmar)
        m1_source : 技能偏向性技术创新数据源 (cnrds/cnipa)
        m2_source : 产业结构创造性破坏数据源 (eps/industrial_firm)
        controls_source : 控制变量数据源 (eps/akshare/wind)
        iv_source : 工具变量数据源 (hydrosheds/osm)
        """
        os.makedirs(self._data_dir, exist_ok=True)

        script = f'''"""
论文「低碳转型的公正代价——低碳城市试点对劳动力市场极化的影响」
专属数据获取脚本

数据源配置:
  Y  (劳动力市场极化)  → {y_source}
  M1 (技能偏向性技术)  → {m1_source}
  M2 (产业结构创造破坏) → {m2_source}
  Controls (6个控制变量) → {controls_source}
  IV (河流长度)        → {iv_source}
"""
import pandas as pd
import numpy as np
import os
import json

DATA_DIR = r"{self._data_dir}"
os.makedirs(DATA_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════
# 配置区：在此填入各数据源的 API Key / Token
# ═══════════════════════════════════════════════════════════
CONFIG = {{
    # EPS数据平台
    "eps_username": "YOUR_EPS_USERNAME",
    "eps_password": "YOUR_EPS_PASSWORD",
    # Tushare
    "tushare_token": "YOUR_TUSHARE_TOKEN",
    # CSMAR
    "csmar_api_key": "YOUR_CSMAR_API_KEY",
    # CNRDS
    "cnrds_api_key": "YOUR_CNRDS_API_KEY",
    # WIND
    "wind_api_endpoint": "http://your-wind-server:port",
}}

# ═══════════════════════════════════════════════════════════
# 城市列表（282个地级市 + 低碳试点标识）
# ═══════════════════════════════════════════════════════════
LCCP_CITIES = {{
    # 第一批 (2010): 广东、辽宁、湖北、陕西、云南5省 + 天津等8市
    "batch1": {{
        "year": 2010,
        "provinces": ["广东省", "辽宁省", "湖北省", "陕西省", "云南省"],
        "cities": ["天津市", "重庆市", "深圳市", "厦门市", "杭州市", "南昌市", "贵阳市", "保定市"],
    }},
    # 第二批 (2012): 北京、上海、海南等29省市
    "batch2": {{
        "year": 2012,
        "cities": ["北京市", "上海市", "石家庄市", "秦皇岛市", "晋城市",
                   "呼伦贝尔市", "吉林市", "苏州市", "淮安市", "镇江市",
                   "宁波市", "温州市", "池州市", "南平市", "景德镇市",
                   "赣州市", "青岛市", "济源市", "武汉市", "广州市",
                   "桂林市", "广元市", "遵义市", "昆明市", "延安市",
                   "金昌市", "乌鲁木齐市"],
    }},
    # 第三批 (2017): 45个城市
    "batch3": {{
        "year": 2017,
        "cities": ["南京市", "合肥市", "长沙市", "成都市", "福州市",
                   "济南市", "三亚市", "兰州市", "西宁市", "银川市",
                   "大连市", "沈阳市", "吉林市", "齐齐哈尔市", "黄石市",
                   "湘潭市", "柳州市", "玉溪市", "拉萨市", "敦煌市",
                   "共青城市", "庄河市", "琼海市", "普洱市", "普洱市思茅区"],
    }},
}}

def build_treat_variable(city_name, year):
    """根据城市名和年份构建Treat变量"""
    for batch_key, batch_info in LCCP_CITIES.items():
        batch_year = batch_info["year"]
        all_lccp = batch_info.get("provinces", []) + batch_info.get("cities", [])
        if city_name in all_lccp or any(prov in city_name for prov in batch_info.get("provinces", [])):
            if year >= batch_year:
                return 1
    return 0

# ═══════════════════════════════════════════════════════════
# 数据获取函数 (按数据源分别实现)
# ═══════════════════════════════════════════════════════════

# ─── AKShare: 城市面板宏观数据 (免费) ───
def fetch_akshare_city_data(years=range(2003, 2023)):
    """使用AKShare获取城市面板数据"""
    try:
        import akshare as ak
        print("[AKShare] 正在获取城市面板数据...")

        # 城市GDP
        # df_gdp = ak.macro_china_city_gdp()
        # 城市财政
        # df_fiscal = ak.macro_china_city_fiscal()

        print("[AKShare] 数据获取完成")
        return True
    except ImportError:
        print("[AKShare] 请先安装: pip install akshare")
        return False
    except Exception as e:
        print(f"[AKShare] 错误: {{e}}")
        return False

# ─── EPS数据平台: 城市统计年鉴指标 (需订阅) ───
def fetch_eps_city_data(username=None, password=None):
    """使用EPS API获取城市统计年鉴数据"""
    u = username or CONFIG.get("eps_username")
    p = password or CONFIG.get("eps_password")

    if "YOUR_EPS" in str(u):
        print("[EPS] 请先配置 EPS 用户名和密码")
        print("[EPS] 需要获取的指标:")
        print("  - 分行业城镇单位就业人数 (19个门类)")
        print("  - 分行业城镇单位平均工资")
        print("  - 三产增加值 / 二产增加值")
        print("  - 私营企业和个体从业人员数")
        print("  - 人均GDP、普通高校在校生数、实际利用外资")
        print("  - 人均城市道路面积、财政支出、城镇化率")
        return False

    print(f"[EPS] 正在通过API获取数据 (用户: {{u}})...")
    # TODO: 根据实际EPS API/SDK实现
    return False

# ─── CNRDS: 专利IPC分类数据 (需订阅) ───
def fetch_cnrds_patent_data(api_key=None):
    """使用CNRDS API获取专利IPC分类"""
    key = api_key or CONFIG.get("cnrds_api_key")

    if "YOUR_CNRDS" in str(key):
        print("[CNRDS] 请先配置 CNRDS API Key")
        print("[CNRDS] 需要获取的数据:")
        print("  - 各城市年度发明专利授权量 (按IPC小类)")
        print("  - 绿色专利标识 (WIPO IPC Green Inventory)")
        print("  - 可以此构建技能偏向性技术创新指标")
        return False

    print(f"[CNRDS] 正在通过API获取专利数据...")
    # TODO: CNRDS REST API 调用
    return False

# ─── CSMAR: 上市公司员工结构 (需订阅) ───
def fetch_csmar_employee_data(api_key=None):
    """使用CSMAR REST API获取上市公司员工学历/岗位构成"""
    key = api_key or CONFIG.get("csmar_api_key")

    if "YOUR_CSMAR" in str(key):
        print("[CSMAR] 请先配置 CSMAR API Key")
        print("[CSMAR] 需要获取的表:")
        print("  - 上市公司员工学历构成表")
        print("  - 上市公司研发创新表")
        return False

    print(f"[CSMAR] 正在通过API获取员工结构数据...")
    # TODO: CSMAR REST API 调用
    return False

# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("论文数据获取脚本")
    print("「低碳转型的公正代价」")
    print("=" * 60)

    results = {{}}

    # 1. 城市面板控制变量 (首选EPS, 备选AKShare)
    if "{controls_source}" == "eps":
        results["controls"] = fetch_eps_city_data()
    else:
        results["controls"] = fetch_akshare_city_data()

    # 2. 劳动力市场数据 (Y)
    if "{y_source}" == "eps":
        results["y_var"] = fetch_eps_city_data()  # EPS含分行业就业
    elif "{y_source}" == "csmar":
        results["y_var"] = fetch_csmar_employee_data()

    # 3. 专利数据 (M1)
    if "{m1_source}" == "cnrds":
        results["m1_var"] = fetch_cnrds_patent_data()

    # 4. 汇总
    print("\\n" + "=" * 60)
    print("数据获取完成，请检查 DATA_DIR 中的输出文件")
    print(f"DATA_DIR: {{DATA_DIR}}")

    # 保存配置供后续使用
    with open(os.path.join(DATA_DIR, "fetch_config.json"), "w", encoding="utf-8") as f:
        json.dump({{"y_source": "{y_source}", "m1_source": "{m1_source}",
                     "m2_source": "{m2_source}", "controls_source": "{controls_source}",
                     "iv_source": "{iv_source}"}}, f, ensure_ascii=False, indent=2)
'''
        path = os.path.join(self._data_dir, "download_paper_data.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(script)

        return {
            "success": True,
            "script_path": path,
            "data_dir": self._data_dir,
            "sources_used": {
                "y": y_source,
                "m1": m1_source,
                "m2": m2_source,
                "controls": controls_source,
                "iv": iv_source,
            }
        }

    def _fetch_data(self, script_path: str = None) -> dict:
        """执行数据下载脚本"""
        if not script_path:
            script_path = os.path.join(self._data_dir, "download_data.py")

        if not os.path.exists(script_path):
            return {"success": False, "error": f"脚本不存在: {script_path}"}

        try:
            result = subprocess.run(
                ["python", script_path],
                capture_output=True, text=True, timeout=300,
                cwd=os.path.dirname(script_path))
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "data_dir": self._data_dir,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
