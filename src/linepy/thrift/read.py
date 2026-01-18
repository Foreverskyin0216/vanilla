"""Thrift read/deserialization functions."""

from io import BytesIO
from typing import Any

from .protocol import PROTOCOLS, TBinaryProtocol, TCompactProtocol
from .types import ParsedThrift, ThriftType


def is_binary(data: bytes) -> bool:
    """Check if data is binary (cannot be safely round-tripped as UTF-8 string).

    Returns True if:
    - Data cannot be decoded as UTF-8, or
    - Data decoded and re-encoded doesn't match original bytes
    """
    try:
        decoded = data.decode("utf-8")
        # Check if round-trip produces different bytes
        if decoded.encode("utf-8") != data:
            return True
        return False
    except UnicodeDecodeError:
        return True


def big_int(data: bytes) -> int | int:
    """Convert bytes to int, returning int if safe."""
    value = int.from_bytes(data, byteorder="big", signed=True)
    return value


def read_thrift(
    data: bytes,
    protocol_key: int = 4,
) -> ParsedThrift:
    """
    Deserialize thrift binary data to a ParsedThrift object.

    Args:
        data: The binary data to deserialize
        protocol_key: 3 for Binary, 4 for Compact protocol

    Returns:
        ParsedThrift containing the deserialized data
    """
    transport = BytesIO(data)
    protocol_class = PROTOCOLS[protocol_key]
    protocol = protocol_class(transport)

    msg_info = protocol.read_message_begin()
    thrift_data = _read_struct(protocol)
    protocol.read_message_end()

    return ParsedThrift(thrift_data, msg_info)


def read_thrift_struct(
    data: bytes,
    protocol_key: int = 4,
) -> dict[int, Any]:
    """
    Deserialize thrift struct data without message header.

    Args:
        data: The binary data to deserialize
        protocol_key: 3 for Binary, 4 for Compact protocol

    Returns:
        Dictionary mapping field IDs to values
    """
    transport = BytesIO(data)
    protocol_class = PROTOCOLS[protocol_key]
    protocol = protocol_class(transport)

    return _read_struct(protocol)


def _read_struct(
    input_protocol: TBinaryProtocol | TCompactProtocol,
) -> dict[int, Any]:
    """Read a struct from the protocol."""
    result: dict[int, Any] = {}
    input_protocol.read_struct_begin()

    while True:
        field = input_protocol.read_field_begin()
        ftype = field["ftype"]
        fid = field["fid"]

        if ftype == ThriftType.STOP:
            break

        result[fid] = _read_value(input_protocol, ftype)
        input_protocol.read_field_end()

    input_protocol.read_struct_end()
    return result


def _read_value(
    input_protocol: TBinaryProtocol | TCompactProtocol,
    ftype: int,
) -> Any:
    """Read a value based on its type."""
    if ftype == ThriftType.STRUCT:
        return _read_struct(input_protocol)

    elif ftype == ThriftType.I32:
        return input_protocol.read_i32()

    elif ftype == ThriftType.I64:
        return input_protocol.read_i64()

    elif ftype == ThriftType.STRING:
        data = input_protocol.read_binary()
        if is_binary(data):
            return data
        else:
            return data.decode("utf-8")

    elif ftype == ThriftType.LIST:
        result = []
        list_info = input_protocol.read_list_begin()
        for _ in range(list_info["size"]):
            result.append(_read_value(input_protocol, list_info["etype"]))
        input_protocol.read_list_end()
        return result

    elif ftype == ThriftType.MAP:
        map_result: dict[Any, Any] = {}
        map_info = input_protocol.read_map_begin()
        for _ in range(map_info["size"]):
            key = _read_value(input_protocol, map_info["ktype"])
            value = _read_value(input_protocol, map_info["vtype"])
            map_result[key] = value
        input_protocol.read_map_end()
        return map_result

    elif ftype == ThriftType.SET:
        result = []
        set_info = input_protocol.read_set_begin()
        for _ in range(set_info["size"]):
            result.append(_read_value(input_protocol, set_info["etype"]))
        input_protocol.read_set_end()
        return result

    elif ftype == ThriftType.BOOL:
        return input_protocol.read_bool()

    elif ftype == ThriftType.DOUBLE:
        return input_protocol.read_double()

    elif ftype == ThriftType.BYTE:
        return input_protocol.read_byte()

    elif ftype == ThriftType.I16:
        return input_protocol.read_i16()

    else:
        input_protocol.skip(ftype)
        return None
