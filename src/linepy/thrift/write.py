"""Thrift write/serialization functions."""

from io import BytesIO
from typing import Any

from .protocol import GEN_HEADER, PROTOCOLS, TBinaryProtocol, TCompactProtocol
from .types import NestedArray, ThriftType


def write_thrift(
    value: NestedArray,
    name: str,
    protocol_key: int = 4,
) -> bytes:
    """
    Serialize a nested array to thrift binary format with header.

    Args:
        value: The nested array to serialize
        name: The method name
        protocol_key: 3 for Binary, 4 for Compact protocol

    Returns:
        The serialized bytes with header
    """
    transport = BytesIO()
    protocol_class = PROTOCOLS[protocol_key]
    protocol = protocol_class(transport)

    _write_struct(protocol, value)

    body = transport.getvalue()
    if len(body) == 1 and body[0] == 0:
        body = b""

    header = GEN_HEADER[protocol_key](name)
    return header + body + bytes([0])


def write_struct(
    value: NestedArray,
    protocol_key: int = 4,
) -> bytes:
    """
    Serialize a nested array to thrift binary format without header.

    Args:
        value: The nested array to serialize
        protocol_key: 3 for Binary, 4 for Compact protocol

    Returns:
        The serialized bytes
    """
    transport = BytesIO()
    protocol_class = PROTOCOLS[protocol_key]
    protocol = protocol_class(transport)

    _write_struct(protocol, value)

    body = transport.getvalue()
    if len(body) == 1 and body[0] == 0:
        body = b""

    return body


def _write_struct(
    output: TBinaryProtocol | TCompactProtocol,
    value: NestedArray,
) -> None:
    """Write a struct to the protocol."""
    if not value:
        return

    output.write_struct_begin()

    for item in value:
        if item is None:
            continue
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            _write_value(output, item[0], item[1], item[2])

    output.write_field_stop()
    output.write_struct_end()


def _write_value(
    output: TBinaryProtocol | TCompactProtocol,
    ftype: int,
    fid: int,
    val: Any,
) -> None:
    """Write a field value to the protocol."""
    if val is None:
        return

    if ftype == ThriftType.STRING:
        if isinstance(val, bytes):
            output.write_field_begin("", ThriftType.STRING, fid)
            output.write_binary(val)
            output.write_field_end()
        else:
            if not isinstance(val, str):
                raise TypeError(f"ftype={ftype}: value is not string")
            output.write_field_begin("", ThriftType.STRING, fid)
            output.write_string(str(val))
            output.write_field_end()

    elif ftype == ThriftType.DOUBLE:
        if not isinstance(val, (int, float)):
            raise TypeError(f"ftype={ftype}: value is not number")
        output.write_field_begin("", ThriftType.DOUBLE, fid)
        output.write_double(float(val))
        output.write_field_end()

    elif ftype == ThriftType.I64:
        if not isinstance(val, int):
            raise TypeError(f"ftype={ftype}: value is not number")
        output.write_field_begin("", ThriftType.I64, fid)
        output.write_i64(val)
        output.write_field_end()

    elif ftype == ThriftType.I32:
        if not isinstance(val, int):
            raise TypeError(f"ftype={ftype}: value is not number")
        output.write_field_begin("", ThriftType.I32, fid)
        output.write_i32(val)
        output.write_field_end()

    elif ftype == ThriftType.I16:
        if not isinstance(val, int):
            raise TypeError(f"ftype={ftype}: value is not number")
        output.write_field_begin("", ThriftType.I16, fid)
        output.write_i16(val)
        output.write_field_end()

    elif ftype == ThriftType.BYTE:
        if not isinstance(val, int):
            raise TypeError(f"ftype={ftype}: value is not number")
        output.write_field_begin("", ThriftType.BYTE, fid)
        output.write_byte(val)
        output.write_field_end()

    elif ftype == ThriftType.BOOL:
        output.write_field_begin("", ThriftType.BOOL, fid)
        output.write_bool(bool(val))
        output.write_field_end()

    elif ftype == ThriftType.STRUCT:
        if not isinstance(val, (list, tuple)):
            raise TypeError(f"ftype={ftype}: value is not struct")
        if not val:
            return
        output.write_field_begin("", ThriftType.STRUCT, fid)
        _write_struct(output, val)
        output.write_field_end()

    elif ftype == ThriftType.MAP:
        if not isinstance(val, (list, tuple)) or len(val) < 3:
            return
        key_type, value_type, data = val[0], val[1], val[2]
        if data is None:
            return
        output.write_field_begin("", ThriftType.MAP, fid)
        if isinstance(data, dict):
            keys = list(data.keys())
            output.write_map_begin(key_type, value_type, len(keys))
            for k in keys:
                v = data[k]
                _write_value_inline(output, key_type, k)
                _write_value_inline(output, value_type, v)
            output.write_map_end()
        output.write_field_end()

    elif ftype == ThriftType.LIST:
        if not isinstance(val, (list, tuple)) or len(val) < 2:
            return
        elem_type = val[0]
        data = val[1]
        if data is None:
            return
        output.write_field_begin("", ThriftType.LIST, fid)
        output.write_list_begin(elem_type, len(data))
        for item in data:
            _write_value_inline(output, elem_type, item)
        output.write_list_end()
        output.write_field_end()

    elif ftype == ThriftType.SET:
        if not isinstance(val, (list, tuple)) or len(val) < 2:
            return
        elem_type = val[0]
        data = val[1]
        if data is None:
            return
        output.write_field_begin("", ThriftType.SET, fid)
        output.write_set_begin(elem_type, len(data))
        for item in data:
            _write_value_inline(output, elem_type, item)
        output.write_set_end()
        output.write_field_end()


def _write_value_inline(
    output: TBinaryProtocol | TCompactProtocol,
    ftype: int,
    val: Any,
) -> None:
    """Write a value without field header (for lists/maps/sets)."""
    if val is None:
        return

    if ftype == ThriftType.STRING:
        if isinstance(val, bytes):
            output.write_binary(val)
        else:
            output.write_string(str(val))

    elif ftype == ThriftType.DOUBLE:
        output.write_double(float(val))

    elif ftype == ThriftType.I64:
        output.write_i64(int(val))

    elif ftype == ThriftType.I32:
        output.write_i32(int(val))

    elif ftype == ThriftType.I16:
        output.write_i16(int(val))

    elif ftype == ThriftType.BYTE:
        output.write_byte(int(val))

    elif ftype == ThriftType.BOOL:
        output.write_bool(bool(val))

    elif ftype == ThriftType.STRUCT:
        _write_struct(output, val)
