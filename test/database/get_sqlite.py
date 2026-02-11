import sqlite3

def fetch_all_tables(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]
    return tables

def fetch_table_schema(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f'PRAGMA table_info("{table_name}");')
    # PRAGMA table_info 返回字段：cid, name, type, notnull, dflt_value, pk
    schema = [{"cid": row[0], "name": row[1], "type": row[2], "notnull": bool(row[3]), "dflt_value": row[4], "pk": bool(row[5])} for row in cursor.fetchall()]
    return schema

def fetch_table_preview(conn, table_name, limit=5):
    cursor = conn.cursor()
    try:
        cursor.execute(f'SELECT * FROM "{table_name}" LIMIT {limit};')
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        return col_names, rows
    except sqlite3.Error as e:
        return None, f"查询错误: {e}"

def main(db_path='app.db', preview_limit=5):
    conn = sqlite3.connect(db_path)
    try:
        tables = fetch_all_tables(conn)
        if not tables:
            print("数据库中没有找到表。")
            return

        for tname in tables:
            print(f"\n=== 表: {tname} ===")

            # 表头（列名）
            schema = fetch_table_schema(conn, tname)
            if schema:
                header = [col['name'] for col in schema]
                print("列名:", ", ".join(header))
                # 简单的类型信息也可以输出
                types = [col['type'] for col in schema]
                print("类型 :", ", ".join(types))
            else:
                print("无法获取表结构。")

            # 前 n 行数据
            col_names, preview = fetch_table_preview(conn, tname, limit=preview_limit)
            if isinstance(preview, str):
                # 出错信息
                print(preview)
            else:
                print("前 {} 行数据：".format(preview_limit))
                if preview:
                    # 构造一个简单的表格输出
                    # 打印表头
                    print(" | ".join(col_names))
                    print("-" * (len(" | ".join(col_names))))
                    for row in preview:
                        print(" | ".join(str(v) for v in row))
                else:
                    print("（空表）")
    finally:
        conn.close()

if __name__ == "__main__":
    # 根据需要修改路径和预览行数
    database_path = "/home/gitclone/BeingDoing/src/backend/app.db"
    main(db_path=database_path, preview_limit=5)