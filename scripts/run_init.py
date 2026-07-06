"""
初始化新论文工作区：将当前产出归档到论文专属文件夹，重置 workspace 准备下一篇。
适配 per-paper 分析目录结构（workspace/analysis/<论文标题>/）。
"""
import os
import sys
import json
import shutil
import re

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def sanitize(name: str, max_len: int = 40) -> str:
    """将论文标题转为安全的文件夹名"""
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    if len(name) > max_len:
        name = name[:max_len]
    return name or "未命名论文"


def main():
    workspace = os.path.abspath("workspace")
    papers_file = os.path.join(workspace, "papers", "metadata.json")
    projects_dir = os.path.join(workspace, "projects")
    state_file = os.path.join(workspace, "state.json")

    # 1. 读取当前论文标题
    paper_title = None
    papers = []
    if os.path.exists(papers_file) and os.path.getsize(papers_file) > 2:
        try:
            with open(papers_file, "r", encoding="utf-8") as f:
                papers = json.load(f)
            if papers and isinstance(papers, list) and len(papers) > 0:
                paper_title = papers[0].get("title", "").strip()
        except Exception:
            pass

    if not paper_title:
        print("[初始化] 未在 workspace/papers/metadata.json 中找到论文标题。")
        print("[初始化] 将清空工作区但不会创建归档（无成果可归档）。")
        # 非交互模式：自动确认
        import sys as _sys
        if not _sys.stdin.isatty():
            print("[初始化] 非交互模式，自动确认清空。")
        else:
            try:
                action = input("确认清空工作区？(y/N): ").strip().lower()
                if action != "y":
                    print("[初始化] 已取消。")
                    return
            except EOFError:
                print("[初始化] 非交互模式，自动确认清空。")
        paper_title = None
    else:
        print(f"[初始化] 当前论文: {paper_title}")

    # 2. 创建归档目录
    if paper_title:
        folder_name = sanitize(paper_title)
        archive_dir = os.path.join(projects_dir, folder_name)
        os.makedirs(archive_dir, exist_ok=True)
        print(f"[初始化] 归档目标: {archive_dir}")

        # 3. 移动产出物（适配 per-paper 目录结构）
        # workspace/analysis/ 包含 <论文标题>/ 子目录 + _cross_paper/ + _analysis_index.json
        # workspace/empirical/ 已废弃（新结构在 analysis/<论文>/empirical.*），但仍处理旧文件
        moves = [
            ("analysis", "analysis"),
            ("empirical", "empirical"),
            ("writing", "writing"),
            ("regression", "regression"),
            ("data", "data"),
            ("literature_review.md", "literature_review.md"),
            ("review_analysis_report.json", "review_analysis_report.json"),
            ("presentation.html", "presentation.html"),
            ("presentation.pptx", "presentation.pptx"),
            ("speech_script.md", "speech_script.md"),
            ("papers", "papers"),
            ("state.json", "state.json"),
        ]

        for src, dst in moves:
            src_path = os.path.join(workspace, src)
            dst_path = os.path.join(archive_dir, dst)
            if os.path.exists(src_path):
                if os.path.isdir(src_path):
                    if os.path.exists(dst_path):
                        shutil.rmtree(dst_path)
                    shutil.move(src_path, dst_path)
                else:
                    if os.path.exists(dst_path):
                        os.remove(dst_path)
                    shutil.move(src_path, dst_path)
                print(f"  [OK] {src} -> projects/{folder_name}/{dst}")
            else:
                print(f"  - {src} (不存在，跳过)")

        # 4. 写入归档信息
        info = {
            "paper_title": paper_title,
            "papers": papers,
            "analysis_structure": "per_paper",  # 标记为新结构
        }
        with open(os.path.join(archive_dir, "project_info.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)

        print(f"\n[初始化] 归档完成 -> workspace/projects/{folder_name}/")

    # 5. 重置工作区
    os.makedirs(os.path.join(workspace, "papers"), exist_ok=True)
    os.makedirs(os.path.join(workspace, "analysis"), exist_ok=True)

    # 空 metadata.json
    with open(papers_file, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)

    # 空 state.json
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump({}, f, ensure_ascii=False, indent=2)

    # 清理 analysis 目录（可能包含 per-paper 子目录）
    analysis_dir = os.path.join(workspace, "analysis")
    if os.path.exists(analysis_dir):
        for item in os.listdir(analysis_dir):
            item_path = os.path.join(analysis_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            elif os.path.isfile(item_path):
                os.remove(item_path)

    # 清理其他可能残留的产出目录
    for dirname in ["empirical", "writing", "regression", "data"]:
        dirpath = os.path.join(workspace, dirname)
        if os.path.exists(dirpath):
            shutil.rmtree(dirpath)

    # 清理 workspace 根目录下的产出文件
    for fname in ["literature_review.md", "review_analysis_report.json",
                   "presentation.html", "presentation.pptx", "speech_script.md"]:
        fpath = os.path.join(workspace, fname)
        if os.path.exists(fpath):
            os.remove(fpath)

    # 清理临时/缓存文件
    for root, dirs, files in os.walk(workspace):
        for f in files:
            if f.endswith(".pyc") or f.startswith("_"):
                fp = os.path.join(root, f)
                if os.path.isfile(fp):
                    os.remove(fp)

    print("[初始化] 工作区已重置，可以开始下一篇论文。")
    print("[初始化] 请将新论文的元数据放入 workspace/papers/metadata.json 后运行 /文献综述。")


if __name__ == "__main__":
    main()
