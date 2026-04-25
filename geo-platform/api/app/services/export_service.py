"""Export service: GeoJSON / Shapefile / GeoPackage.

Both pyshp and fiona are sync libraries — they MUST run via asyncio.to_thread()
to avoid blocking the event loop.
"""
import asyncio
import io
import json
import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.layers import Layer

logger = logging.getLogger(__name__)


def _shp_field_name(name: str) -> str:
    """Truncate field name to 10 chars (Shapefile DBF limit)."""
    return (name or "field")[:10]


async def _fetch_features(
    shard_db: AsyncSession,
    layer_id: uuid.UUID,
    target_srid: int,
    *,
    as_wkb: bool = False,
) -> list[dict[str, Any]]:
    """Return list of {id, geom (geojson dict OR wkb bytes), properties}."""
    geom_select = (
        "ST_AsBinary(ST_Transform(geom, :srid)) AS geom"
        if as_wkb else
        "ST_AsGeoJSON(ST_Transform(geom, :srid))::jsonb AS geom"
    )
    sql = text(f"""
        SELECT id, {geom_select}, properties
        FROM features
        WHERE layer_id = CAST(:lid AS uuid) AND deleted_at IS NULL
        ORDER BY id
    """)
    result = await shard_db.execute(sql, {"lid": str(layer_id), "srid": target_srid})
    return [dict(r) for r in result.mappings().all()]


# ── GeoJSON ────────────────────────────────────────────────────────────────────

async def export_geojson(
    shard_db: AsyncSession,
    layer: Layer,
    target_srid: int,
) -> bytes:
    rows = await _fetch_features(shard_db, layer.id, target_srid)
    fc = {
        "type": "FeatureCollection",
        "name": layer.name,
        "crs": {"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{target_srid}"}},
        "features": [
            {
                "type": "Feature",
                "id": r["id"],
                "geometry": r["geom"] if isinstance(r["geom"], dict) else json.loads(r["geom"]),
                "properties": r["properties"] or {},
            }
            for r in rows
        ],
    }
    return json.dumps(fc, default=str).encode("utf-8")


# ── Shapefile (pyshp) ──────────────────────────────────────────────────────────

def _write_shapefile_sync(
    out_dir: str,
    base_name: str,
    rows: list[dict[str, Any]],
    field_specs: list[tuple[str, str]],
    target_srid: int,
) -> str:
    """Write .shp/.shx/.dbf/.prj into out_dir; returns the resulting .zip path."""
    import shapefile  # pyshp

    shp_path = os.path.join(out_dir, base_name)
    writer = shapefile.Writer(shp_path)
    writer.autoBalance = 1

    # Map original field name → truncated DBF column name
    dbf_names: list[str] = []
    for orig, ftype in field_specs:
        col = _shp_field_name(orig)
        # avoid duplicate truncations
        i = 1
        candidate = col
        while candidate in dbf_names:
            suffix = str(i)
            candidate = (col[: 10 - len(suffix)] + suffix)
            i += 1
        dbf_names.append(candidate)
        if ftype == "N":
            writer.field(candidate, "N", size=18, decimal=6)
        elif ftype == "L":
            writer.field(candidate, "L", size=1)
        else:
            writer.field(candidate, "C", size=254)

    for r in rows:
        # Geometry
        wkb = r["geom"]
        if wkb is None:
            continue
        try:
            from shapely import wkb as shapely_wkb
            shp = shapely_wkb.loads(bytes(wkb))
            geo = shp.__geo_interface__
            gtype = geo["type"]
            if gtype == "Point":
                writer.point(*geo["coordinates"])
            elif gtype == "MultiPoint":
                writer.multipoint(geo["coordinates"])
            elif gtype == "LineString":
                writer.line([geo["coordinates"]])
            elif gtype == "MultiLineString":
                writer.line(geo["coordinates"])
            elif gtype == "Polygon":
                writer.poly(geo["coordinates"])
            elif gtype == "MultiPolygon":
                # pyshp expects flat list of rings across all parts
                rings = []
                for poly in geo["coordinates"]:
                    rings.extend(poly)
                writer.poly(rings)
            else:
                continue
        except Exception as exc:
            logger.warning("skip feature id=%s shapefile geom: %s", r.get("id"), exc)
            continue

        props = r.get("properties") or {}
        record = []
        for orig, _ftype in field_specs:
            v = props.get(orig)
            record.append(v if v is not None else "")
        writer.record(*record)

    writer.close()

    # .prj — minimal WKT for the SRID (4326 fallback)
    prj_path = shp_path + ".prj"
    if target_srid == 4326:
        prj = (
            'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
            'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]'
        )
    else:
        prj = f'PROJCS["EPSG_{target_srid}",AUTHORITY["EPSG","{target_srid}"]]'
    with open(prj_path, "w", encoding="ascii") as f:
        f.write(prj)

    # Zip the four files
    zip_path = os.path.join(out_dir, f"{base_name}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for ext in (".shp", ".shx", ".dbf", ".prj"):
            p = shp_path + ext
            if os.path.exists(p):
                zf.write(p, arcname=os.path.basename(p))
    return zip_path


async def export_shapefile(
    shard_db: AsyncSession,
    meta_db: AsyncSession,
    layer: Layer,
    target_srid: int,
) -> bytes:
    rows = await _fetch_features(shard_db, layer.id, target_srid, as_wkb=True)
    # Discover field schema (best-effort): from layer_schema OR from first feature's properties
    from app.models.layers import LayerSchema
    from sqlalchemy import select as _select
    res = await meta_db.execute(_select(LayerSchema).where(LayerSchema.layer_id == layer.id))
    schema_obj = res.scalar_one_or_none()
    schema_fields = (schema_obj.json_schema or {}).get("fields", []) if schema_obj else []

    type_map = {"string": "C", "number": "N", "boolean": "L", "date": "C"}
    field_specs: list[tuple[str, str]] = []
    if schema_fields:
        for f in schema_fields:
            if isinstance(f, dict) and "name" in f:
                field_specs.append((f["name"], type_map.get(f.get("type"), "C")))
    else:
        # fall back to keys from first feature
        if rows:
            first_props = rows[0].get("properties") or {}
            for k, v in first_props.items():
                if isinstance(v, bool):
                    field_specs.append((k, "L"))
                elif isinstance(v, (int, float)):
                    field_specs.append((k, "N"))
                else:
                    field_specs.append((k, "C"))

    def _do_write() -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            base = (layer.name or "layer").replace(os.sep, "_")
            zip_path = _write_shapefile_sync(tmp, base, rows, field_specs, target_srid)
            with open(zip_path, "rb") as f:
                return f.read()

    return await asyncio.to_thread(_do_write)


# ── GeoPackage (fiona) ─────────────────────────────────────────────────────────

def _write_gpkg_sync(
    layer_name: str,
    rows: list[dict[str, Any]],
    field_specs: list[tuple[str, str]],
    target_srid: int,
) -> bytes:
    import fiona
    from fiona.crs import from_epsg

    # Determine geometry type from first feature
    geom_type = "Unknown"
    for r in rows:
        g = r.get("geom")
        if g is None:
            continue
        if isinstance(g, dict):
            geom_type = g.get("type", "Unknown")
            break
        try:
            geom_type = json.loads(g).get("type", "Unknown")
            break
        except Exception:
            continue
    if geom_type == "Unknown":
        geom_type = "Point"  # fallback

    type_map = {"C": "str", "N": "float", "L": "bool"}
    properties = {orig: type_map.get(t, "str") for orig, t in field_specs}
    schema = {"geometry": geom_type, "properties": properties}

    with tempfile.TemporaryDirectory() as tmp:
        out_path = os.path.join(tmp, f"{(layer_name or 'layer').replace(os.sep, '_')}.gpkg")
        with fiona.open(
            out_path, "w",
            driver="GPKG",
            crs=from_epsg(target_srid),
            schema=schema,
            layer=layer_name or "layer",
        ) as sink:
            for r in rows:
                g = r["geom"]
                if g is None:
                    continue
                if not isinstance(g, dict):
                    g = json.loads(g)
                sink.write({
                    "geometry": g,
                    "properties": {k: (r.get("properties") or {}).get(k) for k in properties},
                })
        with open(out_path, "rb") as f:
            return f.read()


async def export_gpkg(
    shard_db: AsyncSession,
    meta_db: AsyncSession,
    layer: Layer,
    target_srid: int,
) -> bytes:
    rows = await _fetch_features(shard_db, layer.id, target_srid)
    from app.models.layers import LayerSchema
    from sqlalchemy import select as _select
    res = await meta_db.execute(_select(LayerSchema).where(LayerSchema.layer_id == layer.id))
    schema_obj = res.scalar_one_or_none()
    schema_fields = (schema_obj.json_schema or {}).get("fields", []) if schema_obj else []

    type_map = {"string": "C", "number": "N", "boolean": "L", "date": "C"}
    field_specs: list[tuple[str, str]] = []
    if schema_fields:
        for f in schema_fields:
            if isinstance(f, dict) and "name" in f:
                field_specs.append((f["name"], type_map.get(f.get("type"), "C")))
    elif rows:
        first_props = rows[0].get("properties") or {}
        for k, v in first_props.items():
            if isinstance(v, bool):
                field_specs.append((k, "L"))
            elif isinstance(v, (int, float)):
                field_specs.append((k, "N"))
            else:
                field_specs.append((k, "C"))

    return await asyncio.to_thread(
        _write_gpkg_sync, layer.name or "layer", rows, field_specs, target_srid
    )


# ── SRID validation helper ─────────────────────────────────────────────────────

def validate_srid(app_state, srid: int) -> bool:
    valid = getattr(app_state, "valid_srids", None)
    if valid is None or not valid:
        return True  # no info → don't block
    return srid in valid
