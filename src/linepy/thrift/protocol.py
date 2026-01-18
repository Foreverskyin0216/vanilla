"""Thrift protocol implementations (Binary and Compact)."""

import struct
from io import BytesIO
from typing import Any

from .types import ThriftType


class TBinaryProtocol:
    """Thrift Binary Protocol implementation."""

    VERSION_MASK = 0xFFFF0000
    VERSION_1 = 0x80010000
    TYPE_MASK = 0x000000FF

    def __init__(self, transport: BytesIO):
        self.transport = transport

    def write_message_begin(self, name: str, message_type: int, seqid: int) -> None:
        version = self.VERSION_1 | message_type
        self.write_i32(version)
        self.write_string(name)
        self.write_i32(seqid)

    def write_message_end(self) -> None:
        pass

    def write_struct_begin(self, name: str = "") -> None:
        pass

    def write_struct_end(self) -> None:
        pass

    def write_field_begin(self, name: str, field_type: int, field_id: int) -> None:
        self.write_byte(field_type)
        self.write_i16(field_id)

    def write_field_end(self) -> None:
        pass

    def write_field_stop(self) -> None:
        self.write_byte(ThriftType.STOP)

    def write_map_begin(self, key_type: int, value_type: int, size: int) -> None:
        self.write_byte(key_type)
        self.write_byte(value_type)
        self.write_i32(size)

    def write_map_end(self) -> None:
        pass

    def write_list_begin(self, elem_type: int, size: int) -> None:
        self.write_byte(elem_type)
        self.write_i32(size)

    def write_list_end(self) -> None:
        pass

    def write_set_begin(self, elem_type: int, size: int) -> None:
        self.write_byte(elem_type)
        self.write_i32(size)

    def write_set_end(self) -> None:
        pass

    def write_bool(self, value: bool) -> None:
        self.write_byte(1 if value else 0)

    def write_byte(self, value: int) -> None:
        self.transport.write(struct.pack("!b", value))

    def write_i16(self, value: int) -> None:
        self.transport.write(struct.pack("!h", value))

    def write_i32(self, value: int) -> None:
        self.transport.write(struct.pack("!i", value))

    def write_i64(self, value: int) -> None:
        self.transport.write(struct.pack("!q", value))

    def write_double(self, value: float) -> None:
        self.transport.write(struct.pack("!d", value))

    def write_string(self, value: str) -> None:
        encoded = value.encode("utf-8")
        self.write_i32(len(encoded))
        self.transport.write(encoded)

    def write_binary(self, value: bytes) -> None:
        self.write_i32(len(value))
        self.transport.write(value)

    def read_message_begin(self) -> dict[str, Any]:
        sz = self.read_i32()
        if sz < 0:
            version = sz & self.VERSION_MASK
            if version != self.VERSION_1:
                raise Exception(f"Bad version in readMessageBegin: {version}")
            message_type = sz & self.TYPE_MASK
            name = self.read_string()
            seqid = self.read_i32()
            return {"fname": name, "mtype": message_type, "rseqid": seqid}
        else:
            name = self.transport.read(sz).decode("utf-8")
            message_type = self.read_byte()
            seqid = self.read_i32()
            return {"fname": name, "mtype": message_type, "rseqid": seqid}

    def read_message_end(self) -> None:
        pass

    def read_struct_begin(self) -> None:
        pass

    def read_struct_end(self) -> None:
        pass

    def read_field_begin(self) -> dict[str, int]:
        field_type = self.read_byte()
        if field_type == ThriftType.STOP:
            return {"ftype": ThriftType.STOP, "fid": 0}
        field_id = self.read_i16()
        return {"ftype": field_type, "fid": field_id}

    def read_field_end(self) -> None:
        pass

    def read_map_begin(self) -> dict[str, int]:
        key_type = self.read_byte()
        value_type = self.read_byte()
        size = self.read_i32()
        return {"ktype": key_type, "vtype": value_type, "size": size}

    def read_map_end(self) -> None:
        pass

    def read_list_begin(self) -> dict[str, int]:
        elem_type = self.read_byte()
        size = self.read_i32()
        return {"etype": elem_type, "size": size}

    def read_list_end(self) -> None:
        pass

    def read_set_begin(self) -> dict[str, int]:
        elem_type = self.read_byte()
        size = self.read_i32()
        return {"etype": elem_type, "size": size}

    def read_set_end(self) -> None:
        pass

    def read_bool(self) -> bool:
        return self.read_byte() != 0

    def read_byte(self) -> int:
        data = self.transport.read(1)
        if len(data) < 1:
            raise Exception("Unexpected end of data")
        return struct.unpack("!b", data)[0]

    def read_i16(self) -> int:
        data = self.transport.read(2)
        if len(data) < 2:
            raise Exception("Unexpected end of data")
        return struct.unpack("!h", data)[0]

    def read_i32(self) -> int:
        data = self.transport.read(4)
        if len(data) < 4:
            raise Exception("Unexpected end of data")
        return struct.unpack("!i", data)[0]

    def read_i64(self) -> int:
        data = self.transport.read(8)
        if len(data) < 8:
            raise Exception("Unexpected end of data")
        return struct.unpack("!q", data)[0]

    def read_double(self) -> float:
        data = self.transport.read(8)
        if len(data) < 8:
            raise Exception("Unexpected end of data")
        return struct.unpack("!d", data)[0]

    def read_string(self) -> str:
        size = self.read_i32()
        data = self.transport.read(size)
        return data.decode("utf-8")

    def read_binary(self) -> bytes:
        size = self.read_i32()
        return self.transport.read(size)

    def skip(self, field_type: int) -> None:
        if field_type == ThriftType.BOOL:
            self.read_bool()
        elif field_type == ThriftType.BYTE:
            self.read_byte()
        elif field_type == ThriftType.I16:
            self.read_i16()
        elif field_type == ThriftType.I32:
            self.read_i32()
        elif field_type == ThriftType.I64:
            self.read_i64()
        elif field_type == ThriftType.DOUBLE:
            self.read_double()
        elif field_type == ThriftType.STRING:
            self.read_binary()
        elif field_type == ThriftType.STRUCT:
            self.read_struct_begin()
            while True:
                field = self.read_field_begin()
                if field["ftype"] == ThriftType.STOP:
                    break
                self.skip(field["ftype"])
                self.read_field_end()
            self.read_struct_end()
        elif field_type == ThriftType.MAP:
            map_info = self.read_map_begin()
            for _ in range(map_info["size"]):
                self.skip(map_info["ktype"])
                self.skip(map_info["vtype"])
            self.read_map_end()
        elif field_type == ThriftType.SET or field_type == ThriftType.LIST:
            container_info = self.read_list_begin()
            for _ in range(container_info["size"]):
                self.skip(container_info["etype"])
            self.read_list_end()


class TCompactProtocol:
    """Thrift Compact Protocol implementation."""

    PROTOCOL_ID = 0x82
    VERSION = 1
    VERSION_MASK = 0x1F
    TYPE_MASK = 0xE0
    TYPE_BITS = 0x07
    TYPE_SHIFT_AMOUNT = 5

    # Compact type codes (int -> int mapping)
    CTYPES: dict[int, int] = {
        ThriftType.STOP: 0,
        ThriftType.BOOL: 2,
        ThriftType.BYTE: 3,
        ThriftType.I16: 4,
        ThriftType.I32: 5,
        ThriftType.I64: 6,
        ThriftType.DOUBLE: 7,
        ThriftType.STRING: 8,
        ThriftType.LIST: 9,
        ThriftType.SET: 10,
        ThriftType.MAP: 11,
        ThriftType.STRUCT: 12,
    }

    TTYPES: dict[int, int] = {v: k for k, v in CTYPES.items()}
    TTYPES[1] = ThriftType.BOOL  # TRUE
    TTYPES[2] = ThriftType.BOOL  # FALSE

    def __init__(self, transport: BytesIO):
        self.transport = transport
        self._last_field_id = 0
        self._last_field_id_stack: list[int] = []
        self._bool_field_id: int | None = None
        self._bool_value: bool | None = None

    def _write_varint(self, value: int) -> None:
        """Write a variable-length integer."""
        while True:
            byte = value & 0x7F
            value >>= 7
            if value != 0:
                self.transport.write(bytes([byte | 0x80]))
            else:
                self.transport.write(bytes([byte]))
                break

    def _read_varint(self) -> int:
        """Read a variable-length integer."""
        result = 0
        shift = 0
        while True:
            byte = self.transport.read(1)
            if len(byte) < 1:
                raise Exception("Unexpected end of data")
            b = byte[0]
            result |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                break
            shift += 7
        return result

    def _to_zigzag(self, value: int) -> int:
        """Convert to zigzag encoding."""
        return (value << 1) ^ (value >> 63)

    def _from_zigzag(self, value: int) -> int:
        """Convert from zigzag encoding."""
        return (value >> 1) ^ -(value & 1)

    def _get_compact_type(self, ttype: int) -> int:
        """Get compact type code."""
        return self.CTYPES.get(ttype, 0)

    def write_message_begin(self, name: str, message_type: int, seqid: int) -> None:
        self.transport.write(bytes([self.PROTOCOL_ID]))
        self.transport.write(
            bytes(
                [
                    (self.VERSION & self.VERSION_MASK)
                    | ((message_type << self.TYPE_SHIFT_AMOUNT) & self.TYPE_MASK)
                ]
            )
        )
        self._write_varint(seqid)
        self.write_string(name)

    def write_message_end(self) -> None:
        pass

    def write_struct_begin(self, name: str = "") -> None:
        self._last_field_id_stack.append(self._last_field_id)
        self._last_field_id = 0

    def write_struct_end(self) -> None:
        self._last_field_id = self._last_field_id_stack.pop()

    def write_field_begin(self, name: str, field_type: int, field_id: int) -> None:
        if field_type == ThriftType.BOOL:
            self._bool_field_id = field_id
        else:
            self._write_field_begin_internal(field_type, field_id)

    def _write_field_begin_internal(
        self, field_type: int, field_id: int, type_override: int | None = None
    ) -> None:
        compact_type = (
            type_override if type_override is not None else self._get_compact_type(field_type)
        )
        delta = field_id - self._last_field_id
        if 0 < delta <= 15:
            self.transport.write(bytes([(delta << 4) | compact_type]))
        else:
            self.transport.write(bytes([compact_type]))
            self._write_varint(self._to_zigzag(field_id))
        self._last_field_id = field_id

    def write_field_end(self) -> None:
        pass

    def write_field_stop(self) -> None:
        self.transport.write(bytes([ThriftType.STOP]))

    def write_map_begin(self, key_type: int, value_type: int, size: int) -> None:
        if size == 0:
            self.transport.write(bytes([0]))
        else:
            self._write_varint(size)
            key_compact = self._get_compact_type(key_type)
            value_compact = self._get_compact_type(value_type)
            self.transport.write(bytes([(key_compact << 4) | value_compact]))

    def write_map_end(self) -> None:
        pass

    def write_list_begin(self, elem_type: int, size: int) -> None:
        compact_type = self._get_compact_type(elem_type)
        if size < 15:
            self.transport.write(bytes([(size << 4) | compact_type]))
        else:
            self.transport.write(bytes([0xF0 | compact_type]))
            self._write_varint(size)

    def write_list_end(self) -> None:
        pass

    def write_set_begin(self, elem_type: int, size: int) -> None:
        self.write_list_begin(elem_type, size)

    def write_set_end(self) -> None:
        pass

    def write_bool(self, value: bool) -> None:
        if self._bool_field_id is not None:
            self._write_field_begin_internal(
                ThriftType.BOOL, self._bool_field_id, 1 if value else 2
            )
            self._bool_field_id = None
        else:
            self.transport.write(bytes([1 if value else 0]))

    def write_byte(self, value: int) -> None:
        self.transport.write(struct.pack("!b", value))

    def write_i16(self, value: int) -> None:
        self._write_varint(self._to_zigzag(value))

    def write_i32(self, value: int) -> None:
        self._write_varint(self._to_zigzag(value))

    def write_i64(self, value: int) -> None:
        self._write_varint(self._to_zigzag(value))

    def write_double(self, value: float) -> None:
        self.transport.write(struct.pack("<d", value))

    def write_string(self, value: str) -> None:
        encoded = value.encode("utf-8")
        self._write_varint(len(encoded))
        self.transport.write(encoded)

    def write_binary(self, value: bytes) -> None:
        self._write_varint(len(value))
        self.transport.write(value)

    def read_message_begin(self) -> dict[str, Any]:
        proto_id = self.transport.read(1)[0]
        if proto_id != self.PROTOCOL_ID:
            raise Exception(f"Bad protocol id: {proto_id}")
        ver_type = self.transport.read(1)[0]
        version = ver_type & self.VERSION_MASK
        if version != self.VERSION:
            raise Exception(f"Bad version: {version}")
        message_type = (ver_type >> self.TYPE_SHIFT_AMOUNT) & self.TYPE_BITS
        seqid = self._read_varint()
        name = self.read_string()
        return {"fname": name, "mtype": message_type, "rseqid": seqid}

    def read_message_end(self) -> None:
        pass

    def read_struct_begin(self) -> None:
        self._last_field_id_stack.append(self._last_field_id)
        self._last_field_id = 0

    def read_struct_end(self) -> None:
        self._last_field_id = self._last_field_id_stack.pop()

    def read_field_begin(self) -> dict[str, int]:
        byte_data = self.transport.read(1)
        if len(byte_data) < 1:
            return {"ftype": ThriftType.STOP, "fid": 0}
        b = byte_data[0]
        if b == 0:
            return {"ftype": ThriftType.STOP, "fid": 0}

        delta = (b >> 4) & 0x0F
        compact_type = b & 0x0F

        if delta == 0:
            field_id = self._from_zigzag(self._read_varint())
        else:
            field_id = self._last_field_id + delta

        self._last_field_id = field_id

        field_type: int
        if compact_type == 1:
            self._bool_value = True
            field_type = ThriftType.BOOL
        elif compact_type == 2:
            self._bool_value = False
            field_type = ThriftType.BOOL
        else:
            field_type = self.TTYPES.get(compact_type, ThriftType.STOP)

        return {"ftype": field_type, "fid": field_id}

    def read_field_end(self) -> None:
        pass

    def read_map_begin(self) -> dict[str, int]:
        size = self._read_varint()
        if size == 0:
            return {"ktype": ThriftType.STOP, "vtype": ThriftType.STOP, "size": 0}
        types = self.transport.read(1)[0]
        key_type = self.TTYPES.get((types >> 4) & 0x0F, ThriftType.STOP)
        value_type = self.TTYPES.get(types & 0x0F, ThriftType.STOP)
        return {"ktype": key_type, "vtype": value_type, "size": size}

    def read_map_end(self) -> None:
        pass

    def read_list_begin(self) -> dict[str, int]:
        size_type = self.transport.read(1)[0]
        size = (size_type >> 4) & 0x0F
        compact_type = size_type & 0x0F
        if size == 15:
            size = self._read_varint()
        elem_type = self.TTYPES.get(compact_type, ThriftType.STOP)
        return {"etype": elem_type, "size": size}

    def read_list_end(self) -> None:
        pass

    def read_set_begin(self) -> dict[str, int]:
        return self.read_list_begin()

    def read_set_end(self) -> None:
        pass

    def read_bool(self) -> bool:
        if self._bool_value is not None:
            value = self._bool_value
            self._bool_value = None
            return value
        return self.transport.read(1)[0] == 1

    def read_byte(self) -> int:
        data = self.transport.read(1)
        if len(data) < 1:
            raise Exception("Unexpected end of data")
        return struct.unpack("!b", data)[0]

    def read_i16(self) -> int:
        return self._from_zigzag(self._read_varint())

    def read_i32(self) -> int:
        return self._from_zigzag(self._read_varint())

    def read_i64(self) -> int:
        return self._from_zigzag(self._read_varint())

    def read_double(self) -> float:
        data = self.transport.read(8)
        if len(data) < 8:
            raise Exception("Unexpected end of data")
        return struct.unpack("<d", data)[0]

    def read_string(self) -> str:
        size = self._read_varint()
        data = self.transport.read(size)
        return data.decode("utf-8")

    def read_binary(self) -> bytes:
        size = self._read_varint()
        return self.transport.read(size)

    def skip(self, field_type: int) -> None:
        if field_type == ThriftType.BOOL:
            self.read_bool()
        elif field_type == ThriftType.BYTE:
            self.read_byte()
        elif field_type == ThriftType.I16:
            self.read_i16()
        elif field_type == ThriftType.I32:
            self.read_i32()
        elif field_type == ThriftType.I64:
            self.read_i64()
        elif field_type == ThriftType.DOUBLE:
            self.read_double()
        elif field_type == ThriftType.STRING:
            self.read_binary()
        elif field_type == ThriftType.STRUCT:
            self.read_struct_begin()
            while True:
                field = self.read_field_begin()
                if field["ftype"] == ThriftType.STOP:
                    break
                self.skip(field["ftype"])
                self.read_field_end()
            self.read_struct_end()
        elif field_type == ThriftType.MAP:
            map_info = self.read_map_begin()
            for _ in range(map_info["size"]):
                self.skip(map_info["ktype"])
                self.skip(map_info["vtype"])
            self.read_map_end()
        elif field_type == ThriftType.SET or field_type == ThriftType.LIST:
            container_info = self.read_list_begin()
            for _ in range(container_info["size"]):
                self.skip(container_info["etype"])
            self.read_list_end()


# Protocol key mapping
PROTOCOLS: dict[int, type[TBinaryProtocol] | type[TCompactProtocol]] = {
    3: TBinaryProtocol,
    4: TCompactProtocol,
}


def gen_header_v3(name: str) -> bytes:
    """Generate v3 (Binary Protocol) header."""
    name_bytes = name.encode("utf-8")
    if len(name_bytes) > 0xFF:
        raise ValueError("genHeader v3: name too long")
    prefix = bytes([0x80, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, len(name_bytes)])
    suffix = bytes([0x00, 0x00, 0x00, 0x00])
    return prefix + name_bytes + suffix


def gen_header_v4(name: str) -> bytes:
    """Generate v4 (Compact Protocol) header."""
    name_bytes = name.encode("utf-8")
    if len(name_bytes) > 0xFF:
        raise ValueError("genHeader v4: name too long (max 255 bytes)")
    header = bytes([0x82, 0x21, 0x00, len(name_bytes)])
    return header + name_bytes


GEN_HEADER = {
    3: gen_header_v3,
    4: gen_header_v4,
}
