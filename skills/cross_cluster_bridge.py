"""
跨集群桥梁发现引擎 — 在看似无关的文献集群之间检测理论连接。

核心算法：
1. 从 _paper_summary.json 提取所有机制节点（X→M→Y 因果链片段）
2. 将论文聚类为主题集群（基于关键词+变量相似度）
3. 对每一对集群，运行 5 维桥梁检测（LLM驱动）
4. 对所有桥梁按"理论严谨性×创新度×可行性"排序
5. 输出排序后的候选创新题目 → 作为 Step 1 增强选题的输入

设计原则：
- 不是随机的"排列组合"，而是被理论严格约束的"因果链嫁接"
- 只有当来源集群的机制逻辑可以自然延伸到目标集群的情境时，这个桥梁才成立
- LLM 负责5维分析，确定性算法负责集群识别和评分
"""

from __future__ import annotations
import os
import json
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import asdict

from skills.base import BaseSkill
from skills.llm_client import LlmClient, dataclass_to_json_schema
from skills.schemas import (
    PaperCluster, ClusterBridge, MechanismNode, MechanismNetwork,
    TransplantableMechanism, VariableRole, ContradictoryTension,
    CrossClusterInnovationReport, dataclass_to_dict,
    extract_mechanism_nodes_from_summaries,
    cluster_papers_by_topic,
)
from skills.quality_gate import QualityGate


class CrossClusterBridgeDetector(BaseSkill):
    """
    跨集群桥梁发现引擎。

    使用方式：
      detector = CrossClusterBridgeDetector()
      report = detector.run(
          paper_summaries=[...],
          cross_synthesis={...},
      )
      # report.ranked_topics 包含按创新评分排序的候选题目
    """

    def __init__(self):
        super().__init__(
            name="CrossClusterBridgeDetector",
            description="跨集群理论桥梁发现——在看似无关的文献之间挖掘创新题目"
        )
        self.llm = LlmClient()
        self._prompts_dir = os.path.abspath("references/prompts")

    def execute(self, action: str, **kwargs):
        if action == "run":
            return self.run(**kwargs)
        elif action == "cluster_only":
            return self._cluster_only(**kwargs)
        elif action == "detect_bridge":
            return self._detect_single_bridge(**kwargs)
        else:
            raise NotImplementedError(f"未实现: {action}")

    # ═══════════════════════════════════════════════════════════
    # 主流程
    # ═══════════════════════════════════════════════════════════

    def run(
        self,
        paper_summaries: List[Dict] = None,
        cross_synthesis: Dict = None,
        backend: str = None,
        model: str = None,
    ) -> Dict:
        """
        主入口：跨集群桥梁发现的完整流程。

        :param paper_summaries: _paper_summary.json 列表
        :param cross_synthesis: 跨论文对比数据（已有）
        :return: CrossClusterInnovationReport dict
        """
        print(f"\n[{self.name}] ╔══════════════════════════════════════╗")
        print(f"[{self.name}] ║  Step 0: 跨集群桥梁发现                ║")
        print(f"[{self.name}] ╚══════════════════════════════════════╝")

        paper_summaries = paper_summaries or []
        print(f"[{self.name}] 论文池: {len(paper_summaries)} 篇")

        # ── 0a: 提取机制节点 ──
        print(f"\n[{self.name}] 0a: 提取机制节点...")
        mechanism_nodes = extract_mechanism_nodes_from_summaries(paper_summaries)
        print(f"[{self.name}]   提取到 {len(mechanism_nodes)} 个机制节点")

        # ── 0b: 主题聚类 ──
        print(f"\n[{self.name}] 0b: 主题聚类...")
        clusters = cluster_papers_by_topic(paper_summaries)
        # 为每个集群填充机制池
        for cluster in clusters:
            cluster_nodes = [
                n for n in mechanism_nodes
                if n.paper_title in cluster.papers
            ]
            cluster.mechanism_pool = list(set(
                n.mechanism_name for n in cluster_nodes if n.mechanism_name
            ))
            # 收集理论
            all_theories = set()
            for ps in paper_summaries:
                if ps.get("paper_title") in cluster.papers:
                    sections = ps.get("sections", {})
                    theory = sections.get("02_theoretical_framework", {})
                    for t in (theory.get("theories_used", []) or []):
                        if isinstance(t, str):
                            all_theories.add(t)
            cluster.common_theories = list(all_theories)[:10]

        print(f"[{self.name}]   识别到 {len(clusters)} 个主题集群:")
        for c in clusters:
            print(f"     [{c.cluster_id}] {c.cluster_label[:60]} ({c.paper_count} 篇)")
            if c.common_x_vars:
                print(f"       X: {c.common_x_vars}")
            if c.common_y_vars:
                print(f"       Y: {c.common_y_vars}")

        # ── 0c: 构建机制网络 ──
        print(f"\n[{self.name}] 0c: 构建机制网络...")
        network = self._build_mechanism_network(mechanism_nodes, clusters, paper_summaries)
        print(f"[{self.name}]   共享变量: {len(network.shared_variables)} 个")
        print(f"[{self.name}]   共享机制: {len(network.shared_mechanisms)} 个")
        print(f"[{self.name}]   可嫁接因果链: {len(network.graftable_chains)} 条")

        # ── 0d: 逐对集群桥梁检测 ──
        print(f"\n[{self.name}] 0d: 跨集群桥梁检测...")
        all_bridges = []

        if len(clusters) >= 2:
            # 过滤：只保留"真正不同"的集群对
            cluster_pairs = self._filter_meaningful_pairs(clusters)

            print(f"[{self.name}]   有效集群对: {len(cluster_pairs)}/{len(clusters)*(len(clusters)-1)//2} 对")
            if len(cluster_pairs) == 0:
                print(f"[{self.name}]   无有效跨集群对（所有论文主题高度相似），使用集群内回退")
                all_bridges = [self._build_single_cluster_fallback(
                    max(clusters, key=lambda c: c.paper_count),
                    paper_summaries, mechanism_nodes,
                )]

            for ca, cb in cluster_pairs:
                print(f"\n  [{ca.cluster_id}]×[{cb.cluster_id}] 桥梁检测...")
                bridge = self._detect_single_bridge(
                    cluster_a=ca,
                    cluster_b=cb,
                    paper_summaries=paper_summaries,
                    mechanism_nodes=mechanism_nodes,
                    network=network,
                    cross_synthesis=cross_synthesis,
                    backend=backend,
                    model=model,
                )
                if bridge.get("overall_score", 0) > 0:
                    all_bridges.append(bridge)
                    print(f"    桥梁: {bridge.get('bridge_theory_name', 'N/A')}")
                    print(f"    评分: innovation={bridge.get('innovation_score', 0):.1f} "
                          f"theory={bridge.get('theoretical_rigor_score', 0):.1f} "
                          f"feasibility={bridge.get('feasibility_score', 0):.1f}")
                    print(f"    候选题目: {len(bridge.get('candidate_topics', []))} 个")
                else:
                    print(f"    未发现有效桥梁")
        else:
            print(f"[{self.name}]   少于2个集群，跳过桥梁检测")
            # 单个集群：仍可做集群内创新检测
            all_bridges = [self._build_single_cluster_fallback(clusters[0], paper_summaries, mechanism_nodes)]

        # ── 0e: 汇总排序 ──
        print(f"\n[{self.name}] 0e: 汇总排序...")
        ranked_topics = self._rank_topics(all_bridges)
        print(f"[{self.name}]   候选题目总数: {len(ranked_topics)}")

        # ── 组装报告 ──
        report = CrossClusterInnovationReport(
            paper_pool_size=len(paper_summaries),
            clusters_identified=clusters,
            mechanism_network=network,
            cluster_bridges=all_bridges,
            ranked_topics=ranked_topics,
            methodological_recommendations=self._extract_method_recommendations(all_bridges),
            generated_at=datetime.now().isoformat(),
            total_bridges_found=len(all_bridges),
            quality_score=sum(b.get("overall_score", 0) for b in all_bridges) / max(len(all_bridges), 1) / 10,
        )

        # 保存报告
        report_path = os.path.join(
            os.path.abspath("workspace/writing"), "cross_cluster_bridge_report.json"
        )
        report_dict = dataclass_to_dict(report)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)

        print(f"\n[{self.name}] ╔══════════════════════════════════════════╗")
        print(f"[{self.name}] ║  桥梁发现完成                            ║")
        print(f"[{self.name}] ║  集群: {len(clusters)} | 桥梁: {len(all_bridges)} | 题目: {len(ranked_topics)}     ║")
        print(f"[{self.name}] ║  报告: {report_path}")
        print(f"[{self.name}] ╚══════════════════════════════════════════╝")

        return {
            "success": True,
            "report": report_dict,
            "path": report_path,
            "bridge_count": len(all_bridges),
            "topic_count": len(ranked_topics),
        }

    # ═══════════════════════════════════════════════════════════
    # 核心方法
    # ═══════════════════════════════════════════════════════════

    def _detect_single_bridge(
        self,
        cluster_a: PaperCluster,
        cluster_b: PaperCluster,
        paper_summaries: List[Dict],
        mechanism_nodes: List[MechanismNode],
        network: MechanismNetwork = None,
        cross_synthesis: Dict = None,
        backend: str = None,
        model: str = None,
    ) -> Dict:
        """
        对一对集群运行 5 维桥梁检测。

        使用 LLM 做深度分析，输出 ClusterBridge JSON。
        """

        # 构建集群摘要
        ca_summary = self._build_cluster_summary(
            cluster_a, paper_summaries, mechanism_nodes
        )
        cb_summary = self._build_cluster_summary(
            cluster_b, paper_summaries, mechanism_nodes
        )

        # 加载桥梁检测 Prompt
        prompt = self._build_bridge_detection_prompt(
            cluster_a, cluster_b, ca_summary, cb_summary, network, cross_synthesis
        )

        # 用 structured_output 生成 ClusterBridge
        output_schema = dataclass_to_json_schema(ClusterBridge)
        gate = QualityGate(threshold=0.25)

        try:
            bridge_dict = self.llm.structured_output(
                prompt=prompt,
                output_schema=output_schema,
                system_prompt="你是一位经济学理论研究者，擅长在看似无关的研究领域之间发现深层理论连接。请严格遵循5维分析框架进行分析。如果确实不存在有理论支撑的桥梁，请给出空结果。",
                backend=backend,
                model=model,
                max_tokens=8000,
                max_retries=2,
                quality_validator=gate.make_validator("bridge"),
            )
        except Exception as e:
            print(f"    LLM 桥梁检测失败: {e}")
            return {"overall_score": 0, "bridge_theory_name": "", "candidate_topics": []}

        # 计算评分
        innovation = float(bridge_dict.get("innovation_score", 5))
        theory = float(bridge_dict.get("theoretical_rigor_score", 5))
        feasibility = float(bridge_dict.get("feasibility_score", 5))
        bridge_dict["overall_score"] = round(innovation * 0.40 + theory * 0.35 + feasibility * 0.25, 1)
        bridge_dict["id"] = f"bridge_{cluster_a.cluster_id}_{cluster_b.cluster_id}"
        bridge_dict["cluster_a"] = cluster_a.cluster_label
        bridge_dict["cluster_b"] = cluster_b.cluster_label
        bridge_dict["cluster_a_papers"] = cluster_a.papers
        bridge_dict["cluster_b_papers"] = cluster_b.papers

        return bridge_dict

    def _build_mechanism_network(
        self,
        nodes: List[MechanismNode],
        clusters: List[PaperCluster],
        paper_summaries: List[Dict],
    ) -> MechanismNetwork:
        """构建全文献池的机制网络"""
        network = MechanismNetwork(nodes=nodes, clusters=clusters)

        # 找出共享变量（在不同集群中作为不同角色出现）
        var_roles: Dict[str, Dict[str, List[str]]] = {}
        for node in nodes:
            for var_name in [node.x_var, node.y_var, node.mediator_var]:
                if not var_name or len(var_name) < 2:
                    continue
                # 找到该节点的集群
                cluster_id = node.cluster_id or self._find_cluster_for_paper(
                    node.paper_title, clusters
                )
                if cluster_id not in var_roles.setdefault(var_name, {}):
                    var_roles[var_name][cluster_id] = []
                var_roles[var_name][cluster_id].append(
                    "Y" if var_name == node.y_var else ("X" if var_name == node.x_var else "中介")
                )

        shared = []
        for var_name, roles in var_roles.items():
            if len(roles) >= 2:  # 在两个以上集群中出现
                shared.append({
                    "variable": var_name,
                    "roles": {k: list(set(v)) for k, v in roles.items()},
                })
        network.shared_variables = shared

        # 找出共享机制
        mech_clusters: Dict[str, set] = {}
        for node in nodes:
            if not node.mechanism_name:
                continue
            cid = node.cluster_id or self._find_cluster_for_paper(node.paper_title, clusters)
            mech_clusters.setdefault(node.mechanism_name, set()).add(cid)

        network.shared_mechanisms = [
            {"mechanism": mech, "clusters": list(cids)}
            for mech, cids in mech_clusters.items()
            if len(cids) >= 2
        ]

        # 识别可嫁接因果链（初步筛选，不做深度分析）
        graftable = []
        for node_a in nodes:
            for node_b in nodes:
                if node_a.paper_title == node_b.paper_title:
                    continue
                # 条件：A的Y或中介 = B的X → 因果链可以串联
                if (node_a.y_var and node_a.y_var in (node_b.x_var, node_b.mediator_var)) or \
                   (node_a.mediator_var and node_a.mediator_var in (node_b.x_var, node_b.y_var)):
                    graftable.append({
                        "from_paper": node_a.paper_title,
                        "to_paper": node_b.paper_title,
                        "graft_point": node_a.y_var if node_a.y_var in (node_b.x_var, node_b.mediator_var) else node_a.mediator_var,
                        "chain_a": f"{node_a.x_var} → {node_a.mediator_var} → {node_a.y_var}",
                        "chain_b": f"{node_b.x_var} → {node_b.mediator_var} → {node_b.y_var}",
                    })
        network.graftable_chains = graftable[:20]

        return network

    def _build_bridge_detection_prompt(
        self,
        cluster_a: PaperCluster,
        cluster_b: PaperCluster,
        ca_summary: str,
        cb_summary: str,
        network: MechanismNetwork = None,
        cross_synthesis: Dict = None,
    ) -> str:
        """构建跨集群桥梁检测的 LLM Prompt"""
        # 加载模板
        template_path = os.path.join(self._prompts_dir, "bridge_detection.txt")
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()
        else:
            template = self._get_bridge_detection_template()

        # 可嫁接因果链
        graftable_text = ""
        for gc in (network.graftable_chains if network else [])[:10]:
            graftable_text += (
                f"  - {gc['chain_a']} (论文: {gc['from_paper'][:40]})"
                f" →→→ {gc['chain_b']} (论文: {gc['to_paper'][:40]})"
                f" [嫁接点: {gc['graft_point']}]\n"
            )

        # 共享变量
        shared_vars_text = ""
        for sv in (network.shared_variables if network else [])[:10]:
            roles_str = "; ".join(f"{k}: {v}" for k, v in sv.get("roles", {}).items())
            shared_vars_text += f"  - {sv['variable']}: {roles_str}\n"

        # 共享机制
        shared_mech_text = ""
        for sm in (network.shared_mechanisms if network else [])[:10]:
            shared_mech_text += f"  - {sm['mechanism']} (跨 {', '.join(sm['clusters'])})\n"

        return (template
            .replace("{cluster_a_label}", cluster_a.cluster_label)
            .replace("{cluster_b_label}", cluster_b.cluster_label)
            .replace("{cluster_a_summary}", ca_summary)
            .replace("{cluster_b_summary}", cb_summary)
            .replace("{graftable_chains}", graftable_text or "（未发现明显的可嫁接因果链）")
            .replace("{shared_variables}", shared_vars_text or "（无跨集群共享变量）")
            .replace("{shared_mechanisms}", shared_mech_text or "（无跨集群共享机制）"))

    # ═══════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════

    def _cluster_only(self, paper_summaries: List[Dict] = None) -> Dict:
        """仅做聚类，不做桥梁检测（用于预览）"""
        clusters = cluster_papers_by_topic(paper_summaries or [])
        return {
            "success": True,
            "clusters": [dataclass_to_dict(c) for c in clusters],
            "cluster_count": len(clusters),
        }

    def _build_cluster_summary(
        self,
        cluster: PaperCluster,
        paper_summaries: List[Dict],
        mechanism_nodes: List[MechanismNode],
    ) -> str:
        """为一个集群构建人类可读的摘要文本（供 LLM 分析）"""
        parts = [f"【主题集群: {cluster.cluster_label}】"]
        parts.append(f"论文数: {cluster.paper_count} 篇")
        parts.append(f"核心 X: {', '.join(cluster.common_x_vars) if cluster.common_x_vars else '未提取'}")
        parts.append(f"核心 Y: {', '.join(cluster.common_y_vars) if cluster.common_y_vars else '未提取'}")
        parts.append(f"常用方法: {', '.join(cluster.common_methods) if cluster.common_methods else '未提取'}")
        parts.append(f"使用理论: {', '.join(cluster.common_theories[:5]) if cluster.common_theories else '未提取'}")

        # 集群内的机制池
        cluster_nodes = [n for n in mechanism_nodes if n.paper_title in cluster.papers]
        if cluster_nodes:
            parts.append(f"\n机制池 ({len(cluster_nodes)} 条):")
            for n in cluster_nodes[:10]:
                parts.append(
                    f"  - {n.x_var} → [{n.mechanism_name}] → {n.y_var}"
                    f" (中介: {n.mediator_var if n.mediator_var else '无'})"
                    f" [来源: {n.paper_title[:40]}]"
                )

        # 集群内代表性发现
        for ps in paper_summaries:
            if ps.get("paper_title") in cluster.papers:
                sections = ps.get("sections", {})
                baseline = sections.get("06_baseline_results", {})
                sign = baseline.get("core_coefficient_sign", "")
                if sign:
                    parts.append(f"\n代表性发现: {ps['paper_title'][:40]} → 核心系数方向: {sign}")

        return "\n".join(parts)

    def _rank_topics(self, bridges: List[Dict]) -> List[Dict]:
        """从所有桥梁中提取、去重、排序候选题目"""
        all_topics = []
        seen = set()

        for bridge in bridges:
            for topic in bridge.get("candidate_topics", []):
                if isinstance(topic, dict):
                    title = topic.get("title", "")
                    if title and title[:40] not in seen:
                        seen.add(title[:40])
                        topic["bridge_theory"] = bridge.get("bridge_theory_name", "")
                        topic["source_clusters"] = [bridge.get("cluster_a", ""), bridge.get("cluster_b", "")]
                        topic["innovation_score"] = topic.get("innovation_score", bridge.get("innovation_score", 5))
                        topic["theoretical_rigor"] = topic.get("theoretical_rigor", bridge.get("theoretical_rigor_score", 5))
                        topic["feasibility"] = topic.get("feasibility", bridge.get("feasibility_score", 5))
                        # 综合评分
                        topic["overall_score"] = round(
                            float(topic["innovation_score"]) * 0.40 +
                            float(topic["theoretical_rigor"]) * 0.35 +
                            float(topic["feasibility"]) * 0.25, 1
                        )
                        all_topics.append(topic)

        # 按综合评分降序排列
        all_topics.sort(key=lambda t: t.get("overall_score", 0), reverse=True)
        return all_topics

    def _extract_method_recommendations(self, bridges: List[Dict]) -> List[str]:
        """从所有桥梁中提取方法论建议"""
        recs = []
        for b in bridges:
            for mi in b.get("methodological_insights", []):
                if isinstance(mi, dict):
                    recs.append(mi.get("insight", mi.get("description", "")))
                elif isinstance(mi, str):
                    recs.append(mi)
        return list(set(recs))[:10]

    @staticmethod
    def _find_cluster_for_paper(paper_title: str, clusters: List[PaperCluster]) -> str:
        """按论文标题查找所属集群"""
        for c in clusters:
            if paper_title in c.papers:
                return c.cluster_id
        return "unknown"

    @staticmethod
    def _filter_meaningful_pairs(clusters: List[PaperCluster]) -> List[Tuple[PaperCluster, PaperCluster]]:
        """
        只保留"真正不同"的集群对，跳过同一主题内部的细分集群对。

        判定规则：
        1. 两个集群的核心 X 变量必须有差异（共享任一 X → 同主题 → 跳过）
        2. 两个集群的 cluster_label 必须是不同粗主题
        3. 每对集群至少各有 1 篇论文
        """
        if len(clusters) <= 1:
            return []

        # 为每个集群标记粗主题（cluster_label 的前20字符或 TOPIC_PATTERNS 匹配）
        def _coarse_topic(c: PaperCluster) -> str:
            coarse_patterns = ["智慧城市", "金融化", "数据跨境", "耐心资本", "政策试点"]
            label = c.cluster_label
            for pat in coarse_patterns:
                if pat in label:
                    return pat
            # 回退：检查 X 变量
            if c.common_x_vars:
                return c.common_x_vars[0][:20]
            return label[:20]

        # 只为不同粗主题的集群对生成桥梁
        pairs = []
        seen_pairs = set()
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                ca, cb = clusters[i], clusters[j]
                topic_a = _coarse_topic(ca)
                topic_b = _coarse_topic(cb)

                # 跳过同一粗主题
                if topic_a == topic_b:
                    continue

                # 检查是否已经处理过这个主题对
                pair_key = tuple(sorted([topic_a, topic_b]))
                if pair_key in seen_pairs:
                    continue

                # 只保留差距足够大的集群（至少论文数≥1 且摘要长度足够）
                if ca.paper_count >= 1 and cb.paper_count >= 1:
                    pairs.append((ca, cb))
                    seen_pairs.add(pair_key)

        # 限制最多 5 对（避免 token 爆炸）
        return pairs[:5]

    def _build_single_cluster_fallback(
        self,
        cluster: PaperCluster,
        paper_summaries: List[Dict],
        mechanism_nodes: List[MechanismNode],
    ) -> Dict:
        """
        当只有一个集群时的回退方案：做集群内创新检测。
        LLM 分析该集群内部的变量组合、机制深化、方法改进空间。
        """
        ca_summary = self._build_cluster_summary(cluster, paper_summaries, mechanism_nodes)

        prompt = f"""你是一位经济学研究者。以下是一个文献集群的完整分析摘要。
虽然这些论文共享相似的主题，请从以下角度挖掘集群内部的创新空间：

{ca_summary}

【分析要求】
1. 变量组合创新：该集群的 X 和 Y 是否可以用新的方式组合？
2. 机制深化：是否存在未被充分检验的机制渠道？是否存在竞争性机制？
3. 方法改进：现有方法（主要是DID）有哪些可改进的空间？
4. 情境迁移：该集群的发现是否可以迁移到新的制度情境或群体？

请输出与该集群相关的 3-5 个创新题目候选。"""

        try:
            result = self.llm.structured_output(
                prompt=prompt,
                output_schema={
                    "type": "object",
                    "properties": {
                        "bridge_theory_name": {"type": "string"},
                        "theoretical_bridge_summary": {"type": "string"},
                        "candidate_topics": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "research_question": {"type": "string"},
                                    "innovation_type": {"type": "string"},
                                    "innovation_score": {"type": "number"},
                                    "theoretical_rigor": {"type": "number"},
                                    "feasibility": {"type": "number"},
                                    "key_variables": {"type": "array", "items": {"type": "string"}},
                                    "identification_strategy": {"type": "string"},
                                    "theoretical_basis": {"type": "string"},
                                },
                            },
                        },
                        "overall_score": {"type": "number"},
                    },
                },
                system_prompt="你是一位经济学研究者。请基于文献集群的深度分析，提出集群内部的创新题目。",
                backend=None,
                model=None,
                max_tokens=4000,
                max_retries=1,
            )
            return result
        except Exception:
            return {"overall_score": 0, "candidate_topics": []}

    @staticmethod
    def _get_bridge_detection_template() -> str:
        """回退：内联的桥梁检测 Prompt 模板"""
        return """你是一位经济学理论研究者。你的任务是在以下两组看似无关的文献集群之间发现深层理论连接。

【集群A: {cluster_a_label}】
{cluster_a_summary}

【集群B: {cluster_b_label}】
{cluster_b_summary}

【预处理结果——可嫁接因果链候选】
{graftable_chains}

【预处理结果——跨集群共享变量】
{shared_variables}

【预处理结果——跨集群共享机制】
{shared_mechanisms}

【5维分析框架——请严格按此框架分析】

### 1. 理论统合分析
- 集群A使用了哪些中层理论？集群B使用了哪些？
- 是否存在一个**更高层级的统合理论**，可以同时解释A和B中的核心发现？
- 理论推导链：更高层理论 → 同时解释A的现象 + B的现象 → 可检验的新假说
- 标注此理论在文献中的先例（如有）

### 2. 机制迁移分析
- 对于每条"可嫁接因果链"候选，严格评估：
  a) 来源集群的机制逻辑是否依赖于该集群特有情境？
  b) 如果移植到目标集群，因果方向是否仍然成立？
  c) 需要哪些辅助假设才能使移植成立？
- 对每个有效的移植，给出：来源机制 → 移植逻辑 → 目标集群新假说

### 3. 方法互鉴分析
- 集群A的识别策略能否解决集群B中的内生性挑战？
- 集群B的变量测度方式是否可用于丰富集群A的研究设计？
- 两个集群中哪个的方法论更严谨？是否存在可借鉴的诊断检验？

### 4. 变量串联分析
- 对每个"共享变量"：分析它在集群A和集群B中的不同角色
- 这种角色转换是否暗示了新的因果链？如：A的Y → B的X？
- 是否有变量在一个集群中是被控制的噪音，在另一集群中有独立的理论意义？

### 5. 矛盾与张力分析（创新性最强的维度）
- 两个集群的核心结论是否有矛盾或张力？
- 集群A发现"政策X提升经济表现"，集群B发现"经济不确定性→企业脱实向虚"
  → 如果政策X降低不确定性，它能否在金融化程度高的子样本中同样有效？
- 矛盾是否指向一个缺失的**调节变量**或**边界条件**？

【输出要求】
生成一个完整的 ClusterBridge JSON。如果确实不存在有理论支撑的桥梁，candidate_topics 可以为空数组。
所有 candidate_topics 必须来自以上的理论分析，不能凭空编造。"""
