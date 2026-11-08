"""Parquet storage contract: typed source projections plus lossless JSON payload.

The payload preserves unknown fields, explicit nulls, geometry and type drift.
It preserves parsed JSON values, not the byte representation of HTTP responses.
No canonical crime mapping or event deduplication occurs here.
"""
import json
import math
from hashlib import sha256
import pyarrow as pa

from . import detroit_arcgis

CONTRACT_VERSION = 2
TYPES = {
    'esriFieldTypeOID': pa.int64(), 'esriFieldTypeInteger': pa.int64(),
    'esriFieldTypeSmallInteger': pa.int64(), 'esriFieldTypeBigInteger': pa.int64(),
    'esriFieldTypeDate': pa.int64(),
    'esriFieldTypeDouble': pa.float64(), 'esriFieldTypeSingle': pa.float64(),
    'esriFieldTypeString': pa.string(), 'esriFieldTypeGUID': pa.string(),
    'esriFieldTypeGlobalID': pa.string(),
}

def schema_for(info):
    """Freeze a schema from layer metadata before the first batch, even if empty."""
    types = dict(info.field_types)
    fields = [pa.field(n, TYPES.get(types.get(n), pa.string())) for n in info.fields]
    return pa.schema([
        pa.field('attributes', pa.struct(fields)),
        pa.field('_feature_json', pa.string(), nullable=False),
        pa.field('_extra', pa.string()),
        pa.field('source_system', pa.string(), nullable=False),
        pa.field('pipeline_run_id', pa.string(), nullable=False),
        pa.field('ingested_at_utc', pa.timestamp('us', tz='UTC'), nullable=False),
    ], metadata={b'bronze_contract_version': b'2'})

def schema_hash(schema):
    """Hash the physical storage schema separately from the source fingerprint."""
    return sha256(str(schema).encode('utf-8')).hexdigest()

def fits(value, dtype):
    if value is None:
        return True
    if pa.types.is_integer(dtype):
        return type(value) is int and -(2**63) <= value < 2**63
    if pa.types.is_floating(dtype):
        return type(value) in (int, float) and math.isfinite(value)
    return isinstance(value, str)

def to_row(feature, schema, run_id, started):
    """Project valid source types; preserve all exceptions in JSON, never coerce IDs."""
    attrs = feature.get('attributes') or {}
    projected, extra = {}, {}
    for f in schema.field('attributes').type:
        value = attrs.get(f.name)
        projected[f.name] = value if fits(value, f.type) else None
        if not fits(value, f.type):
            extra[f.name] = value
    extra.update({k: v for k, v in attrs.items() if k not in projected})
    return {
        'attributes': projected,
        '_feature_json': json.dumps(feature, ensure_ascii=False, allow_nan=False),
        '_extra': json.dumps(extra, ensure_ascii=False, allow_nan=False) if extra else None,
        # Zur Laufzeit gelesen: ``use_source`` kann die Quelle gewechselt haben.
        'source_system': detroit_arcgis.SOURCE_SYSTEM, 'pipeline_run_id': run_id,
        'ingested_at_utc': started,
    }
