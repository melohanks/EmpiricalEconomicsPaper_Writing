"""
统一知识索引层 — 替代零散的文件系统扫描。

功能：
1. SQLite 存储所有 PaperSummary + 结构化字段
2. 倒排索引：方法→论文、变量→论文、机制→论文
3. 向量存储接口（ChromaDB/FAISS 可选）
4. 增量更新（新增论文不触发全量重建）

架构：
  KnowledgeIndex (主入口)
    ├── SQLiteIndex     — 结构化精确查询 + 统计
    ├── InvertedIndex   — 内存倒排索引（快速关联查询）
    └── VectorStore      — 语义搜索（可选，需 pip install chromadb）
"""

from __future__ import annotations
import os
import json
import sqlite3
import hashlib
from typing import Optional, List, Dict, Any, Tuple, Iterator
from dataclasses import asdict
from datetime import datetime

# 从同目录导入 Schema
try:
    from skills.schemas import (
        PaperSummary, dataclass_to_dict, dict_to_dataclass,
        SECTION_SCHEMAS, SECTION_FIELD_MAP,
        EstimationMethod, ClusterLevel, RobustnessScore,
    )
except ImportError:
    from schemas import (
        PaperSummary, dataclass_to_dict, dict_to_dataclass,
        SECTION_SCHEMAS, SECTION_FIELD_MAP,
        EstimationMethod, ClusterLevel, RobustnessScore,
    )


# ═══════════════════════════════════════════════════════════════
# SQLite 索引
# ═══════════════════════════════════════════════════════════════

class SQLiteIndex:
    """
    SQLite 结构化索引。存储所有论文的摘要级数据，
    支持精确查询、聚合统计、方法-变量-机制关联。
    """

    def __init__(self, db_path: str = "workspace/knowledge_index.db"):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        """创建表结构"""
        c = self.conn.cursor()

        # ── 论文主表 ──
        c.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,           -- title 的 MD5 hash
                title TEXT NOT NULL,
                authors TEXT,
                source TEXT,
                pub_date TEXT,
                keywords TEXT,                       -- JSON array
                abstract TEXT,
                doi TEXT,
                fulltext_length INTEGER DEFAULT 0,
                overall_quality_score REAL DEFAULT 0.0,
                sections_completed TEXT,             -- JSON array
                last_updated TEXT
            )
        """)

        # ── 方法论索引（支持精确查询"哪些论文用了 DID？"）──
        c.execute("""
            CREATE TABLE IF NOT EXISTS methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT NOT NULL,
                estimation_method TEXT,              -- OLS/DID/RDD/...
                baseline_model_form TEXT,
                fixed_effects TEXT,                  -- JSON array
                standard_error_type TEXT,
                cluster_level TEXT,
                identification_strategy TEXT,
                endogeneity_strategy TEXT,
                methodological_rigor_score TEXT,
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
        """)

        # ── 变量索引（支持"碳排放强度的所有测度方式"查询）──
        c.execute("""
            CREATE TABLE IF NOT EXISTS variables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT NOT NULL,
                variable_name TEXT,                  -- 变量名
                variable_symbol TEXT,                -- 变量符号
                role TEXT,                           -- Y/X/control/mediator/moderator/IV
                definition TEXT,
                unit TEXT,
                data_source TEXT,
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
        """)

        # ── 机制索引 ──
        c.execute("""
            CREATE TABLE IF NOT EXISTS mechanisms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT NOT NULL,
                channel_name TEXT,
                mediator_variable TEXT,
                test_method TEXT,
                effect_direction TEXT,
                evidence_strength TEXT,
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
        """)

        # ── 异质性索引 ──
        c.execute("""
            CREATE TABLE IF NOT EXISTS heterogeneity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT NOT NULL,
                dimension TEXT,
                grouping_method TEXT,
                key_finding TEXT,
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
        """)

        # ── 系数/结果索引 ──
        c.execute("""
            CREATE TABLE IF NOT EXISTS coefficients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT NOT NULL,
                variable TEXT,
                coefficient REAL,
                standard_error REAL,
                significance TEXT,                   -- p<0.01/p<0.05/p<0.10/不显著
                is_core BOOLEAN DEFAULT 0,
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
        """)

        # ── 全文索引（用于 FTS 搜索 .md 文件内容）──
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS analysis_fts USING fts5(
                paper_id,
                section_key,
                content
            )
        """)

        self.conn.commit()

    # ─── 写入 ──────────────────────────────────────────────────

    def upsert_paper(self, summary: PaperSummary):
        """插入或更新一篇论文的完整索引"""
        paper_id = hashlib.md5(summary.paper_title.encode()).hexdigest()[:16]
        c = self.conn.cursor()

        # 主表
        c.execute("""
            INSERT OR REPLACE INTO papers
            (paper_id, title, authors, source, pub_date, keywords, abstract, doi,
             fulltext_length, overall_quality_score, sections_completed, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper_id,
            summary.paper_title,
            summary.authors,
            summary.source,
            summary.pub_date,
            json.dumps(summary.keywords, ensure_ascii=False),
            summary.abstract,
            summary.doi,
            summary.fulltext_length,
            summary.overall_quality_score,
            json.dumps(summary.sections_completed, ensure_ascii=False),
            datetime.now().isoformat(),
        ))

        # 方法表
        self._index_methods(paper_id, summary)

        # 变量表
        self._index_variables(paper_id, summary)

        # 机制表
        self._index_mechanisms(paper_id, summary)

        # 异质性表
        self._index_heterogeneity(paper_id, summary)

        # 系数表
        self._index_coefficients(paper_id, summary)

        # FTS
        self._index_fts(paper_id, summary)

        self.conn.commit()
        return paper_id

    def _index_methods(self, paper_id: str, s: PaperSummary):
        c = self.conn.cursor()
        # 从 section_05 提取
        methods_entries = []

        if s.section_05_methodology:
            sec = s.section_05_methodology
            methods_entries.append({
                "estimation_method": sec.estimation_method.value if sec.estimation_method else "",
                "baseline_model_form": sec.baseline_model_form,
                "fixed_effects": json.dumps(sec.fixed_effects, ensure_ascii=False),
                "standard_error_type": sec.standard_error_type.value if sec.standard_error_type else "",
                "cluster_level": sec.cluster_level.value if sec.cluster_level else "",
                "identification_strategy": "",
                "endogeneity_strategy": "",
                "methodological_rigor_score": sec.methodological_rigor_score,
            })

        # 从 section_03 (识别策略) 补充
        if s.section_03_identification:
            if methods_entries:
                methods_entries[0]["identification_strategy"] = s.section_03_identification.identification_strategy
            else:
                methods_entries.append({
                    "estimation_method": "",
                    "baseline_model_form": "",
                    "fixed_effects": "[]",
                    "standard_error_type": "",
                    "cluster_level": "",
                    "identification_strategy": s.section_03_identification.identification_strategy,
                    "endogeneity_strategy": "",
                    "methodological_rigor_score": "",
                })

        # 从 empirical 补充
        if s.empirical:
            if methods_entries:
                methods_entries[0]["endogeneity_strategy"] = s.empirical.endogeneity_strategy
                if not methods_entries[0]["estimation_method"] and s.empirical.estimation_method:
                    methods_entries[0]["estimation_method"] = s.empirical.estimation_method.value
            else:
                methods_entries.append({
                    "estimation_method": s.empirical.estimation_method.value if s.empirical.estimation_method else "",
                    "baseline_model_form": s.empirical.baseline_model_form,
                    "fixed_effects": json.dumps(s.empirical.fixed_effects, ensure_ascii=False),
                    "standard_error_type": s.empirical.standard_error_type.value if s.empirical.standard_error_type else "",
                    "cluster_level": s.empirical.cluster_level.value if s.empirical.cluster_level else "",
                    "identification_strategy": "",
                    "endogeneity_strategy": s.empirical.endogeneity_strategy,
                    "methodological_rigor_score": "",
                })

        for entry in methods_entries:
            c.execute("""
                INSERT INTO methods (paper_id, estimation_method, baseline_model_form,
                    fixed_effects, standard_error_type, cluster_level,
                    identification_strategy, endogeneity_strategy, methodological_rigor_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                paper_id, entry["estimation_method"], entry["baseline_model_form"],
                entry["fixed_effects"], entry["standard_error_type"], entry["cluster_level"],
                entry["identification_strategy"], entry["endogeneity_strategy"],
                entry["methodological_rigor_score"],
            ))

    def _index_variables(self, paper_id: str, s: PaperSummary):
        c = self.conn.cursor()
        entries = []

        def add_var(name, symbol, role, definition, unit, data_source):
            if name:
                entries.append((paper_id, name, symbol, role, definition, unit, data_source))

        # 从 section_04 提取
        if s.section_04_data:
            sec = s.section_04_data
            if sec.y_variable:
                add_var(sec.y_variable.name, sec.y_variable.symbol, "Y",
                        sec.y_variable.definition, sec.y_variable.unit, sec.y_variable.data_source)
            if sec.x_variable:
                add_var(sec.x_variable.name, sec.x_variable.symbol, "X",
                        sec.x_variable.definition, sec.x_variable.unit, sec.x_variable.data_source)
            for ctrl in sec.control_variables:
                add_var(ctrl.name, ctrl.symbol, "control",
                        ctrl.definition, ctrl.unit, ctrl.data_source)

        # 从 empirical 补充
        if s.empirical:
            emp = s.empirical
            if emp.y_var and not any(e[1] == emp.y_var for e in entries):
                add_var(emp.y_var, "", "Y", emp.y_definition, "", "")
            if emp.x_var and not any(e[1] == emp.x_var for e in entries):
                add_var(emp.x_var, "", "X", emp.x_definition, "", "")
            for mv in emp.mechanism_vars:
                if not any(e[1] == mv for e in entries):
                    add_var(mv, "", "mediator", "", "", "")
            for cv in emp.control_vars:
                if not any(e[1] == cv for e in entries):
                    add_var(cv, "", "control", "", "", "")

        c.executemany("""
            INSERT INTO variables (paper_id, variable_name, variable_symbol, role, definition, unit, data_source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, entries)

    def _index_mechanisms(self, paper_id: str, s: PaperSummary):
        c = self.conn.cursor()
        entries = []

        if s.section_08_mechanism:
            for ch in s.section_08_mechanism.mechanism_channels:
                entries.append((
                    paper_id, ch.name, ch.mediator_variable,
                    ch.test_method, ch.effect_direction, ch.evidence_strength,
                ))

        if s.empirical:
            for ch in s.empirical.mechanism_channels:
                entries.append((
                    paper_id, ch.name, ch.mediator_variable,
                    ch.test_method, ch.effect_direction, ch.evidence_strength,
                ))

        c.executemany("""
            INSERT INTO mechanisms (paper_id, channel_name, mediator_variable,
                test_method, effect_direction, evidence_strength)
            VALUES (?, ?, ?, ?, ?, ?)
        """, entries)

    def _index_heterogeneity(self, paper_id: str, s: PaperSummary):
        c = self.conn.cursor()
        entries = []

        if s.section_09_heterogeneity:
            for hd in s.section_09_heterogeneity.heterogeneity_dimensions:
                entries.append((paper_id, hd.dimension, hd.grouping_method, hd.key_finding))

        if s.empirical:
            for hd in s.empirical.heterogeneity_details:
                entries.append((paper_id, hd.dimension, hd.grouping_method, hd.key_finding))

        c.executemany("""
            INSERT INTO heterogeneity (paper_id, dimension, grouping_method, key_finding)
            VALUES (?, ?, ?, ?)
        """, entries)

    def _index_coefficients(self, paper_id: str, s: PaperSummary):
        c = self.conn.cursor()
        entries = []

        if s.section_06_baseline:
            for coeff in s.section_06_baseline.core_coefficient_table:
                entries.append((
                    paper_id, coeff.variable, coeff.coefficient,
                    coeff.standard_error, coeff.significance.value if coeff.significance else "",
                    True,
                ))

        if s.empirical:
            for coeff in s.empirical.key_coefficients:
                entries.append((
                    paper_id, coeff.variable, coeff.coefficient,
                    coeff.standard_error, coeff.significance.value if coeff.significance else "",
                    True,
                ))

        c.executemany("""
            INSERT INTO coefficients (paper_id, variable, coefficient, standard_error, significance, is_core)
            VALUES (?, ?, ?, ?, ?, ?)
        """, entries)

    def _index_fts(self, paper_id: str, s: PaperSummary):
        """将关键文本字段写入 FTS5 全文索引"""
        c = self.conn.cursor()

        # 删除旧记录
        c.execute("DELETE FROM analysis_fts WHERE paper_id = ?", (paper_id,))

        # 索引各维度信息
        section_data = [
            ("00_abstract", s.abstract),
        ]

        for num, field_name in SECTION_FIELD_MAP.items():
            section = getattr(s, field_name, None)
            if section is not None:
                # 提取关键文本字段
                parts = []
                for key, value in asdict(section).items():
                    if isinstance(value, str) and len(value) > 20:
                        parts.append(value)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str) and len(item) > 10:
                                parts.append(item)
                            elif isinstance(item, dict):
                                parts.append(json.dumps(item, ensure_ascii=False))
                section_data.append((num, " ".join(parts)))

        for sec_key, content in section_data:
            if content.strip():
                c.execute(
                    "INSERT INTO analysis_fts (paper_id, section_key, content) VALUES (?, ?, ?)",
                    (paper_id, sec_key, content[:5000]),
                )

    # ─── 查询 ──────────────────────────────────────────────────

    def get_paper(self, paper_id: str = None, title: str = None) -> Optional[Dict]:
        """获取单篇论文索引"""
        c = self.conn.cursor()
        if paper_id:
            c.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,))
        elif title:
            c.execute("SELECT * FROM papers WHERE title = ?", (title,))
        else:
            return None
        row = c.fetchone()
        return dict(row) if row else None

    def query_by_method(self, method: str) -> List[Dict]:
        """查询使用特定方法的论文"""
        c = self.conn.cursor()
        c.execute("""
            SELECT DISTINCT p.* FROM papers p
            JOIN methods m ON p.paper_id = m.paper_id
            WHERE m.estimation_method LIKE ? OR m.identification_strategy LIKE ?
        """, (f"%{method}%", f"%{method}%"))
        return [dict(r) for r in c.fetchall()]

    def query_by_variable(self, var_name: str, role: str = None) -> List[Dict]:
        """查询使用特定变量的论文"""
        c = self.conn.cursor()
        if role:
            c.execute("""
                SELECT DISTINCT p.*, v.role, v.definition FROM papers p
                JOIN variables v ON p.paper_id = v.paper_id
                WHERE v.variable_name LIKE ? AND v.role = ?
            """, (f"%{var_name}%", role))
        else:
            c.execute("""
                SELECT DISTINCT p.*, v.role, v.definition FROM papers p
                JOIN variables v ON p.paper_id = v.paper_id
                WHERE v.variable_name LIKE ?
            """, (f"%{var_name}%",))
        return [dict(r) for r in c.fetchall()]

    def query_by_mechanism(self, channel: str) -> List[Dict]:
        """查询使用特定机制的论文"""
        c = self.conn.cursor()
        c.execute("""
            SELECT DISTINCT p.*, m.channel_name, m.test_method, m.evidence_strength
            FROM papers p
            JOIN mechanisms m ON p.paper_id = m.paper_id
            WHERE m.channel_name LIKE ?
        """, (f"%{channel}%",))
        return [dict(r) for r in c.fetchall()]

    def query_by_heterogeneity(self, dimension: str) -> List[Dict]:
        """查询包含特定异质性维度的论文"""
        c = self.conn.cursor()
        c.execute("""
            SELECT DISTINCT p.*, h.dimension, h.key_finding
            FROM papers p
            JOIN heterogeneity h ON p.paper_id = h.paper_id
            WHERE h.dimension LIKE ?
        """, (f"%{dimension}%",))
        return [dict(r) for r in c.fetchall()]

    def fts_search(self, query: str, limit: int = 10) -> List[Dict]:
        """全文搜索分析内容"""
        c = self.conn.cursor()
        c.execute("""
            SELECT paper_id, section_key, snippet(analysis_fts, 2, '<b>', '</b>', '...', 40) as snippet
            FROM analysis_fts
            WHERE analysis_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit))
        return [dict(r) for r in c.fetchall()]

    # ─── 统计 ──────────────────────────────────────────────────

    def method_frequency(self) -> Dict[str, int]:
        """各方法的使用频率统计"""
        c = self.conn.cursor()
        c.execute("""
            SELECT estimation_method, COUNT(DISTINCT paper_id) as cnt
            FROM methods
            WHERE estimation_method != ''
            GROUP BY estimation_method
            ORDER BY cnt DESC
        """)
        return {r["estimation_method"]: r["cnt"] for r in c.fetchall()}

    def variable_frequency(self, role: str = None) -> Dict[str, int]:
        """各变量的使用频率统计"""
        c = self.conn.cursor()
        if role:
            c.execute("""
                SELECT variable_name, COUNT(DISTINCT paper_id) as cnt
                FROM variables WHERE role = ? AND variable_name != ''
                GROUP BY variable_name ORDER BY cnt DESC
            """, (role,))
        else:
            c.execute("""
                SELECT variable_name, COUNT(DISTINCT paper_id) as cnt
                FROM variables WHERE variable_name != ''
                GROUP BY variable_name ORDER BY cnt DESC
            """)
        return {r["variable_name"]: r["cnt"] for r in c.fetchall()}

    def mechanism_frequency(self) -> Dict[str, int]:
        """各机制渠道的使用频率统计"""
        c = self.conn.cursor()
        c.execute("""
            SELECT channel_name, COUNT(DISTINCT paper_id) as cnt
            FROM mechanisms WHERE channel_name != ''
            GROUP BY channel_name ORDER BY cnt DESC
        """)
        return {r["channel_name"]: r["cnt"] for r in c.fetchall()}

    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计概览"""
        c = self.conn.cursor()
        stats = {}
        c.execute("SELECT COUNT(*) as total FROM papers")
        stats["total_papers"] = c.fetchone()["total"]
        c.execute("SELECT COUNT(DISTINCT paper_id) as total FROM methods WHERE estimation_method != ''")
        stats["papers_with_methods"] = c.fetchone()["total"]
        c.execute("SELECT COUNT(DISTINCT variable_name) as total FROM variables WHERE variable_name != ''")
        stats["unique_variables"] = c.fetchone()["total"]
        c.execute("SELECT COUNT(DISTINCT channel_name) as total FROM mechanisms WHERE channel_name != ''")
        stats["unique_mechanisms"] = c.fetchone()["total"]
        c.execute("SELECT AVG(overall_quality_score) as avg_quality FROM papers")
        avg_q = c.fetchone()["avg_quality"]
        stats["avg_quality_score"] = round(avg_q, 2) if avg_q else 0.0
        return stats

    def close(self):
        self.conn.close()


# ═══════════════════════════════════════════════════════════════
# 内存倒排索引（快速关联查询，毫秒级）
# ═══════════════════════════════════════════════════════════════

class InvertedIndex:
    """
    内存倒排索引。从 PaperSummary 构建 method→papers, variable→papers,
    mechanism→papers 等映射，实现 O(1) 关联查询。
    """

    def __init__(self):
        self.method_index: Dict[str, List[str]] = {}       # "DID" → [paper_title, ...]
        self.variable_index: Dict[str, List[Dict]] = {}    # "碳排放" → [{paper, role, definition}, ...]
        self.mechanism_index: Dict[str, List[str]] = {}    # "创新驱动" → [paper_title, ...]
        self.heterogeneity_index: Dict[str, List[str]] = {}
        self.paper_index: Dict[str, PaperSummary] = {}     # paper_title → PaperSummary

    def index_paper(self, summary: PaperSummary):
        """索引单篇论文"""
        title = summary.paper_title
        self.paper_index[title] = summary

        # 方法索引
        methods = self._extract_methods(summary)
        for m in methods:
            self.method_index.setdefault(m, []).append(title)

        # 变量索引
        variables = self._extract_variables(summary)
        for v in variables:
            key = v["name"]
            self.variable_index.setdefault(key, []).append({
                "paper": title, "role": v["role"], "definition": v.get("definition", ""),
            })

        # 机制索引
        mechanisms = self._extract_mechanisms(summary)
        for m in mechanisms:
            self.mechanism_index.setdefault(m, []).append(title)

        # 异质性索引
        het_dims = self._extract_heterogeneity(summary)
        for h in het_dims:
            self.heterogeneity_index.setdefault(h, []).append(title)

    def _extract_methods(self, s: PaperSummary) -> List[str]:
        methods = set()
        # 方法别名映射（支持中英文查询）
        ALIASES = {
            "面板双向固定效应": ["DID", "FE", "固定效应", "panel_fe", "双向固定效应"],
            "双重差分": ["DID", "双重差分", "倍差法", "Difference-in-Differences"],
            "多时点DID": ["DID", "staggered_DID", "多时点DID", "多期DID", "交叠DID"],
            "三重差分": ["DDD", "三重差分"],
            "断点回归": ["RDD", "断点回归", "RD"],
            "工具变量2SLS": ["IV", "2SLS", "工具变量"],
            "系统GMM": ["GMM", "系统GMM"],
            "差分GMM": ["GMM", "差分GMM"],
            "倾向得分匹配": ["PSM", "倾向得分匹配"],
            "合成控制": ["SCM", "合成控制"],
            "Heckman两步法": ["Heckman", "样本选择"],
            "空间计量": ["空间计量", "SAR", "SEM", "SDM"],
            "双重机器学习": ["DML", "双重机器学习", "机器学习"],
            "OLS": ["OLS"],
        }
        if s.section_05_methodology and s.section_05_methodology.estimation_method:
            m = s.section_05_methodology.estimation_method
            if isinstance(m, str):
                methods.add(m)
                # 找别名
                for key, aliases in ALIASES.items():
                    if m in key or key in m:
                        methods.update(aliases)
            else:
                methods.add(m.value if hasattr(m, 'value') else str(m))
        if s.section_03_identification and s.section_03_identification.identification_strategy:
            for keyword in ["DID", "双重差分", "RDD", "断点", "IV", "工具变量", "PSM", "SCM",
                          "合成控制", "GMM", "Heckman", "事件史", "DML", "机器学习"]:
                if keyword in s.section_03_identification.identification_strategy:
                    methods.add(keyword)
        if s.empirical and s.empirical.estimation_method:
            em = s.empirical.estimation_method
            m_val = em.value if hasattr(em, 'value') else str(em)
            methods.add(m_val)
        return list(methods) if methods else ["未提取"]

    def _extract_variables(self, s: PaperSummary) -> List[Dict]:
        variables = []
        # Y
        y_var = ""
        if s.section_04_data and s.section_04_data.y_variable:
            y_var = s.section_04_data.y_variable.name
        if not y_var and s.empirical:
            y_var = s.empirical.y_var
        if y_var:
            variables.append({"name": y_var, "role": "Y",
                            "definition": s.section_04_data.y_variable.definition if s.section_04_data and s.section_04_data.y_variable else ""})

        # X
        x_var = ""
        if s.section_04_data and s.section_04_data.x_variable:
            x_var = s.section_04_data.x_variable.name
        if not x_var and s.empirical:
            x_var = s.empirical.x_var
        if x_var:
            variables.append({"name": x_var, "role": "X", "definition": ""})

        # Controls
        if s.section_04_data:
            for ctrl in s.section_04_data.control_variables:
                variables.append({"name": ctrl.name, "role": "control", "definition": ctrl.definition})

        # Mechanism vars
        if s.empirical:
            for mv in s.empirical.mechanism_vars:
                variables.append({"name": mv, "role": "mediator", "definition": ""})

        return variables

    def _extract_mechanisms(self, s: PaperSummary) -> List[str]:
        mechanisms = set()
        if s.section_08_mechanism:
            for ch in s.section_08_mechanism.mechanism_channels:
                mechanisms.add(ch.name)
        if s.empirical:
            for ch in s.empirical.mechanism_channels:
                mechanisms.add(ch.name)
        return list(mechanisms)

    def _extract_heterogeneity(self, s: PaperSummary) -> List[str]:
        dims = set()
        if s.section_09_heterogeneity:
            for hd in s.section_09_heterogeneity.heterogeneity_dimensions:
                dims.add(hd.dimension)
        if s.empirical:
            for hd in s.empirical.heterogeneity_details:
                dims.add(hd.dimension)
        return list(dims)

    # ─── 查询 ──────────────────────────────────────────────────

    def find_papers_by_method(self, method: str) -> List[str]:
        """查找使用特定方法的所有论文"""
        results = []
        for key, papers in self.method_index.items():
            if method.lower() in key.lower():
                results.extend(papers)
        return list(set(results))

    def find_papers_by_variable(self, var_name: str) -> List[Dict]:
        """查找使用特定变量的所有论文及角色"""
        results = []
        for key, entries in self.variable_index.items():
            if var_name.lower() in key.lower():
                results.extend(entries)
        return results

    def find_papers_by_mechanism(self, channel: str) -> List[str]:
        """查找使用特定机制的论文"""
        results = []
        for key, papers in self.mechanism_index.items():
            if channel.lower() in key.lower():
                results.extend(papers)
        return list(set(results))

    def get_method_distribution(self) -> Dict[str, int]:
        """方法分布统计"""
        return {k: len(set(v)) for k, v in self.method_index.items()}

    def get_paper(self, title: str) -> Optional[PaperSummary]:
        return self.paper_index.get(title)

    def get_all_titles(self) -> List[str]:
        return list(self.paper_index.keys())

    def size(self) -> int:
        return len(self.paper_index)


# ═══════════════════════════════════════════════════════════════
# 向量存储接口（可选，用于 RAG 语义搜索）
# ═══════════════════════════════════════════════════════════════

class VectorStore:
    """
    向量存储接口。支持 ChromaDB（推荐）和 FAISS 两种后端。

    需要 pip install chromadb 或 pip install faiss-cpu

    使用方式：
      store = VectorStore(backend="chromadb")
      store.index_paper_analyses(paper_title, analysis_md_files)
      results = store.semantic_search("DID方法的标准误聚类层级")
    """

    def __init__(self, backend: str = "chromadb", persist_dir: str = "workspace/vector_store"):
        self.backend = backend
        self.persist_dir = os.path.abspath(persist_dir)
        self._client = None
        self._collection = None
        self._available = False

        if backend == "chromadb":
            self._init_chromadb()
        elif backend == "faiss":
            self._init_faiss()

    def _init_chromadb(self):
        try:
            import chromadb
            os.makedirs(self.persist_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = self._client.get_or_create_collection(
                name="paper_analyses",
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            print(f"[VectorStore] ChromaDB 初始化成功 → {self.persist_dir}")
        except ImportError:
            print("[VectorStore] ChromaDB 未安装 (pip install chromadb)，向量搜索不可用")
        except Exception as e:
            print(f"[VectorStore] ChromaDB 初始化失败: {e}")

    def _init_faiss(self):
        try:
            import faiss
            import numpy as np
            self._faiss = faiss
            self._np = np
            self._index = None
            self._documents = []
            self._available = True
            print("[VectorStore] FAISS 初始化成功")
        except ImportError:
            print("[VectorStore] FAISS 未安装 (pip install faiss-cpu)，向量搜索不可用")

    @property
    def is_available(self) -> bool:
        return self._available

    def index_paper_analyses(self, paper_title: str, section_texts: Dict[str, str]):
        """
        索引一篇论文的所有分析文件。
        :param paper_title: 论文标题
        :param section_texts: {"01_introduction": "分析文本...", "05_methodology": "...", ...}
        """
        if not self._available:
            return

        if self.backend == "chromadb":
            ids = []
            documents = []
            metadatas = []
            for section_key, text in section_texts.items():
                if len(text) < 50:
                    continue
                # 智能分块：按段落分割，每块不超过 2000 字符
                chunks = self._chunk_text(text, chunk_size=2000)
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{paper_title[:40]}_{section_key}_chunk{i}"
                    ids.append(chunk_id)
                    documents.append(chunk)
                    metadatas.append({
                        "paper": paper_title,
                        "section": section_key,
                        "chunk_index": i,
                    })

            if ids:
                # 删除旧记录
                old_ids = self._collection.get(where={"paper": paper_title})
                if old_ids and old_ids["ids"]:
                    self._collection.delete(ids=old_ids["ids"])

                self._collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                )
                print(f"[VectorStore] 索引 {paper_title[:40]} → {len(ids)} chunks")

    def semantic_search(self, query: str, top_k: int = 10,
                        filter_paper: str = None) -> List[Dict]:
        """
        语义搜索。
        :param query: 查询文本
        :param top_k: 返回结果数
        :param filter_paper: 限定某篇论文
        """
        if not self._available:
            return []

        if self.backend == "chromadb":
            where_filter = {"paper": filter_paper} if filter_paper else None
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter,
            )
            output = []
            if results and results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    output.append({
                        "id": doc_id,
                        "document": results["documents"][0][i] if results["documents"] else "",
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else None,
                    })
            return output

        return []

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> List[str]:
        """将长文本按段落智能分块"""
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # 重叠：保留上一块的末尾
                if len(current_chunk) > overlap:
                    current_chunk = current_chunk[-overlap:] + para + "\n\n"
                else:
                    current_chunk = para + "\n\n"
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        return chunks

    def close(self):
        pass  # ChromaDB 自动持久化


# ═══════════════════════════════════════════════════════════════
# 统一知识索引入口
# ═══════════════════════════════════════════════════════════════

class KnowledgeIndex:
    """
    统一知识索引 — 全流程的唯一数据访问入口。

    使用方式：
      ki = KnowledgeIndex()
      ki.index_paper(paper_summary)           # 索引一篇论文
      papers = ki.find_by_method("DID")       # 精确查询
      papers = ki.find_by_variable("碳排放")  # 变量查询
      stats = ki.get_stats()                  # 统计概览
      results = ki.semantic_search("...")     # 语义搜索（需向量存储）
    """

    def __init__(
        self,
        sqlite_path: str = "workspace/knowledge_index.db",
        vector_backend: str = "chromadb",
        vector_dir: str = "workspace/vector_store",
    ):
        self.sqlite = SQLiteIndex(sqlite_path)
        self.inverted = InvertedIndex()
        self.vector = VectorStore(backend=vector_backend, persist_dir=vector_dir)

    # ─── 索引 ──────────────────────────────────────────────────

    def index_paper(self, summary: PaperSummary, section_md_files: Dict[str, str] = None):
        """
        索引一篇论文的完整信息。
        :param summary: PaperSummary 实例
        :param section_md_files: 可选，各维度 .md 分析文件内容（用于向量索引）
        """
        self.sqlite.upsert_paper(summary)
        self.inverted.index_paper(summary)
        if section_md_files and self.vector.is_available:
            self.vector.index_paper_analyses(summary.paper_title, section_md_files)

    def index_paper_batch(self, summaries: List[PaperSummary]):
        """批量索引"""
        for s in summaries:
            self.index_paper(s)

    # ─── 查询 ──────────────────────────────────────────────────

    def find_by_method(self, method: str) -> List[str]:
        """查找使用特定方法的论文"""
        return self.inverted.find_papers_by_method(method)

    def find_by_variable(self, var_name: str) -> List[Dict]:
        """查找使用特定变量的论文"""
        return self.inverted.find_papers_by_variable(var_name)

    def find_by_mechanism(self, channel: str) -> List[str]:
        """查找使用特定机制的论文"""
        return self.inverted.find_papers_by_mechanism(channel)

    def get_method_stats(self) -> Dict[str, int]:
        """方法频率统计"""
        return self.inverted.get_method_distribution()

    def get_sqlite_stats(self) -> Dict[str, Any]:
        """SQLite 中的详细统计"""
        return self.sqlite.get_stats()

    def get_all_stats(self) -> Dict[str, Any]:
        """获取完整统计概览"""
        inv_stats = {
            "total_indexed": self.inverted.size(),
            "method_distribution": self.get_method_stats(),
        }
        sql_stats = self.get_sqlite_stats()
        return {**inv_stats, "sqlite": sql_stats}

    def semantic_search(self, query: str, top_k: int = 10, paper_filter: str = None) -> List[Dict]:
        """语义搜索（需向量存储可用）"""
        return self.vector.semantic_search(query, top_k, paper_filter)

    def fts_search(self, query: str, limit: int = 10) -> List[Dict]:
        """全文搜索（SQLite FTS5）"""
        return self.sqlite.fts_search(query, limit)

    @property
    def vector_available(self) -> bool:
        return self.vector.is_available

    def close(self):
        self.sqlite.close()
        self.vector.close()


# ═══════════════════════════════════════════════════════════════
# 从现有 workspace 构建索引的迁移工具
# ═══════════════════════════════════════════════════════════════

def build_index_from_workspace(
    workspace_root: str = "workspace",
    db_path: str = "workspace/knowledge_index.db",
) -> KnowledgeIndex:
    """
    从现有 workspace/analysis 中的所有 JSON 文件构建知识索引。
    用于从旧格式迁移到新 Schema。
    """
    import re
    from glob import glob

    ki = KnowledgeIndex(sqlite_path=db_path)

    analysis_root = os.path.join(workspace_root, "analysis")
    if not os.path.exists(analysis_root):
        print(f"[KnowledgeIndex] 未找到分析目录: {analysis_root}")
        return ki

    # 扫描所有 _paper_summary.json
    paper_dirs = []
    for dname in os.listdir(analysis_root):
        paper_dir = os.path.join(analysis_root, dname)
        if os.path.isdir(paper_dir) and not dname.startswith("_"):
            summary_path = os.path.join(paper_dir, "_paper_summary.json")
            if os.path.exists(summary_path):
                paper_dirs.append((dname, paper_dir, summary_path))

    # 也扫描已归档项目
    projects_root = os.path.join(workspace_root, "projects")
    if os.path.exists(projects_root):
        for proj_name in os.listdir(projects_root):
            proj_analysis = os.path.join(projects_root, proj_name, "analysis")
            if not os.path.exists(proj_analysis):
                continue
            for dname in os.listdir(proj_analysis):
                paper_dir = os.path.join(proj_analysis, dname)
                if os.path.isdir(paper_dir) and not dname.startswith("_"):
                    summary_path = os.path.join(paper_dir, "_paper_summary.json")
                    if os.path.exists(summary_path) and summary_path not in [p[2] for p in paper_dirs]:
                        paper_dirs.append((dname, paper_dir, summary_path))

    print(f"[KnowledgeIndex] 发现 {len(paper_dirs)} 篇论文的分析数据，开始构建索引...")

    for i, (dname, paper_dir, summary_path) in enumerate(paper_dirs):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 构建 PaperSummary（从旧格式适配）
            try:
                summary = _convert_old_summary_to_new(data, paper_dir)
            except Exception as conv_err:
                print(f"    ⚠ 格式转换失败: {conv_err}，使用最小化 PaperSummary")
                # 最小化回退
                from skills.schemas import PaperSummary
                summary = PaperSummary(
                    paper_title=data.get("paper_title", dname),
                    authors=data.get("authors", ""),
                    abstract=data.get("abstract", ""),
                )

            # 收集 .md 文件用于向量索引
            md_files = {}
            for fname in os.listdir(paper_dir):
                if fname.endswith(".md") and not fname.startswith("_"):
                    with open(os.path.join(paper_dir, fname), "r", encoding="utf-8") as f:
                        md_files[fname.replace(".md", "")] = f.read()[:3000]

            ki.index_paper(summary, md_files)
            print(f"  [{i+1}/{len(paper_dirs)}] ✓ {summary.paper_title[:50]}")

        except Exception as e:
            print(f"  [{i+1}/{len(paper_dirs)}] ✗ {dname[:50]}: {e}")

    stats = ki.get_all_stats()
    print(f"\n[KnowledgeIndex] 索引构建完成: {stats['total_indexed']} 篇论文")
    print(f"[KnowledgeIndex] 方法分布: {stats.get('method_distribution', {})}")
    return ki


def _convert_old_summary_to_new(data: dict, paper_dir: str) -> PaperSummary:
    """将旧格式 _paper_summary.json 转换为新的 PaperSummary"""
    sections = data.get("sections", {})

    def get_section(key):
        return sections.get(key, {})

    # 构建各维度（从旧格式的简单 dict 映射到新 Schema）
    s01 = _build_s01(get_section("01_introduction"))
    s02 = _build_s02(get_section("02_theoretical_framework"))
    s03 = _build_s03(get_section("03_identification"))
    s04 = _build_s04(get_section("04_data_variables"))
    s05 = _build_s05(get_section("05_empirical_methodology"))
    s06 = _build_s06(get_section("06_baseline_results"))
    s07 = _build_s07(get_section("07_robustness"))
    s08 = _build_s08(get_section("08_mechanism"))
    s09 = _build_s09(get_section("09_heterogeneity"))
    s10 = _build_s10(get_section("10_endogeneity"))
    s11 = _build_s11(get_section("11_conclusion"))
    emp = _build_empirical(get_section("empirical"))

    # 计算已完成的维度
    all_sections = [s01, s02, s03, s04, s05, s06, s07, s08, s09, s10, s11]
    completed = [f"{i+1:02d}" for i, s in enumerate(all_sections) if s is not None]

    from skills.schemas import compute_quality_score
    overall_score = round(
        sum(compute_quality_score(s) for s in all_sections if s is not None) / max(len(completed), 1), 2
    )

    return PaperSummary(
        paper_title=data.get("paper_title", ""),
        authors=data.get("authors", ""),
        source=data.get("source", ""),
        pub_date=data.get("pub_date", ""),
        keywords=data.get("keywords", []),
        abstract=data.get("abstract", ""),
        doi=data.get("doi", ""),
        fulltext=data.get("fulltext", ""),
        fulltext_length=len(data.get("fulltext", "")),
        section_01_introduction=s01,
        section_02_theoretical=s02,
        section_03_identification=s03,
        section_04_data=s04,
        section_05_methodology=s05,
        section_06_baseline=s06,
        section_07_robustness=s07,
        section_08_mechanism=s08,
        section_09_heterogeneity=s09,
        section_10_endogeneity=s10,
        section_11_conclusion=s11,
        empirical=emp,
        sections_completed=completed,
        overall_quality_score=overall_score,
        last_updated=datetime.now().isoformat(),
    )


def _build_s01(d: dict):
    if not d or not d.get("key_findings"):
        return None
    from skills.schemas import Section01Introduction, compute_quality_score
    s = Section01Introduction(
        research_question=d.get("research_question", ""),
        question_type=_parse_enum(d.get("question_type", "")),
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s

def _build_s02(d: dict):
    if not d or not d.get("key_findings"):
        return None
    from skills.schemas import Section02TheoreticalFramework, HypothesisEntry, compute_quality_score
    s = Section02TheoreticalFramework(
        theories_used=d.get("theories_used", []) if isinstance(d.get("theories_used"), list) else [],
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s

def _build_s03(d: dict):
    if not d or not d.get("key_findings"):
        return None
    from skills.schemas import Section03Identification, compute_quality_score
    s = Section03Identification(
        identification_strategy=d.get("identification_strategy", ""),
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s

def _build_s04(d: dict):
    if not d or not d.get("key_findings"):
        return None
    from skills.schemas import Section04DataVariables, compute_quality_score
    s = Section04DataVariables(
        data_source=d.get("data_source", ""),
        data_structure=d.get("data_structure", ""),
        sample_period=d.get("sample_period", ""),
        sample_size=d.get("sample_size", ""),
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s

def _build_s05(d: dict):
    if not d or not d.get("key_findings"):
        return None
    from skills.schemas import Section05EmpiricalMethodology, compute_quality_score
    s = Section05EmpiricalMethodology(
        baseline_model_form=d.get("baseline_model_form", ""),
        estimation_method=_parse_estimation(d.get("estimation_method", "")),
        fixed_effects=d.get("fixed_effects", []) if isinstance(d.get("fixed_effects"), list) else [],
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s

def _build_s06(d: dict):
    if not d or not d.get("key_findings"):
        return None
    from skills.schemas import Section06BaselineResults, compute_quality_score
    s = Section06BaselineResults(
        core_coefficient_sign=d.get("core_coefficient_sign", ""),
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s

def _build_s07(d: dict):
    if not d or not d.get("key_findings"):
        return None
    from skills.schemas import Section07Robustness, compute_quality_score
    s = Section07Robustness(
        robustness_checks_performed=d.get("robustness_checks_performed", []) if isinstance(d.get("robustness_checks_performed"), list) else d.get("robustness_checks", []) if isinstance(d.get("robustness_checks"), list) else [],
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s

def _build_s08(d: dict):
    if not d or not d.get("key_findings"):
        return None
    from skills.schemas import Section08Mechanism, compute_quality_score
    channels = d.get("mechanism_channels", [])
    if isinstance(channels, list):
        channels = [_parse_mechanism_channel(ch) for ch in channels]
    s = Section08Mechanism(
        mechanism_channels=channels,
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s

def _build_s09(d: dict):
    if not d or not d.get("key_findings"):
        return None
    from skills.schemas import Section09Heterogeneity, compute_quality_score
    dims = d.get("heterogeneity_dimensions", [])
    if isinstance(dims, list):
        dims = [_parse_het_dim(h) for h in dims]
    s = Section09Heterogeneity(
        heterogeneity_dimensions=dims,
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s

def _build_s10(d: dict):
    if not d or not d.get("key_findings"):
        return None
    from skills.schemas import Section10Endogeneity, compute_quality_score
    s = Section10Endogeneity(
        treatment_method=d.get("treatment_method", ""),
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s

def _build_s11(d: dict):
    if not d or not d.get("key_findings"):
        return None
    from skills.schemas import Section11Conclusion, compute_quality_score
    s = Section11Conclusion(
        core_conclusions=d.get("core_conclusions", []) if isinstance(d.get("core_conclusions"), list) else [],
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s

def _build_empirical(d: dict):
    if not d:
        return None
    from skills.schemas import EmpiricalAnalysis, HypothesisEntry, compute_quality_score
    hyps = d.get("hypotheses", {})
    if isinstance(hyps, dict):
        try:
            hyps = [HypothesisEntry(id=str(k), content=str(v)[:200]) for k, v in hyps.items()]
        except Exception:
            hyps = []
    elif isinstance(hyps, list):
        hyps = []
    else:
        hyps = []
    s = EmpiricalAnalysis(
        title=d.get("title", ""),
        hypotheses=hyps,
        model_type=d.get("model_type", ""),
        endogeneity_strategy=d.get("endogeneity_strategy", ""),
        y_var=d.get("y_var", ""),
        x_var=d.get("x_var", ""),
        mechanism_vars=d.get("mechanism_vars", []) if isinstance(d.get("mechanism_vars"), list) else [],
        heterogeneity_dims=d.get("heterogeneity_dims", []) if isinstance(d.get("heterogeneity_dims"), list) else [],
        robustness_checks=d.get("robustness_checks", []) if isinstance(d.get("robustness_checks"), list) else [],
        key_results=d.get("key_results", []) if isinstance(d.get("key_results"), list) else [],
        key_findings=d.get("key_findings", []) if isinstance(d.get("key_findings"), list) else [],
        gaps=d.get("gaps", []) if isinstance(d.get("gaps"), list) else [],
    )
    s.quality_score = compute_quality_score(s)
    return s


# ─── 解析辅助 ──────────────────────────────────────────────────

def _parse_enum(val: str):
    """尝试解析枚举值，失败返回原字符串"""
    return val

def _parse_estimation(val: str):
    from skills.schemas import EstimationMethod
    for member in EstimationMethod:
        if member.value in val or val in member.value:
            return member
    return EstimationMethod.OTHER

def _parse_mechanism_channel(ch):
    from skills.schemas import MechanismChannel
    if isinstance(ch, MechanismChannel):
        return ch
    if isinstance(ch, dict):
        return MechanismChannel(
            name=ch.get("name", ch.get("channel_name", "")),
            mediator_variable=ch.get("mediator_variable", ""),
            test_method=ch.get("test_method", ""),
            evidence_strength=ch.get("evidence_strength", ""),
        )
    if isinstance(ch, str):
        return MechanismChannel(name=ch)
    return MechanismChannel()

def _parse_het_dim(h):
    from skills.schemas import HeterogeneityDimension
    if isinstance(h, HeterogeneityDimension):
        return h
    if isinstance(h, dict):
        return HeterogeneityDimension(
            dimension=h.get("dimension", h.get("name", "")),
            key_finding=h.get("key_finding", h.get("finding", "")),
        )
    if isinstance(h, str):
        return HeterogeneityDimension(dimension=h)
    return HeterogeneityDimension()


# ═══════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--build":
        print("从现有 workspace 构建知识索引...")
        ki = build_index_from_workspace()
        stats = ki.get_all_stats()
        print("\n索引统计:")
        print(f"  论文总数: {stats['total_indexed']}")
        print(f"  方法分布: {stats.get('method_distribution', {})}")
        print(f"  SQLite 统计: {stats.get('sqlite', {})}")
        ki.close()
    elif len(sys.argv) > 1 and sys.argv[1] == "--stats":
        ki = KnowledgeIndex()
        stats = ki.get_all_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        ki.close()
    else:
        print("用法:")
        print("  python knowledge_index.py --build   # 从 workspace 构建索引")
        print("  python knowledge_index.py --stats   # 查看索引统计")
