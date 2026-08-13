"""
Backend proxy between the Drone Image Profiling tool (index.html) and the real Postgres
schema (road_profile / footpath_profile, discovered via check_db.py / check_db2.py against
the DB copy). The browser never sees DB credentials -- it POSTs plain JSON here, this
server does the actual parameterized INSERT/UPSERT.

REAL SCHEMA NOTES (see db-backend/check_db2.py output for how these were confirmed):
  - road_profile unique key:     (audit_infra_id, point_code)
  - footpath_profile unique key: (audit_infra_id, side, point_code)

  *** KNOWN BROKEN, DO NOT TRUST UNTIL FIXED (2026-08-12) ***
  road_id and audit_infra_id are CONFIRMED DIFFERENT, UNRELATED values (per the user,
  2026-08-12) -- audit_infra_id is not derivable from road_id by any mapping known so far.
  The point-code list's "id" property (what the frontend calls road_id) is NOT the same
  thing as audit_infra_id. road_profile/footpath_profile only have an audit_infra_id column
  (no road_id column exists there at all -- confirmed via check_db2.py's column dump), so
  this endpoint currently does something WRONG: it takes the incoming road_id and writes it
  straight into the audit_infra_id column below, as if they were the same number. They are
  not. Do not re-enable/rely on this endpoint for real writes until there's an actual known
  way to resolve the correct audit_infra_id (whatever that lookup turns out to be -- possibly
  via audit_infrastructure, possibly something else entirely; not yet investigated). This is
  harmless right now only because the whole DB save path is disabled in index.html.
  - geometry columns are PostGIS GEOMETRY(SRID 4326). The frontend sends plain [[lng,lat],
    [lng,lat]] coordinate pairs; this server builds the line via ST_MakeLine/ST_MakePoint.
  - form_filled and approved_status are NOT NULL but have DB defaults (false) -- never sent,
    Postgres fills them in.
  - road_profile.median is a plain boolean: false -> road_width is set, side_a/median_width/
    side_b/height stay NULL; true -> the reverse.

AUTH: every request must carry `Authorization: Bearer <API_TOKEN>` matching the API_TOKEN
env var -- this writes to a real database, so (unlike the old wide-open Apps Script sheet
endpoint) it should never be left open to the internet.

ENV VARS (set in Render's dashboard, never committed):
  DATABASE_URL  -- full Postgres connection string
  API_TOKEN     -- shared secret the frontend sends back
"""

import os
import functools
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ["DATABASE_URL"]
API_TOKEN = os.environ["API_TOKEN"]


def require_auth(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {API_TOKEN}":
            return jsonify({"status": "error", "message": "unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def geometry_sql(coords):
    """coords: [[lng,lat],[lng,lat]] -> a ST_MakeLine SQL fragment + its params."""
    (lng1, lat1), (lng2, lat2) = coords
    return (
        "ST_SetSRID(ST_MakeLine(ST_MakePoint(%s,%s), ST_MakePoint(%s,%s)), 4326)",
        [lng1, lat1, lng2, lat2],
    )


@app.route("/api/road", methods=["POST"])
@require_auth
def save_road():
    data = request.get_json(force=True)
    if "road_id" not in data or data["road_id"] is None:
        return jsonify({"status": "error", "message": "road_id is required"}), 400
    if "point_code" not in data or data["point_code"] is None:
        return jsonify({"status": "error", "message": "point_code is required"}), 400
    if not data.get("geometry_coords"):
        return jsonify({"status": "error", "message": "geometry_coords is required"}), 400

    geom_sql, geom_params = geometry_sql(data["geometry_coords"])

    # KNOWN WRONG -- see the *** KNOWN BROKEN *** note at the top of this file. road_id is
    # NOT audit_infra_id; this write needs a real resolution step before it can be trusted.
    columns = [
        "audit_infra_id", "point_code", "median", "road_width",
        "road_width_side_a", "median_width", "median_height", "road_width_side_b",
        "data_collection_timestamp", "geometry",
    ]
    values = [
        data["road_id"], data["point_code"], bool(data.get("median")), data.get("road_width"),
        data.get("road_width_side_a"), data.get("median_width"), data.get("median_height"), data.get("road_width_side_b"),
        data.get("data_collection_timestamp"),
    ]

    col_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * (len(columns) - 1) + [geom_sql])
    update_cols = [c for c in columns if c not in ("audit_infra_id", "point_code")]
    update_sql = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    query = (
        f"INSERT INTO road_profile ({col_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT (audit_infra_id, point_code) DO UPDATE SET {update_sql}"
    )

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, values + geom_params)
    finally:
        conn.close()

    return jsonify({"status": "ok"})


@app.route("/api/footpath", methods=["POST"])
@require_auth
def save_footpath():
    data = request.get_json(force=True)
    if "road_id" not in data or data["road_id"] is None:
        return jsonify({"status": "error", "message": "road_id is required"}), 400
    if "point_code" not in data or data["point_code"] is None:
        return jsonify({"status": "error", "message": "point_code is required"}), 400
    if data.get("side") not in ("A", "B"):
        return jsonify({"status": "error", "message": "side must be 'A' or 'B'"}), 400
    if not data.get("geometry_coords"):
        return jsonify({"status": "error", "message": "geometry_coords is required"}), 400

    geom_sql, geom_params = geometry_sql(data["geometry_coords"])

    # KNOWN WRONG -- see the *** KNOWN BROKEN *** note at the top of this file.
    columns = [
        "audit_infra_id", "point_code", "side", "footpath_width_m",
        "data_collection_timestamp", "geometry",
    ]
    values = [
        data["road_id"], data["point_code"], data["side"], data.get("footpath_width_m"),
        data.get("data_collection_timestamp"),
    ]

    col_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * (len(columns) - 1) + [geom_sql])
    update_cols = [c for c in columns if c not in ("audit_infra_id", "point_code", "side")]
    update_sql = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    query = (
        f"INSERT INTO footpath_profile ({col_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT (audit_infra_id, side, point_code) DO UPDATE SET {update_sql}"
    )

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, values + geom_params)
    finally:
        conn.close()

    return jsonify({"status": "ok"})


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "drone profiler db-backend is live"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
