"""
统一数据访问层 (Data Access Layer) — 替代分散的 _load_* 方法。

所有数据读取操作统一通过此模块进行，底层使用 KnowledgeIndex 缓存。
支持：
1. 当前工作区 + 已归档项目的透明访问
2. 内存缓存（避免重复扫描文件系统）
3. 增量扫描（只处理新增/修改的文件）
4. 向后兼容旧的扁平目录结构
"""

from __future__ import annotations
import os
import json
import hashlib
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from functools import lru_cache


class WorkspaceDAL:
    """
    统一数据访问层。

    使用方式：
      dal = WorkspaceDAL()
      papers = dal.get_all_papers()              # 所有论文元数据
      summaries = dal.get_paper_summaries()      # 所有 PaperSummary
      cross = dal.get_cross_paper_synthesis()    # 跨论文对比数据
      empirical = dal.get_empirical_results()    # 实证分析结果
      reviews = dal.get_literature_reviews()     # 文献综述文本
      projects = dal.list_projects()             # 项目概览
    """

    def __init__(self, workspace_root: str = "workspace"):
        self._workspace_root = os.path.abspath(workspace_root)
        self._projects_root = os.path.join(self._workspace_root, "projects")
        self._analysis_root = os.path.join(self._workspace_root, "analysis")
        self._papers_dir = os.path.join(self._workspace_root, "papers")

        # 缓存
        self._cache: Dict[str, Any] = {}
        self._cache_timestamp: Dict[str, float] = {}
        self._knowledge_index = None  # 延迟加载

    # ═══════════════════════════════════════════════════════════
    # 论文元数据
    # ═══════════════════════════════════════════════════════════

    def get_papers_metadata(self, include_archived: bool = True) -> List[Dict]:
        """获取所有论文的原始元数据（metadata.json 格式）"""
        cache_key = f"papers_meta_{include_archived}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        all_papers = []

        # 当前工作区
        self._add_papers_from_dir(self._papers_dir, all_papers)

        # 已归档项目
        if include_archived:
            for proj_dir in self._iter_project_dirs():
                papers_dir = os.path.join(proj_dir, "papers")
                self._add_papers_from_dir(papers_dir, all_papers, source_project=os.path.basename(proj_dir))

        # 去重（按 title）
        seen = set()
        unique = []
        for p in all_papers:
            title = p.get("title", "")
            if title and title not in seen:
                seen.add(title)
                unique.append(p)

        self._set_cache(cache_key, unique)
        return unique

    def get_papers_titles(self, include_archived: bool = True) -> List[str]:
        """获取所有论文标题列表"""
        papers = self.get_papers_metadata(include_archived)
        return [p.get("title", "") for p in papers if p.get("title")]

    # ═══════════════════════════════════════════════════════════
    # PaperSummary（核心数据结构）
    # ═══════════════════════════════════════════════════════════

    def get_paper_summaries(self, include_archived: bool = True) -> List[Dict]:
        """
        获取所有 _paper_summary.json 的内容。
        返回旧格式的 dict 列表（向后兼容）。
        """
        cache_key = f"summaries_{include_archived}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        summaries = []

        # 当前工作区
        self._scan_summaries(self._analysis_root, summaries)

        # 已归档项目
        if include_archived:
            for proj_dir in self._iter_project_dirs():
                analysis_dir = os.path.join(proj_dir, "analysis")
                self._scan_summaries(analysis_dir, summaries)

        # 也扫描旧结构（empirical 单独目录）
        if include_archived:
            for proj_dir in self._iter_project_dirs():
                empirical_dir = os.path.join(proj_dir, "empirical")
                if os.path.exists(empirical_dir):
                    for fname in os.listdir(empirical_dir):
                        if fname.endswith("_empirical.json"):
                            try:
                                with open(os.path.join(empirical_dir, fname), "r", encoding="utf-8") as f:
                                    emp = json.load(f)
                                # 补充到已有 summary 或创建新条目
                                title = emp.get("title", "")
                                found = False
                                for s in summaries:
                                    if s.get("paper_title", "") == title:
                                        if "sections" not in s:
                                            s["sections"] = {}
                                        s["sections"]["empirical"] = emp
                                        found = True
                                        break
                                if not found:
                                    summaries.append({
                                        "paper_title": title,
                                        "sections": {"empirical": emp},
                                    })
                            except Exception:
                                pass

        self._set_cache(cache_key, summaries)
        return summaries

    # ═══════════════════════════════════════════════════════════
    # 11 维度分析结果
    # ═══════════════════════════════════════════════════════════

    def get_section_analyses(self, paper_title: str,
                             include_archived: bool = True) -> Dict[str, Dict]:
        """
        获取某篇论文的所有 11 维度分析 JSON。
        返回 {"01": {...}, "02": {...}, ...}
        """
        cache_key = f"sections_{paper_title}_{include_archived}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        # 定位论文目录
        paper_dir = self._find_paper_dir(paper_title, include_archived)
        if not paper_dir:
            return {}

        sections = {}
        for fname in sorted(os.listdir(paper_dir)):
            if fname.endswith(".json") and not fname.startswith("_") and fname != "empirical.json":
                # 提取维度编号（如 "01_introduction.json" → "01"）
                section_num = fname[:2]
                if section_num.isdigit():
                    try:
                        with open(os.path.join(paper_dir, fname), "r", encoding="utf-8") as f:
                            sections[section_num] = json.load(f)
                    except Exception:
                        pass

        self._set_cache(cache_key, sections)
        return sections

    # ═══════════════════════════════════════════════════════════
    # 实证分析结果
    # ═══════════════════════════════════════════════════════════

    def get_empirical_results(self, include_archived: bool = True) -> List[Dict]:
        """获取所有论文的实证分析结果"""
        cache_key = f"empirical_{include_archived}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        results = []

        # 从 summaries 提取
        summaries = self.get_paper_summaries(include_archived)
        for s in summaries:
            sections = s.get("sections", {})
            emp = sections.get("empirical", {})
            if emp:
                entry = {
                    "title": s.get("paper_title", ""),
                    "json": emp,
                    "success": bool(emp.get("key_findings") or emp.get("y_var")),
                }
                results.append(entry)

        # 也扫描独立的 empirical 文件
        def _scan_empirical(root_dir):
            if not os.path.exists(root_dir):
                return
            for dname in os.listdir(root_dir):
                paper_dir = os.path.join(root_dir, dname)
                if not os.path.isdir(paper_dir) or dname.startswith("_"):
                    continue
                emp_json = os.path.join(paper_dir, "empirical.json")
                emp_md = os.path.join(paper_dir, "empirical.md")
                if os.path.exists(emp_json):
                    # 检查是否已在 results 中
                    title = dname
                    if any(r.get("title") == title for r in results):
                        continue
                    try:
                        with open(emp_json, "r", encoding="utf-8") as f:
                            emp = json.load(f)
                        entry = {
                            "title": emp.get("title", dname),
                            "json": emp,
                            "success": bool(emp.get("key_findings")),
                        }
                        if os.path.exists(emp_md):
                            with open(emp_md, "r", encoding="utf-8") as f:
                                entry["markdown"] = f.read()
                        results.append(entry)
                    except Exception:
                        pass

        _scan_empirical(self._analysis_root)
        if include_archived:
            for proj_dir in self._iter_project_dirs():
                _scan_empirical(os.path.join(proj_dir, "analysis"))
                _scan_empirical(os.path.join(proj_dir, "empirical"))

        self._set_cache(cache_key, results)
        return results

    # ═══════════════════════════════════════════════════════════
    # 跨论文对比数据
    # ═══════════════════════════════════════════════════════════

    def get_cross_paper_synthesis(self) -> Dict:
        """
        获取跨论文对比的综合数据。
        优先 _writing_synthesis.json，回退 _cross_paper_summary.json。
        """
        cache_key = "cross_synthesis"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        # 当前工作区
        cross_dir = os.path.join(self._analysis_root, "_cross_paper")
        result = self._load_cross_synthesis_from_dir(cross_dir)

        if result:
            self._set_cache(cache_key, result)
            return result

        # 回退：搜索归档项目
        for proj_dir in self._iter_project_dirs():
            cross_dir = os.path.join(proj_dir, "analysis", "_cross_paper")
            result = self._load_cross_synthesis_from_dir(cross_dir)
            if result:
                self._set_cache(cache_key, result)
                return result

        return {}

    def get_cross_paper_comparisons(self) -> Dict[str, Dict]:
        """获取所有跨论文对比矩阵（11维度+6实证）"""
        cache_key = "cross_comparisons"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        comparisons = {}

        cross_dir = os.path.join(self._analysis_root, "_cross_paper")
        if os.path.exists(cross_dir):
            for fname in os.listdir(cross_dir):
                if fname.endswith("_comparison.json"):
                    try:
                        with open(os.path.join(cross_dir, fname), "r", encoding="utf-8") as f:
                            key = fname.replace("_comparison.json", "")
                            comparisons[key] = json.load(f)
                    except Exception:
                        pass

        # 归档项目
        for proj_dir in self._iter_project_dirs():
            cross_dir = os.path.join(proj_dir, "analysis", "_cross_paper")
            if os.path.exists(cross_dir):
                for fname in os.listdir(cross_dir):
                    if fname.endswith("_comparison.json"):
                        key = fname.replace("_comparison.json", "")
                        if key not in comparisons:
                            try:
                                with open(os.path.join(cross_dir, fname), "r", encoding="utf-8") as f:
                                    comparisons[key] = json.load(f)
                            except Exception:
                                pass

        self._set_cache(cache_key, comparisons)
        return comparisons

    # ═══════════════════════════════════════════════════════════
    # 文献综述
    # ═══════════════════════════════════════════════════════════

    def get_literature_reviews(self, include_archived: bool = True) -> Dict[str, str]:
        """
        获取所有文献综述文本。
        返回 {"（当前）": "...", "项目名": "...", ...}
        """
        cache_key = f"reviews_{include_archived}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        reviews = {}

        # 当前工作区
        lr_path = os.path.join(self._workspace_root, "literature_review.md")
        if os.path.exists(lr_path):
            with open(lr_path, "r", encoding="utf-8") as f:
                reviews["（当前）"] = f.read()

        # 归档项目
        if include_archived:
            for proj_dir in self._iter_project_dirs():
                lr_path = os.path.join(proj_dir, "literature_review.md")
                if os.path.exists(lr_path):
                    with open(lr_path, "r", encoding="utf-8") as f:
                        reviews[os.path.basename(proj_dir)] = f.read()

        self._set_cache(cache_key, reviews)
        return reviews

    # ═══════════════════════════════════════════════════════════
    # 项目概览
    # ═══════════════════════════════════════════════════════════

    def list_projects(self) -> List[Dict]:
        """列出所有项目及其状态"""
        cache_key = "projects"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        projects = []

        # 当前工作区
        current = {
            "name": "（当前工作区）",
            "folder": None,
            "papers_count": 0,
            "analysis_count": 0,
            "has_review": False,
            "has_writing": False,
            "is_current": True,
        }
        papers_meta = os.path.join(self._papers_dir, "metadata.json")
        if os.path.exists(papers_meta):
            try:
                with open(papers_meta, "r", encoding="utf-8") as f:
                    current["papers_count"] = len(json.load(f))
            except Exception:
                pass
        current["has_review"] = os.path.exists(os.path.join(self._workspace_root, "literature_review.md"))
        current["has_writing"] = os.path.exists(os.path.join(self._workspace_root, "writing", "full_paper.md"))
        current["analysis_count"] = self._count_analyses(self._analysis_root)
        projects.append(current)

        # 归档项目
        if os.path.exists(self._projects_root):
            for dname in sorted(os.listdir(self._projects_root)):
                proj_dir = os.path.join(self._projects_root, dname)
                if not os.path.isdir(proj_dir):
                    continue

                info_path = os.path.join(proj_dir, "project_info.json")
                info = {}
                if os.path.exists(info_path):
                    try:
                        with open(info_path, "r", encoding="utf-8") as f:
                            info = json.load(f)
                    except Exception:
                        pass

                papers_path = os.path.join(proj_dir, "papers", "metadata.json")
                papers_count = 0
                if os.path.exists(papers_path):
                    try:
                        with open(papers_path, "r", encoding="utf-8") as f:
                            papers_count = len(json.load(f))
                    except Exception:
                        pass

                analysis_dir = os.path.join(proj_dir, "analysis")
                analysis_count = self._count_analyses(analysis_dir)

                projects.append({
                    "name": info.get("paper_title", dname),
                    "folder": dname,
                    "papers_count": papers_count,
                    "analysis_count": analysis_count,
                    "has_review": os.path.exists(os.path.join(proj_dir, "literature_review.md")),
                    "has_writing": os.path.exists(os.path.join(proj_dir, "writing", "full_paper.md")),
                    "has_presentation": os.path.exists(os.path.join(proj_dir, "presentation.pptx")),
                    "has_regression": os.path.exists(os.path.join(proj_dir, "regression")),
                    "is_current": False,
                    "info": info,
                })

        self._set_cache(cache_key, projects)
        return projects

    # ═══════════════════════════════════════════════════════════
    # 论文全文
    # ═══════════════════════════════════════════════════════════

    def get_paper_fulltext(self, paper_title: str) -> str:
        """获取某篇论文的全文（从 metadata.json 或归档项目）"""
        cache_key = f"fulltext_{hashlib.md5(paper_title.encode()).hexdigest()[:12]}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        fulltext = ""

        # 1. 当前工作区
        meta_path = os.path.join(self._papers_dir, "metadata.json")
        fulltext = self._find_fulltext_in_metadata(meta_path, paper_title)
        if fulltext:
            self._set_cache(cache_key, fulltext)
            return fulltext

        # 2. 归档项目
        for proj_dir in self._iter_project_dirs():
            meta_path = os.path.join(proj_dir, "papers", "metadata.json")
            fulltext = self._find_fulltext_in_metadata(meta_path, paper_title)
            if fulltext:
                self._set_cache(cache_key, fulltext)
                return fulltext

        self._set_cache(cache_key, "")
        return ""

    # ═══════════════════════════════════════════════════════════
    # Knowledge Index 集成
    # ═══════════════════════════════════════════════════════════

    def get_knowledge_index(self):
        """获取或懒加载 KnowledgeIndex 实例"""
        if self._knowledge_index is None:
            from skills.knowledge_index import KnowledgeIndex
            self._knowledge_index = KnowledgeIndex()
        return self._knowledge_index

    def query_method(self, method: str) -> List[str]:
        """快速查询：哪些论文使用了特定方法？（使用倒排索引）"""
        ki = self.get_knowledge_index()
        return ki.find_by_method(method)

    def query_variable(self, var_name: str) -> List[Dict]:
        """快速查询：哪些论文使用了特定变量？"""
        ki = self.get_knowledge_index()
        return ki.find_by_variable(var_name)

    def get_method_stats(self) -> Dict[str, int]:
        """获取方法使用频率统计"""
        ki = self.get_knowledge_index()
        return ki.get_method_stats()

    def rebuild_index(self):
        """重建知识索引（从当前 workspace）"""
        from skills.knowledge_index import build_index_from_workspace
        self._knowledge_index = build_index_from_workspace(self._workspace_root)
        self.clear_cache()

    # ═══════════════════════════════════════════════════════════
    # 缓存管理
    # ═══════════════════════════════════════════════════════════

    def _get_cache(self, key: str) -> Optional[Any]:
        """检查缓存是否有效（有效期 5 分钟）"""
        if key in self._cache:
            ts = self._cache_timestamp.get(key, 0)
            if (datetime.now().timestamp() - ts) < 300:  # 5 分钟
                return self._cache[key]
        return None

    def _set_cache(self, key: str, value: Any):
        self._cache[key] = value
        self._cache_timestamp[key] = datetime.now().timestamp()

    def clear_cache(self):
        self._cache.clear()
        self._cache_timestamp.clear()

    # ═══════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════

    def _iter_project_dirs(self):
        """迭代所有归档项目目录"""
        if not os.path.exists(self._projects_root):
            return
        for dname in sorted(os.listdir(self._projects_root)):
            proj_dir = os.path.join(self._projects_root, dname)
            if os.path.isdir(proj_dir):
                yield proj_dir

    def _add_papers_from_dir(self, papers_dir: str, all_papers: List[Dict],
                             source_project: str = None):
        """从目录加载论文元数据"""
        meta_path = os.path.join(papers_dir, "metadata.json")
        if not os.path.exists(meta_path):
            return
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                papers = json.load(f)
            if isinstance(papers, list):
                for p in papers:
                    if source_project:
                        p["_source_project"] = source_project
                    all_papers.append(p)
        except Exception:
            pass

    def _scan_summaries(self, root_dir: str, summaries: List[Dict]):
        """扫描目录树中的所有 _paper_summary.json"""
        if not os.path.exists(root_dir):
            return
        for dname in os.listdir(root_dir):
            paper_dir = os.path.join(root_dir, dname)
            if not os.path.isdir(paper_dir) or dname.startswith("_"):
                continue
            summary_path = os.path.join(paper_dir, "_paper_summary.json")
            if os.path.exists(summary_path):
                try:
                    with open(summary_path, "r", encoding="utf-8") as f:
                        summaries.append(json.load(f))
                except Exception:
                    pass

    def _find_paper_dir(self, paper_title: str, include_archived: bool = True) -> Optional[str]:
        """按标题查找论文分析目录"""
        import re

        def _search(base_dir):
            if not os.path.exists(base_dir):
                return None
            for dname in os.listdir(base_dir):
                paper_dir = os.path.join(base_dir, dname)
                if not os.path.isdir(paper_dir) or dname.startswith("_"):
                    continue
                # 标题匹配（模糊）
                safe_name = re.sub(r'[<>:"/\\|?*]', '', paper_title.strip())[:50]
                if dname == safe_name or paper_title[:30] in dname or dname in paper_title[:30]:
                    if os.path.exists(os.path.join(paper_dir, "_paper_summary.json")):
                        return paper_dir
            return None

        result = _search(self._analysis_root)
        if result or not include_archived:
            return result

        for proj_dir in self._iter_project_dirs():
            result = _search(os.path.join(proj_dir, "analysis"))
            if result:
                return result
        return None

    @staticmethod
    def _count_analyses(analysis_dir: str) -> int:
        """统计分析目录中的分析文件数"""
        if not os.path.exists(analysis_dir):
            return 0
        count = 0
        for dname in os.listdir(analysis_dir):
            paper_dir = os.path.join(analysis_dir, dname)
            if os.path.isdir(paper_dir) and not dname.startswith("_"):
                count += len([f for f in os.listdir(paper_dir)
                              if f.endswith(".json") and f[:2].isdigit()])
        return count

    @staticmethod
    def _load_cross_synthesis_from_dir(cross_dir: str) -> Dict:
        """从目录加载跨论文综合数据"""
        if not os.path.exists(cross_dir):
            return {}
        for fname in ["_writing_synthesis.json", "_cross_paper_summary.json"]:
            path = os.path.join(cross_dir, fname)
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
        return {}

    @staticmethod
    def _find_fulltext_in_metadata(meta_path: str, paper_title: str) -> str:
        """在 metadata.json 中查找指定论文的全文"""
        if not os.path.exists(meta_path):
            return ""
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                papers = json.load(f)
            for p in papers:
                if p.get("title", "") == paper_title:
                    return p.get("fulltext", "")
        except Exception:
            pass
        return ""


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

# 全局实例（单例）
_dal_instance: Optional[WorkspaceDAL] = None


def get_dal(workspace_root: str = "workspace") -> WorkspaceDAL:
    """获取 WorkspaceDAL 单例（缓存 5 分钟内有效）"""
    global _dal_instance
    if _dal_instance is None:
        _dal_instance = WorkspaceDAL(workspace_root)
    return _dal_instance


def reset_dal():
    """重置 DAL 单例（用于测试或重建索引后）"""
    global _dal_instance
    _dal_instance = None
