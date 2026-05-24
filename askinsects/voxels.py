from __future__ import annotations

import io
import json
import sqlite3
import struct
import zipfile
from pathlib import Path
from typing import Any


ELEMENT_TYPES: dict[str, tuple[str, int]] = {
    "MET_CHAR": ("b", 1),
    "MET_UCHAR": ("B", 1),
    "MET_SHORT": ("h", 2),
    "MET_USHORT": ("H", 2),
    "MET_INT": ("i", 4),
    "MET_UINT": ("I", 4),
    "MET_FLOAT": ("f", 4),
    "MET_DOUBLE": ("d", 8),
}


def _payload_for_record(index_path: Path, record_id: str) -> dict[str, Any]:
    with sqlite3.connect(index_path) as conn:
        row = conn.execute(
            "select payload_json from record_payloads where record_id=?",
            (record_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"record_id not found in payload table: {record_id}")
    payload = json.loads(str(row[0]))
    if not isinstance(payload, dict):
        raise ValueError(f"payload is not an object for record_id: {record_id}")
    return payload


def _read_zip_member(path: Path, member: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(member)


def _volume_bytes(access: dict[str, Any]) -> bytes:
    kind = str(access.get("kind"))
    archive_path = Path(str(access["archive_path"]))
    if kind == "zip_mha_local":
        return _read_zip_member(archive_path, str(access["member"]))
    if kind == "zip_raw_member":
        return _read_zip_member(archive_path, str(access["raw_member"]))
    if kind == "nested_zip_mha_local":
        nested_bytes = _read_zip_member(archive_path, str(access["nested_archive_member"]))
        with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
            return nested.read(str(access["member"]))
    if kind == "nested_zip_raw_member":
        nested_bytes = _read_zip_member(archive_path, str(access["nested_archive_member"]))
        with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
            return nested.read(str(access["raw_member"]))
    raise ValueError(f"unsupported voxel access kind: {kind}")


def read_voxel_value(*, index_path: Path, record_id: str, x: int, y: int, z: int) -> dict[str, Any]:
    payload = _payload_for_record(index_path, record_id)
    access = payload.get("voxel_access")
    if not isinstance(access, dict):
        raise ValueError(f"record has no voxel_access payload: {record_id}")

    dims = [int(value) for value in access.get("dim_size", [])]
    if len(dims) != 3:
        raise ValueError(f"record has invalid DimSize: {record_id}")
    dim_x, dim_y, dim_z = dims
    if not (0 <= x < dim_x and 0 <= y < dim_y and 0 <= z < dim_z):
        raise ValueError(f"coordinate out of bounds for {record_id}: ({x}, {y}, {z}) not within {dims}")

    element_type = str(access.get("element_type", ""))
    if element_type not in ELEMENT_TYPES:
        raise ValueError(f"unsupported MetaImage element type for {record_id}: {element_type}")
    code, byte_count = ELEMENT_TYPES[element_type]
    endian = ">" if access.get("byte_order_msb") is True else "<"
    data_offset = int(access.get("data_offset", 0))
    value_offset = data_offset + ((z * dim_y * dim_x) + (y * dim_x) + x) * byte_count
    data = _volume_bytes(access)
    if value_offset + byte_count > len(data):
        raise ValueError(f"voxel offset exceeds data size for {record_id}: {value_offset}")
    value = struct.unpack_from(f"{endian}{code}", data, value_offset)[0]
    if hasattr(value, "item"):
        value = value.item()
    return {
        "ok": True,
        "record_id": record_id,
        "coordinate": {"x": x, "y": y, "z": z},
        "dim_size": dims,
        "element_type": element_type,
        "value": value,
        "source_locator": payload.get("locator"),
    }
