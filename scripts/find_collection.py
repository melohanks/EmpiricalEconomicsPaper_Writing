"""查找 Zotero 中特定文件夹并导出其论文"""
import sqlite3, os, shutil, json, sys

FIELD_NAMES_TO_IDS = {
    "title": 1, "abstractNote": 2, "date": 6, "DOI": 8,
    "url": 10, "publicationTitle": 41, "extra": 44,
    "accessDate": 52, "language": 53, "ISSN": 27,
}

def get_field_value(cur, item_id, field_id):
    cur.execute(
        """SELECT idv.value FROM itemData id
           JOIN itemDataValues idv ON id.valueID = idv.valueID
           WHERE id.itemID = ? AND id.fieldID = ?""",
        (item_id, field_id),
    )
    row = cur.fetchone()
    return row[0] if row else None

def get_authors(cur, item_id):
    cur.execute(
        """SELECT c.firstName, c.lastName
           FROM creators c
           JOIN itemCreators ic ON c.creatorID = ic.creatorID
           JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
           WHERE ic.itemID = ? AND ct.creatorType = 'author'
           ORDER BY ic.orderIndex""",
        (item_id,),
    )
    return [f"{last} {first}" if first else (last or "") for first, last in cur.fetchall()]

def get_keywords(cur, item_id):
    """获取标签作为关键词"""
    cur.execute(
        """SELECT t.name FROM tags t
           JOIN itemTags it ON t.tagID = it.tagID
           WHERE it.itemID = ?""",
        (item_id,),
    )
    return [r[0] for r in cur.fetchall() if r[0]]

# 复制数据库避免锁定
src = os.path.expandvars(r'%USERPROFILE%\Zotero\zotero.sqlite')
if not os.path.exists(src):
    src = r'C:\Users\User\Zotero\zotero.sqlite'
if not os.path.exists(src):
    print("找不到 Zotero 数据库")
    sys.exit(1)

dst = os.path.expandvars(r'%TEMP%\zotero_query.sqlite')
shutil.copy2(src, dst)
conn = sqlite3.connect(dst)
cur = conn.cursor()

search_terms = sys.argv[1:] if len(sys.argv) > 1 else ["智能城市", "智慧城市试点"]
print(f"搜索关键词: {search_terms}")

found = []
for term in search_terms:
    cur.execute("""
        SELECT c.collectionName, c.collectionID, p.collectionName
        FROM collections c
        LEFT JOIN collections p ON c.parentCollectionID = p.collectionID
        WHERE c.collectionName LIKE ?
    """, (f'%{term}%',))
    for name, cid, parent in cur.fetchall():
        if (name, cid) not in found:
            found.append((name, cid, parent))

if not found:
    print("未找到匹配文件夹。")
else:
    all_items = set()
    for name, cid, parent in found:
        print(f'\n📁 "{name}" (key={cid}, parent={parent or "根"})')
        cur.execute("""
            SELECT DISTINCT i.itemID, i.key, it.typeName
            FROM collectionItems ci
            JOIN items i ON ci.itemID = i.itemID
            LEFT JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
            WHERE ci.collectionID = ?
            ORDER BY i.dateAdded DESC
        """, (cid,))
        items = cur.fetchall()
        print(f'   论文数: {len(items)}')
        for item_id, zkey, itype in items:
            title = get_field_value(cur, item_id, 1)
            date = get_field_value(cur, item_id, 6)
            journal = get_field_value(cur, item_id, 41)
            doi = get_field_value(cur, item_id, 8)
            authors = get_authors(cur, item_id)
            keywords = get_keywords(cur, item_id)
            if title:
                all_items.add(zkey)
                short = title[:65] + ('...' if len(title) > 65 else '')
                print(f'     [{zkey[:8]}] {short}')
                if authors:
                    print(f'          {" ".join(authors[:3])}')
                if journal or date:
                    print(f'          {journal or ""}  ({date or ""})')
                if keywords:
                    print(f'          关键词: {", ".join(keywords[:4])}')

    print(f'\n--- 总计: {len(all_items)} 篇独特论文 ---')

conn.close()
os.remove(dst)
