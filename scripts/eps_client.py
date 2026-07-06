"""
EPS 数据平台 API Python 客户端
认证 → 维度探索 → 数据请求 → 保存 CSV

使用方式:
  python scripts/eps_client.py --login        # 测试登录
  python scripts/eps_client.py --list-cubes   # 列出可用数据集
  python scripts/eps_client.py --explore <cubeId>  # 探索数据集结构
  python scripts/eps_client.py --fetch <cubeId> --output data.csv  # 获取数据
"""
import requests
import json
import os
import sys
import time
from typing import Optional

# ══════════════════════════════════════════════════════
# 配置
# ══════════════════════════════════════════════════════
CONFIG = {
    "user_base": "https://olap.epsnet.com.cn/user",
    "eps_base": "https://olap.epsnet.com.cn/eps",
    "login_type": "IP",              # IP / GROUP_PWD / MOBILE
    "account": "",                    # 仅 GROUP_PWD / MOBILE 需要
    "password": "",                   # 仅 GROUP_PWD 需要
    "output_dir": os.path.abspath("workspace/data"),
    "sid_file": os.path.abspath("workspace/data/.eps_sid"),
}

# 论文需要的数据集 (cubeId 待确认，以下是常见编码)
# EPS 中 "中国城市统计年鉴" 的典型 cubeId
DATASET_CANDIDATES = {
    "城市统计年鉴": {
        "possible_cubeIds": ["C01", "C02", "C03", "Y01", "Y02"],
        "needed_indicators": [
            "地区生产总值(GDP)",
            "年末总人口",
            "普通高等学校在校学生数",
            "实际使用外资金额",
            "地方一般公共预算支出",
            "年末实有城市道路面积",
            "城镇常住人口",
            "分行业城镇单位就业人数",  # 19个门类
            "私营企业和个体从业人员",
            "第二产业增加值",
            "第三产业增加值",
        ],
    },
    "劳动统计年鉴": {
        "possible_cubeIds": ["L01", "Z01", "Z02"],
        "needed_indicators": [
            "分行业城镇单位就业人员平均工资",  # 用于技能分组排序
            "分行业城镇单位就业人员年末人数",
        ],
    },
}


class EPSClient:
    """EPS 数据平台 API 客户端"""

    def __init__(self, login_type: str = None):
        self.login_type = login_type or CONFIG["login_type"]
        self.account = CONFIG["account"]
        self.password = CONFIG["password"]
        self.sid: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "EPS-Python-Client/1.0",
            "Accept": "application/json",
            "Lang": "1",  # 中文
        })
        self._load_sid()

    # ─── 认证 ───────────────────────────────────────

    def login(self) -> dict:
        """登录 EPS，获取 SID"""
        if self.login_type == "IP":
            url = f"{CONFIG['user_base']}/login/login"
            params = {"loginType": "IP"}
        elif self.login_type == "GROUP_PWD":
            url = f"{CONFIG['user_base']}/login/login"
            params = {
                "account": self.account,
                "pwd": self.password,
                "loginType": "GROUP_PWD",
            }
        elif self.login_type == "MOBILE":
            raise NotImplementedError("手机号登录请先手动获取验证码")
        else:
            raise ValueError(f"不支持的登录方式: {self.login_type}")

        r = self.session.get(url, params=params, timeout=30)
        result = r.json()
        print(f"[EPS] 登录响应: {r.status_code} | {json.dumps(result, ensure_ascii=False)[:300]}")

        # 从响应中提取 SID
        sid = self._extract_sid(result)
        if sid:
            self.sid = sid
            self._save_sid()
            print(f"[EPS] ✅ 登录成功, SID: {sid[:16]}...")
        else:
            print(f"[EPS] ⚠️ 未能提取 SID，请检查登录方式或网络环境。")
        return result

    def _extract_sid(self, response: dict) -> Optional[str]:
        """从 EPS 响应中提取 SID"""
        # SID 可能在 ResultObject.sid, data.sid, 或顶层 sid 字段
        for key in ["sid", "SID", "token", "access_token"]:
            if key in response:
                return response[key]
        if "ResultObject" in response:
            ro = response["ResultObject"]
            if isinstance(ro, dict):
                for key in ["sid", "SID", "token"]:
                    if key in ro:
                        return ro[key]
            elif isinstance(ro, str):
                return ro  # 可能直接返回 SID 字符串
        if "data" in response:
            d = response["data"]
            if isinstance(d, dict):
                for key in ["sid", "SID"]:
                    if key in d:
                        return d[key]
        return None

    def _save_sid(self):
        with open(CONFIG["sid_file"], "w") as f:
            json.dump({"sid": self.sid, "time": time.time()}, f)

    def _load_sid(self):
        if os.path.exists(CONFIG["sid_file"]):
            with open(CONFIG["sid_file"], "r") as f:
                data = json.load(f)
                # SID 有效期通常数小时，超过 2 小时重新登录
                if time.time() - data.get("time", 0) < 7200:
                    self.sid = data["sid"]
                    print(f"[EPS] 已加载缓存 SID: {self.sid[:16]}...")

    def _require_sid(self):
        """确保有有效 SID"""
        if not self.sid:
            self.login()
        if not self.sid:
            raise RuntimeError("未获取到有效 SID，无法继续。请确认: 1) 机构IP在EPS授权范围 2) 或使用账号密码登录")

    # ─── 维度查询 ───────────────────────────────────

    def get_dimensions(self, cube_id: str) -> dict:
        """获取数据集的维度结构"""
        self._require_sid()
        url = f"{CONFIG['eps_base']}/getDimension.do"
        params = {"cubeId": cube_id, "sid": self.sid}
        r = self.session.get(url, params=params, timeout=30,
                            headers={"Lang": "1"})
        return r.json()

    def get_dimension_members(self, sheet_id: str, dim_type: str,
                               parent_code: str = "01") -> dict:
        """获取某维度下的具体成员（地区/年份/指标等）"""
        self._require_sid()
        url = f"{CONFIG['eps_base']}/getDimensionList.do"
        params = {
            "sid": self.sid,
            "sheetId": sheet_id,
            "dimType": dim_type,
            "parentCode": parent_code,
        }
        r = self.session.get(url, params=params, timeout=30,
                            headers={"Lang": "1"})
        return r.json()

    # ─── 数据请求 ───────────────────────────────────

    def get_data(self, cube_id: str, params: dict) -> dict:
        """请求最终数据 (POST)"""
        self._require_sid()
        url = f"{CONFIG['eps_base']}/getData.do"
        body = {
            "sid": self.sid,
            "cubeId": cube_id,
            **params,
        }
        r = self.session.post(url, json=body, timeout=120,
                             headers={"Lang": "1", "Content-Type": "application/json"})
        return r.json()

    # ─── 探索工具 ───────────────────────────────────

    def explore_cube(self, cube_id: str, max_depth: int = 3) -> dict:
        """递归探索数据集结构，帮助确认维度编码"""
        print(f"\n[EPS] 探索数据集: {cube_id}")
        dims = self.get_dimensions(cube_id)
        print(f"[EPS] 维度结构: {json.dumps(dims, ensure_ascii=False)[:500]}")

        # 提取维度信息
        dimensions = {}
        if isinstance(dims, dict):
            for key, val in dims.items():
                if isinstance(val, dict):
                    sheet_id = val.get("sheetId", "")
                    dim_type = val.get("dimType", "")
                    dim_name = val.get("dimName", key)
                    if sheet_id and dim_type:
                        dimensions[dim_name] = {
                            "sheetId": sheet_id,
                            "dimType": dim_type,
                        }
                        # 尝试获取第一层成员
                        try:
                            members = self.get_dimension_members(
                                sheet_id, dim_type, "01"
                            )
                            member_list = []
                            if isinstance(members, dict):
                                for mk, mv in members.items():
                                    if isinstance(mv, list):
                                        member_list = [
                                            m.get("code", "") + ":" + m.get("name", "")
                                            for m in mv[:10]
                                        ]
                                    elif isinstance(mv, dict):
                                        member_list = [
                                            f"{k}:{v}" for k, v in list(mv.items())[:10]
                                        ]
                            dimensions[dim_name]["sample_members"] = member_list[:10]
                        except Exception:
                            pass

        return {"cube_id": cube_id, "dimensions": dimensions}

    def suggest_cubes(self) -> list:
        """尝试常见的 cubeId 前缀，帮助用户找到数据集"""
        self._require_sid()
        # EPS 的 cubeId 通常为字母+数字组合
        common_prefixes = [
            # 城市年鉴
            "C01", "C02", "C03", "C04", "C05",
            # 综合年鉴
            "Y01", "Y02", "Y03",
            # 劳动/就业
            "L01", "L02",
            # 人口
            "Z01", "Z02",
            # 区域经济
            "Q01",
        ]
        found = []
        for cid in common_prefixes:
            try:
                dims = self.get_dimensions(cid)
                found.append({"cubeId": cid, "status": "OK"})
                print(f"  [{cid}] ✅ 可用")
            except Exception:
                pass
        return found


# ══════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="EPS数据平台API客户端")
    parser.add_argument("--login", action="store_true", help="测试登录")
    parser.add_argument("--login-type", default="IP",
                        choices=["IP", "GROUP_PWD", "MOBILE"],
                        help="登录方式 (默认: IP)")
    parser.add_argument("--account", default="", help="账号(GROUP_PWD/MOBILE)")
    parser.add_argument("--password", default="", help="密码(GROUP_PWD)")
    parser.add_argument("--list-cubes", action="store_true", help="探测可用数据集")
    parser.add_argument("--explore", type=str, help="探索指定 cubeId 的结构")
    parser.add_argument("--fetch", type=str, help="获取指定 cubeId 的数据")
    parser.add_argument("--output", type=str, help="输出 CSV 文件路径")

    args = parser.parse_args()

    client = EPSClient(login_type=args.login_type)
    if args.account:
        client.account = args.account
    if args.password:
        client.password = args.password

    if args.login:
        client.login()

    elif args.list_cubes:
        client._require_sid()
        print("[EPS] 正在探测可用数据集...")
        cubes = client.suggest_cubes()
        print(f"\n[EPS] 找到 {len(cubes)} 个可用数据集")

    elif args.explore:
        result = client.explore_cube(args.explore)
        print(f"\n[EPS] 数据集 {args.explore} 结构:")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.fetch:
        # 交互式数据获取：先探索 → 用户选择维度 → 请求数据
        info = client.explore_cube(args.fetch)
        print(f"\n[EPS] 数据集 {args.fetch} 包含以下维度:")
        for name, dim in info.get("dimensions", {}).items():
            print(f"  [{dim['sheetId']}] {name} (dimType={dim['dimType']})")
            samples = dim.get("sample_members", [])
            if samples:
                print(f"    样例: {', '.join(samples[:5])}")
        print("\n[EPS] 请根据以上维度信息，编辑 fetch 参数后重新运行。")
        print("[EPS] 数据获取的完整参数格式请参考文档。")

    else:
        parser.print_help()
