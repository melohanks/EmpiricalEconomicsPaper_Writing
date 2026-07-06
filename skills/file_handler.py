import os
import json
import glob
import pandas as pd
from skills.base import BaseSkill


class FileHandler(BaseSkill):
    """
    工作空间数据文件读写与格式化处理技能。
    负责论文元数据文件的保存、CSV格式转化、本地目录导入以及分析报告的导出。
    """

    # CSV 列名到标准字段的映射（支持中英文列名）
    CSV_COLUMN_MAP = {
        "标题": "title", "title": "title",
        "作者": "authors", "authors": "authors",
        "来源": "source", "source": "source", "期刊": "source", "journal": "source",
        "发表时间": "pub_date", "pub_date": "pub_date", "日期": "pub_date", "date": "pub_date",
        "摘要": "abstract", "abstract": "abstract",
        "关键词": "keywords", "keywords": "keywords",
        "链接": "link", "link": "link", "url": "link",
    }

    def __init__(self):
        super().__init__(
            name="FileHandler",
            description="处理工作区Papers目录下的JSON、CSV数据读写与一致性转换，支持本地导入"
        )

    def execute(self, action: str, data=None, papers_dir: str = "workspace/papers") -> dict:
        """
        执行文件处理动作。
        :param action: 'save_papers' | 'load_papers' | 'import_papers'
        :param data: 当 action='save_papers' 时传入的 papers list 结构
        :param papers_dir: 保存/读取的物理路径
        """
        os.makedirs(papers_dir, exist_ok=True)
        json_path = os.path.join(papers_dir, "metadata.json")
        csv_path = os.path.join(papers_dir, "papers_metadata.csv")

        if action == "save_papers":
            return self._save_papers(data, json_path, csv_path)

        elif action == "load_papers":
            return self._load_papers(json_path)

        elif action == "import_papers":
            return self._import_papers(papers_dir, json_path, csv_path)

        else:
            raise NotImplementedError(f"未实现的 FileHandler 动作: {action}")

    # ─── 私有方法 ──────────────────────────────────────────────

    def _save_papers(self, data, json_path: str, csv_path: str) -> dict:
        if data is None:
            raise ValueError("保存论文信息必须传入 data 数据体。")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        df = pd.DataFrame(data)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")

        return {
            "json_path": json_path,
            "csv_path": csv_path,
            "count": len(data),
        }

    def _load_papers(self, json_path: str) -> dict:
        if not os.path.exists(json_path):
            return {"papers": [], "exists": False}
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                papers = json.load(f)
            return {"papers": papers, "exists": True}
        except Exception as e:
            print(f"[{self.name}] 载入元数据 JSON 发生异常: {e}")
            return {"papers": [], "exists": False, "error": str(e)}

    def _import_papers(self, papers_dir: str, json_path: str, csv_path: str) -> dict:
        """
        从本地目录导入论文元数据。
        优先级: metadata.json > 任意 *.csv > 报错
        校验每条论文至少包含 title 字段。
        """
        print(f"\n[{self.name}] 正在从本地目录导入论文: {papers_dir}")

        papers = []

        # 1) 优先读取 metadata.json
        if os.path.exists(json_path) and os.path.getsize(json_path) > 0:
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                if isinstance(content, list) and len(content) > 0:
                    papers = content
                    print(f"[{self.name}] 从 metadata.json 读取到 {len(papers)} 条记录")
            except json.JSONDecodeError as e:
                print(f"[{self.name}] metadata.json 格式错误: {e}，尝试回退到 CSV")

        # 2) 回退：扫描 CSV 文件
        if not papers:
            csv_files = glob.glob(os.path.join(papers_dir, "*.csv"))
            for csv_file in csv_files:
                try:
                    df = pd.read_csv(csv_file, encoding="utf-8-sig")
                except Exception:
                    try:
                        df = pd.read_csv(csv_file, encoding="utf-8")
                    except Exception as e:
                        print(f"[{self.name}] 无法读取 CSV {csv_file}: {e}")
                        continue

                if df.empty:
                    continue

                # 列名映射
                rename_map = {}
                for col in df.columns:
                    col_stripped = col.strip()
                    if col_stripped in self.CSV_COLUMN_MAP:
                        std = self.CSV_COLUMN_MAP[col_stripped]
                        if col != std:
                            rename_map[col] = std
                    else:
                        # 保留原始列名（可能是已标准化的）
                        pass

                if rename_map:
                    df.rename(columns=rename_map, inplace=True)

                raw = df.to_dict(orient="records")
                print(f"[{self.name}] 从 {os.path.basename(csv_file)} 读取到 {len(raw)} 条记录")
                papers.extend(raw)
                break  # 只取第一个有效 CSV

        # 3) 校验 & 清洗
        cleaned = []
        for i, p in enumerate(papers):
            if not isinstance(p, dict):
                continue
            title = p.get("title", "").strip()
            if not title:
                print(f"[{self.name}] ⚠ 跳过第 {i+1} 条：缺少标题")
                continue
            cleaned.append({
                "title": title,
                "authors": p.get("authors", "未知作者"),
                "source": p.get("source", "未知来源"),
                "pub_date": p.get("pub_date", "未知日期"),
                "abstract": p.get("abstract", ""),
                "fulltext": p.get("fulltext", ""),       # PDF 全文
                "extra": p.get("extra", ""),             # Zotero Extra 字段
                "zotero_key": p.get("zotero_key", ""),   # Zotero 条目 key
                "doi": p.get("doi", ""),
                "keywords": self._normalize_keywords(p.get("keywords", [])),
                "link": p.get("link", ""),
                "attachments": p.get("attachments", []),  # PDF 附件信息
            })

        if not cleaned:
            print(f"[{self.name}] 未找到有效论文数据。请将 metadata.json 或 CSV 文件放入 {papers_dir}/")
            print(f"[{self.name}] JSON 格式示例: [{{\"title\": \"论文标题\", \"authors\": \"作者\", ...}}]")
            return {"papers": [], "exists": False, "count": 0}

        # 将清洗后的数据写回 metadata.json
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=4)

        df = pd.DataFrame(cleaned)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")

        print(f"[{self.name}] 导入完成：共 {len(cleaned)} 篇有效论文")
        return {"papers": cleaned, "exists": True, "count": len(cleaned)}

    @staticmethod
    def _normalize_keywords(keywords):
        """将关键词规范化为 list[str]"""
        if isinstance(keywords, list):
            return [str(k).strip() for k in keywords if str(k).strip()]
        if isinstance(keywords, str):
            # 尝试以逗号/分号/中文逗号分割
            parts = []
            for sep in [",", ";", "，", "；"]:
                if sep in keywords:
                    parts = [k.strip() for k in keywords.split(sep) if k.strip()]
                    break
            if not parts:
                parts = [keywords.strip()]
            return parts
        return []
