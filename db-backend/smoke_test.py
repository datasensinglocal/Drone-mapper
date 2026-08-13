import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# libpq keyword/value DSN -- avoids URL-encoding headaches with special characters in the password
os.environ["DATABASE_URL"] = (
    f"host={os.environ['DB_HOST']} port={os.environ.get('DB_PORT','5432')} "
    f"dbname={os.environ['DB_NAME']} user={os.environ['DB_USER']} password={os.environ['DB_PASSWORD']}"
)
os.environ.setdefault("API_TOKEN", os.environ.get("API_TOKEN", "test-token"))

import server  # noqa: E402  (must set env vars first)

client = server.app.test_client()
AUTH = {"Authorization": f"Bearer {os.environ['API_TOKEN']}"}
TEST_AUDIT_INFRA_ID = 1442  # known real id from audit_infrastructure sample (code S-190)
TEST_POINT_CODE = 999901    # unlikely to collide with real survey data

print("-- POST /api/road --")
resp = client.post("/api/road", json={
    "road_id": TEST_AUDIT_INFRA_ID, "point_code": TEST_POINT_CODE, "median": False,
    "road_width": 7.5, "geometry_coords": [[77.65, 12.96], [77.6501, 12.9601]],
    "data_collection_timestamp": "2026-08-10T00:00:00Z",
}, headers=AUTH)
print(resp.status_code, resp.get_json())

print("\n-- POST /api/footpath (side A) --")
resp = client.post("/api/footpath", json={
    "road_id": TEST_AUDIT_INFRA_ID, "point_code": TEST_POINT_CODE, "side": "A",
    "footpath_width_m": 1.8, "geometry_coords": [[77.65, 12.96], [77.6501, 12.9601]],
    "data_collection_timestamp": "2026-08-10T00:00:00Z",
}, headers=AUTH)
print(resp.status_code, resp.get_json())

print("\n-- re-POST /api/road (should update, not duplicate) --")
resp = client.post("/api/road", json={
    "road_id": TEST_AUDIT_INFRA_ID, "point_code": TEST_POINT_CODE, "median": True,
    "road_width_side_a": 3.0, "median_width": 1.0, "median_height": 0.2, "road_width_side_b": 3.0,
    "geometry_coords": [[77.65, 12.96], [77.6501, 12.9601]],
    "data_collection_timestamp": "2026-08-10T00:01:00Z",
}, headers=AUTH)
print(resp.status_code, resp.get_json())

print("\n-- verify + cleanup --")
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("SELECT audit_infra_id, point_code, median, road_width, road_width_side_a, median_width, road_width_side_b, ST_AsText(geometry) FROM road_profile WHERE point_code=%s", (TEST_POINT_CODE,))
print("road_profile rows:", cur.fetchall())
cur.execute("SELECT audit_infra_id, point_code, side, footpath_width_m, ST_AsText(geometry) FROM footpath_profile WHERE point_code=%s", (TEST_POINT_CODE,))
print("footpath_profile rows:", cur.fetchall())

cur.execute("DELETE FROM road_profile WHERE point_code=%s", (TEST_POINT_CODE,))
cur.execute("DELETE FROM footpath_profile WHERE point_code=%s", (TEST_POINT_CODE,))
conn.commit()
print("cleanup done, rows removed")
cur.close()
conn.close()
