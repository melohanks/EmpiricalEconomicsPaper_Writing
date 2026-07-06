"""
从 Zotero 本地 SQLite 数据库提取论文元数据

用法:
  # 列出所有期刊论文
  python scripts/zotero_extract.py --list

  # 按关键词筛选并导出到 metadata.json
  python scripts/zotero_extract.py --search "耐心资本" --output workspace/papers/metadata.json

  # 导出指定论文（按 Zotero key）
  python scripts/zotero_extract.py --key KMJDXCRI --output workspace/papers/metadata.json

  # 导出全部期刊论文
  python scripts/zotero_extract.py --all --output workspace/papers/metadata.json
"""
import os
import sys
import json
import shutil
import sqlite3
import argparse

ZOTERO_DB = os.path.expandvars(r"%USERPROFILE%\Zotero\zotero.sqlite")
ZOTERO_STORAGE = os.path.expandvars(r"%USERPROFILE%\Zotero\storage")

# PDF 全文提取上限（字符数），防止 token 爆炸
PDF_FULLTEXT_MAX_CHARS = 15000

# Zotero 字段ID映射
FIELD_IDS = {
    "title": 1,
    "abstractNote": 2,
    "date": 6,
    "DOI": 8,
    "url": 10,
    "publicationTitle": 41,
    "extra": 44,
    "accessDate": 52,
    "language": 53,
    "ISSN": 27,
}

ITEM_TYPES = {
    "journalArticle": "期刊论文",
    "newspaperArticle": "报纸",
    "webpage": "网页",
    "conferencePaper": "会议论文",
    "thesis": "学位论文",
    "book": "图书",
}


def get_field_value(cur, item_id, field_id):
    """获取某个 item 的字段值"""
    cur.execute(
        """SELECT idv.value FROM itemData id
           JOIN itemDataValues idv ON id.valueID = idv.valueID
           WHERE id.itemID = ? AND id.fieldID = ?""",
        (item_id, field_id),
    )
    row = cur.fetchone()
    return row[0] if row else None


def get_authors(cur, item_id):
    """获取作者列表"""
    cur.execute(
        """SELECT c.firstName, c.lastName, ct.creatorType
           FROM creators c
           JOIN itemCreators ic ON c.creatorID = ic.creatorID
           JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
           WHERE ic.itemID = ?
           ORDER BY ic.orderIndex""",
        (item_id,),
    )
    authors = []
    for first, last, ctype in cur.fetchall():
        name = f"{last} {first}" if first else (last or "")
        if ctype == "author":
            authors.append(name)
    return authors


def get_keywords(cur, item_id):
    """获取标签（关键词）"""
    cur.execute(
        """SELECT t.name FROM tags t
           JOIN itemTags it ON t.tagID = it.tagID
           WHERE it.itemID = ?""",
        (item_id,),
    )
    return [r[0] for r in cur.fetchall()]


def get_attachment_paths(cur, item_id):
    """获取PDF附件路径和 attachment key"""
    cur.execute(
        """SELECT ia.itemID, ia.path, ia.contentType
           FROM itemAttachments ia
           WHERE ia.parentItemID = ?""",
        (item_id,),
    )
    results = []
    for att_id, path, ctype in cur.fetchall():
        # 获取 attachment 自身的 zotero key（用于构建存储路径）
        cur.execute("SELECT key FROM items WHERE itemID = ?", (att_id,))
        row = cur.fetchone()
        att_key = row[0] if row else None
        results.append((att_id, att_key, path, ctype))
    return results


def extract_pdf_fulltext(att_key: str, filename: str, max_chars: int = PDF_FULLTEXT_MAX_CHARS) -> str:
    """
    从 Zotero storage 中的 PDF 提取全文。

    :param att_key: 附件的 Zotero key（用于定位 storage 子目录）
    :param filename: 文件名（从 ia.path 中提取，如 'storage:xxx.pdf' → 'xxx.pdf'）
    :param max_chars: 最大返回字符数
    :return: 提取的文本，失败返回空字符串
    """
    fname = os.path.basename(filename.replace("storage:", "").replace(":", ""))
    pdf_path = os.path.join(ZOTERO_STORAGE, att_key, fname)

    if not os.path.exists(pdf_path):
        return ""

    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        text_parts = []
        total = 0
        for page in doc:
            page_text = page.get_text()
            if total + len(page_text) > max_chars:
                text_parts.append(page_text[:max_chars - total])
                break
            text_parts.append(page_text)
            total += len(page_text)
        doc.close()
        return "\n\n".join(text_parts).strip()
    except Exception:
        return ""


def extract_paper(cur, item_id, key, item_type):
    """提取单篇论文的完整元数据"""
    title = get_field_value(cur, item_id, FIELD_IDS["title"]) or ""
    abstract = get_field_value(cur, item_id, FIELD_IDS["abstractNote"]) or ""
    doi = get_field_value(cur, item_id, FIELD_IDS["DOI"]) or ""
    pub_title = get_field_value(cur, item_id, FIELD_IDS["publicationTitle"]) or ""
    date = get_field_value(cur, item_id, FIELD_IDS["date"]) or ""
    url = get_field_value(cur, item_id, FIELD_IDS["url"]) or ""
    authors = get_authors(cur, item_id)
    keywords = get_keywords(cur, item_id)
    attachments = get_attachment_paths(cur, item_id)

    # 清理日期
    pub_date = date.split("-")[0] if date and "-" in date else (date[:4] if date and len(date) >= 4 else "")

    # Extra 字段：Zotero 用户自定义笔记/补充信息
    extra = get_field_value(cur, item_id, FIELD_IDS["extra"]) or ""

    paper = {
        "zotero_key": key,
        "title": title,
        "authors": ", ".join(authors) if authors else "",
        "source": pub_title,
        "pub_date": pub_date,
        "abstract": abstract if abstract else "",  # 不再截断，保留完整摘要
        "extra": extra[:5000] if extra else "",    # Zotero Extra 字段（截断到 5000 以防异常数据）
        "keywords": keywords,
        "link": doi_to_url(doi) if doi else url,
        "doi": doi,
        "item_type": ITEM_TYPES.get(item_type, item_type),
    }

    # PDF 附件
    if attachments:
        paper["attachments"] = [
            {"path": p[2], "type": p[3]} for p in attachments if p[2]
        ]
        # 提取第一个 PDF 的全文
        for att_id, att_key, path, ctype in attachments:
            if ctype == "application/pdf" and att_key:
                print(f"    提取 PDF 全文: {os.path.basename(path)[:50]}...")
                fulltext = extract_pdf_fulltext(att_key, path)
                if fulltext:
                    paper["fulltext"] = fulltext
                    print(f"    全文提取成功: {len(fulltext)} chars")
                else:
                    print(f"    全文提取失败（PDF 不存在或无法解析）")
                break  # 只提取第一个 PDF

    return paper


def doi_to_url(doi: str) -> str:
    if not doi:
        return ""
    doi = doi.strip()
    if doi.startswith("http"):
        return doi
    return f"https://doi.org/{doi}"


def get_working_copy(db_path):
    """获取数据库的工作副本（绕过锁）"""
    tmp = db_path + ".copy"
    shutil.copy2(db_path, tmp)
    return tmp


def main():
    parser = argparse.ArgumentParser(description="从 Zotero 本地库提取论文元数据")
    parser.add_argument("--list", action="store_true", help="列出所有期刊论文")
    parser.add_argument("--search", type=str, help="按标题/关键词搜索")
    parser.add_argument("--key", type=str, help="按 Zotero key 导出单篇")
    parser.add_argument("--all", action="store_true", help="导出全部期刊论文")
    parser.add_argument("--output", type=str, default="workspace/papers/metadata.json",
                        help="输出 JSON 路径")
    parser.add_argument("--limit", type=int, default=50, help="最大导出数量")
    args = parser.parse_args()

    if not os.path.exists(ZOTERO_DB):
        print(f"[错误] Zotero 数据库未找到: {ZOTERO_DB}")
        sys.exit(1)

    # 复制数据库避免锁定
    tmp_db = get_working_copy(ZOTERO_DB)
    conn = sqlite3.connect(tmp_db)
    cur = conn.cursor()

    # 查询论文
    where_clause = "it.typeName = 'journalArticle'"
    params = []

    if args.key:
        where_clause = "i.key = ?"
        params = [args.key]
    elif args.search:
        # 关键词搜索（标题 + 标签）
        search_terms = args.search.split()
        title_conditions = " OR ".join(
            [
                """EXISTS (SELECT 1 FROM itemData id2
                   JOIN itemDataValues idv2 ON id2.valueID = idv2.valueID
                   WHERE id2.itemID = i.itemID AND id2.fieldID = 1
                   AND idv2.value LIKE ?)"""
            ]
            * len(search_terms)
        )
        where_clause = (
            f"it.typeName = 'journalArticle' AND ({title_conditions})"
        )
        params = [f"%{t}%" for t in search_terms]

    query = f"""
        SELECT i.itemID, i.key, it.typeName
        FROM items i
        JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
        WHERE {where_clause}
        ORDER BY i.dateAdded DESC
        LIMIT ?
    """
    params.append(args.limit)
    cur.execute(query, params)
    rows = cur.fetchall()

    if args.list:
        print(f"\nZotero 期刊论文列表 ({len(rows)} 篇):\n")
        for i, (item_id, key, itype) in enumerate(rows):
            title = get_field_value(cur, item_id, FIELD_IDS["title"]) or "?"
            date = get_field_value(cur, item_id, FIELD_IDS["date"]) or ""
            doi = get_field_value(cur, item_id, FIELD_IDS["DOI"]) or ""
            source = get_field_value(cur, item_id, FIELD_IDS["publicationTitle"]) or ""
            authors = get_authors(cur, item_id)
            kw = get_keywords(cur, item_id)
            print(f"  {i+1:2d}. [{key[:8]}] {date[:10]:10s} {title[:60]}")
            print(f"      {', '.join(authors[:3])} · {source}")
            print(f"      DOI: {doi or 'N/A'}  | 关键词: {', '.join(kw[:5])}")
            print()
        conn.close()
        os.remove(tmp_db)
        return

    # 提取完整元数据
    papers = []
    for item_id, key, itype in rows:
        try:
            paper = extract_paper(cur, item_id, key, itype)
            papers.append(paper)
        except Exception as e:
            print(f"  [警告] 提取 {key[:8]} 失败: {e}")

    conn.close()
    os.remove(tmp_db)

    # 输出
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        # 如果文件已存在，合并而非覆盖
        existing = []
        if os.path.exists(args.output):
            try:
                with open(args.output, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass
        # 按 key 去重
        existing_keys = {p.get("zotero_key", ""): i for i, p in enumerate(existing)}
        for paper in papers:
            k = paper.get("zotero_key", "")
            if k and k in existing_keys:
                existing[existing_keys[k]] = paper  # 更新
            else:
                existing.append(paper)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"\n[完成] 提取 {len(papers)} 篇论文 → {args.output}")

    # 打印摘要
    for i, p in enumerate(papers[:5]):
        print(f"  {i+1}. {p['title'][:60]}")
        print(f"     作者: {p['authors'][:50]}")
        print(f"     来源: {p['source']} ({p['pub_date']})")
        print(f"     关键词: {', '.join(p.get('keywords', [])[:5])}")
        print()


if __name__ == "__main__":
    main()
