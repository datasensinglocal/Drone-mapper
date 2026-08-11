import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(
    host=os.environ["DB_HOST"], port=os.environ.get("DB_PORT", "5432"),
    dbname=os.environ["DB_NAME"], user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
)
cur = conn.cursor()

print("-- composite constraints, grouped by constraint name --")
cur.execute("""
    SELECT tc.table_name, tc.constraint_name, tc.constraint_type,
           array_agg(kcu.column_name ORDER BY kcu.ordinal_position) AS columns
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    WHERE tc.table_name IN ('audit_infrastructure', 'road_profile', 'footpath_profile')
      AND tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
    GROUP BY tc.table_name, tc.constraint_name, tc.constraint_type
    ORDER BY tc.table_name;
""")
for row in cur.fetchall():
    print(" ", row)

print("\n-- column defaults for NOT NULL columns on road_profile/footpath_profile/audit_infrastructure --")
cur.execute("""
    SELECT table_name, column_name, column_default, is_nullable, udt_name
    FROM information_schema.columns
    WHERE table_schema='public' AND table_name IN ('road_profile','footpath_profile','audit_infrastructure')
      AND is_nullable = 'NO'
    ORDER BY table_name, ordinal_position;
""")
for row in cur.fetchall():
    print(" ", row)

print("\n-- udt (enum/array element) names for USER-DEFINED / ARRAY columns --")
cur.execute("""
    SELECT table_name, column_name, data_type, udt_name
    FROM information_schema.columns
    WHERE table_schema='public' AND table_name IN ('road_profile','footpath_profile','audit_infrastructure')
      AND (data_type = 'USER-DEFINED' OR data_type = 'ARRAY')
    ORDER BY table_name, column_name;
""")
udt_rows = cur.fetchall()
for row in udt_rows:
    print(" ", row)

print("\n-- enum values for those udt types --")
udt_names = set(r[3].lstrip('_') for r in udt_rows)
for udt in udt_names:
    cur.execute("""
        SELECT e.enumlabel FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = %s ORDER BY e.enumsortorder;
    """, (udt,))
    vals = [r[0] for r in cur.fetchall()]
    print(f"  {udt}: {vals}")

print("\n-- geometry column type/srid (via geometry_columns view) --")
cur.execute("""
    SELECT f_table_name, f_geometry_column, coord_dimension, srid, type
    FROM geometry_columns
    WHERE f_table_name IN ('road_profile','footpath_profile','audit_infrastructure');
""")
for row in cur.fetchall():
    print(" ", row)

print("\n-- sample rows (id, audit_infra_id/code only, no PII) --")
cur.execute("SELECT id, code, project_id, type FROM audit_infrastructure LIMIT 5;")
for row in cur.fetchall():
    print("  audit_infrastructure:", row)
cur.execute("SELECT id FROM projects LIMIT 5;")
for row in cur.fetchall():
    print("  projects.id:", row)

cur.close()
conn.close()
