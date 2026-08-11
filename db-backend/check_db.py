import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.environ["DB_HOST"],
    port=os.environ.get("DB_PORT", "5432"),
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
)
cur = conn.cursor()
cur.execute("SELECT version();")
print("CONNECTED OK:", cur.fetchone()[0])

print("\n-- tables in this database --")
cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' ORDER BY table_name;
""")
for row in cur.fetchall():
    print(" ", row[0])

TARGET_TABLES = ('road_profile', 'footpath_profile', 'audit_infrastructure', 'footpath_audit', 'junction_audit', 'streets', 'junctions')

print("\n-- columns of each relevant table --")
cur.execute("""
    SELECT table_name, column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = ANY(%s)
    ORDER BY table_name, ordinal_position;
""", (list(TARGET_TABLES),))
for row in cur.fetchall():
    print(" ", row)

print("\n-- unique/primary key constraints on those tables (if they exist) --")
cur.execute("""
    SELECT tc.table_name, tc.constraint_type, kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
    WHERE tc.table_name = ANY(%s)
      AND tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
    ORDER BY tc.table_name, tc.constraint_type;
""", (list(TARGET_TABLES),))
rows = cur.fetchall()
if rows:
    for row in rows:
        print(" ", row)
else:
    print("  (none found)")

cur.close()
conn.close()
