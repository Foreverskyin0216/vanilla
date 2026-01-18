"""Tests for linepy/thrift/protocol.py."""

import struct
from io import BytesIO

import pytest

from src.linepy.thrift.protocol import (
    GEN_HEADER,
    PROTOCOLS,
    TBinaryProtocol,
    TCompactProtocol,
    gen_header_v3,
    gen_header_v4,
)
from src.linepy.thrift.types import ThriftType


class TestTBinaryProtocol:
    """Tests for TBinaryProtocol."""

    def test_write_and_read_byte(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_byte(42)
        transport.seek(0)
        assert protocol.read_byte() == 42

    def test_write_and_read_byte_negative(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_byte(-10)
        transport.seek(0)
        assert protocol.read_byte() == -10

    def test_write_and_read_i16(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_i16(12345)
        transport.seek(0)
        assert protocol.read_i16() == 12345

    def test_write_and_read_i16_negative(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_i16(-5000)
        transport.seek(0)
        assert protocol.read_i16() == -5000

    def test_write_and_read_i32(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_i32(123456789)
        transport.seek(0)
        assert protocol.read_i32() == 123456789

    def test_write_and_read_i32_negative(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_i32(-987654321)
        transport.seek(0)
        assert protocol.read_i32() == -987654321

    def test_write_and_read_i64(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_i64(9223372036854775807)
        transport.seek(0)
        assert protocol.read_i64() == 9223372036854775807

    def test_write_and_read_i64_negative(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_i64(-9223372036854775808)
        transport.seek(0)
        assert protocol.read_i64() == -9223372036854775808

    def test_write_and_read_double(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_double(3.14159265359)
        transport.seek(0)
        assert protocol.read_double() == pytest.approx(3.14159265359)

    def test_write_and_read_bool_true(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_bool(True)
        transport.seek(0)
        assert protocol.read_bool() is True

    def test_write_and_read_bool_false(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_bool(False)
        transport.seek(0)
        assert protocol.read_bool() is False

    def test_write_and_read_string(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_string("Hello, World!")
        transport.seek(0)
        assert protocol.read_string() == "Hello, World!"

    def test_write_and_read_string_unicode(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_string("你好世界")
        transport.seek(0)
        assert protocol.read_string() == "你好世界"

    def test_write_and_read_binary(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        data = b"\x00\x01\x02\x03\xff"
        protocol.write_binary(data)
        transport.seek(0)
        assert protocol.read_binary() == data

    def test_write_and_read_field_begin(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_field_begin("test", ThriftType.STRING, 5)
        transport.seek(0)
        field = protocol.read_field_begin()
        assert field["ftype"] == ThriftType.STRING
        assert field["fid"] == 5

    def test_read_field_begin_stop(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_field_stop()
        transport.seek(0)
        field = protocol.read_field_begin()
        assert field["ftype"] == ThriftType.STOP
        assert field["fid"] == 0

    def test_write_and_read_map_begin(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_map_begin(ThriftType.STRING, ThriftType.I32, 3)
        transport.seek(0)
        map_info = protocol.read_map_begin()
        assert map_info["ktype"] == ThriftType.STRING
        assert map_info["vtype"] == ThriftType.I32
        assert map_info["size"] == 3

    def test_write_and_read_list_begin(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_list_begin(ThriftType.I64, 5)
        transport.seek(0)
        list_info = protocol.read_list_begin()
        assert list_info["etype"] == ThriftType.I64
        assert list_info["size"] == 5

    def test_write_and_read_set_begin(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_set_begin(ThriftType.BOOL, 2)
        transport.seek(0)
        set_info = protocol.read_set_begin()
        assert set_info["etype"] == ThriftType.BOOL
        assert set_info["size"] == 2

    def test_write_and_read_message_begin_versioned(self):
        # Test reading a versioned message (created manually since VERSION_1 | mtype overflows i32)
        # The binary protocol uses versioned format with negative first int32
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        # Write version as signed int (-2147418111 = 0x80010001)
        transport.write(struct.pack("!i", -2147418111))  # VERSION_1 | mtype=1
        protocol.write_string("testMethod")
        protocol.write_i32(42)
        transport.seek(0)
        msg = protocol.read_message_begin()
        assert msg["fname"] == "testMethod"
        assert msg["mtype"] == 1
        assert msg["rseqid"] == 42

    def test_skip_bool(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_bool(True)
        transport.seek(0)
        protocol.skip(ThriftType.BOOL)
        assert transport.read() == b""

    def test_skip_i32(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_i32(12345)
        transport.seek(0)
        protocol.skip(ThriftType.I32)
        assert transport.read() == b""

    def test_skip_string(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_string("test string")
        transport.seek(0)
        protocol.skip(ThriftType.STRING)
        assert transport.read() == b""

    def test_read_byte_eof_raises(self):
        transport = BytesIO(b"")
        protocol = TBinaryProtocol(transport)
        with pytest.raises(Exception, match="Unexpected end of data"):
            protocol.read_byte()

    def test_read_i16_eof_raises(self):
        transport = BytesIO(b"\x00")
        protocol = TBinaryProtocol(transport)
        with pytest.raises(Exception, match="Unexpected end of data"):
            protocol.read_i16()

    def test_read_i32_eof_raises(self):
        transport = BytesIO(b"\x00\x00")
        protocol = TBinaryProtocol(transport)
        with pytest.raises(Exception, match="Unexpected end of data"):
            protocol.read_i32()

    def test_read_i64_eof_raises(self):
        transport = BytesIO(b"\x00\x00\x00\x00")
        protocol = TBinaryProtocol(transport)
        with pytest.raises(Exception, match="Unexpected end of data"):
            protocol.read_i64()

    def test_read_double_eof_raises(self):
        transport = BytesIO(b"\x00\x00\x00\x00")
        protocol = TBinaryProtocol(transport)
        with pytest.raises(Exception, match="Unexpected end of data"):
            protocol.read_double()


class TestTCompactProtocol:
    """Tests for TCompactProtocol."""

    def test_write_and_read_byte(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_byte(42)
        transport.seek(0)
        assert protocol.read_byte() == 42

    def test_write_and_read_i16(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_i16(12345)
        transport.seek(0)
        assert protocol.read_i16() == 12345

    def test_write_and_read_i16_negative(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_i16(-5000)
        transport.seek(0)
        assert protocol.read_i16() == -5000

    def test_write_and_read_i32(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_i32(123456789)
        transport.seek(0)
        assert protocol.read_i32() == 123456789

    def test_write_and_read_i32_negative(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_i32(-987654321)
        transport.seek(0)
        assert protocol.read_i32() == -987654321

    def test_write_and_read_i64(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_i64(9223372036854775807)
        transport.seek(0)
        assert protocol.read_i64() == 9223372036854775807

    def test_write_and_read_i64_negative(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_i64(-9223372036854775808)
        transport.seek(0)
        assert protocol.read_i64() == -9223372036854775808

    def test_write_and_read_double(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_double(3.14159265359)
        transport.seek(0)
        assert protocol.read_double() == pytest.approx(3.14159265359)

    def test_write_and_read_bool_true(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_bool(True)
        transport.seek(0)
        assert protocol.read_bool() is True

    def test_write_and_read_bool_false(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_bool(False)
        transport.seek(0)
        assert protocol.read_bool() is False

    def test_write_and_read_string(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_string("Hello, World!")
        transport.seek(0)
        assert protocol.read_string() == "Hello, World!"

    def test_write_and_read_string_unicode(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_string("你好世界")
        transport.seek(0)
        assert protocol.read_string() == "你好世界"

    def test_write_and_read_binary(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        data = b"\x00\x01\x02\x03\xff"
        protocol.write_binary(data)
        transport.seek(0)
        assert protocol.read_binary() == data

    def test_write_and_read_message_begin(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_message_begin("testMethod", 1, 42)
        transport.seek(0)
        msg = protocol.read_message_begin()
        assert msg["fname"] == "testMethod"
        assert msg["mtype"] == 1
        assert msg["rseqid"] == 42

    def test_write_and_read_field_begin_delta(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_struct_begin()
        protocol.write_field_begin("field1", ThriftType.I32, 1)
        protocol.write_i32(100)
        protocol.write_field_end()
        protocol.write_field_begin("field2", ThriftType.I32, 5)
        protocol.write_i32(200)
        protocol.write_field_end()
        protocol.write_field_stop()
        protocol.write_struct_end()

        transport.seek(0)
        protocol2 = TCompactProtocol(transport)
        protocol2.read_struct_begin()
        f1 = protocol2.read_field_begin()
        assert f1["ftype"] == ThriftType.I32
        assert f1["fid"] == 1
        assert protocol2.read_i32() == 100
        protocol2.read_field_end()

        f2 = protocol2.read_field_begin()
        assert f2["ftype"] == ThriftType.I32
        assert f2["fid"] == 5
        assert protocol2.read_i32() == 200

    def test_write_and_read_bool_in_field(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_struct_begin()
        protocol.write_field_begin("boolField", ThriftType.BOOL, 1)
        protocol.write_bool(True)
        protocol.write_field_end()
        protocol.write_field_stop()
        protocol.write_struct_end()

        transport.seek(0)
        protocol2 = TCompactProtocol(transport)
        protocol2.read_struct_begin()
        field = protocol2.read_field_begin()
        assert field["ftype"] == ThriftType.BOOL
        assert field["fid"] == 1
        assert protocol2.read_bool() is True

    def test_write_and_read_map_begin(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_map_begin(ThriftType.STRING, ThriftType.I32, 3)
        transport.seek(0)
        map_info = protocol.read_map_begin()
        assert map_info["ktype"] == ThriftType.STRING
        assert map_info["vtype"] == ThriftType.I32
        assert map_info["size"] == 3

    def test_write_and_read_empty_map(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_map_begin(ThriftType.STRING, ThriftType.I32, 0)
        transport.seek(0)
        map_info = protocol.read_map_begin()
        assert map_info["size"] == 0

    def test_write_and_read_list_begin_small(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_list_begin(ThriftType.I64, 5)
        transport.seek(0)
        list_info = protocol.read_list_begin()
        assert list_info["etype"] == ThriftType.I64
        assert list_info["size"] == 5

    def test_write_and_read_list_begin_large(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_list_begin(ThriftType.I32, 20)
        transport.seek(0)
        list_info = protocol.read_list_begin()
        assert list_info["etype"] == ThriftType.I32
        assert list_info["size"] == 20

    def test_write_and_read_set_begin(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_set_begin(ThriftType.BOOL, 2)
        transport.seek(0)
        set_info = protocol.read_set_begin()
        assert set_info["etype"] == ThriftType.BOOL
        assert set_info["size"] == 2

    def test_zigzag_encoding(self):
        protocol = TCompactProtocol(BytesIO())
        assert protocol._to_zigzag(0) == 0
        assert protocol._to_zigzag(-1) == 1
        assert protocol._to_zigzag(1) == 2
        assert protocol._to_zigzag(-2) == 3
        assert protocol._to_zigzag(2) == 4

    def test_zigzag_decoding(self):
        protocol = TCompactProtocol(BytesIO())
        assert protocol._from_zigzag(0) == 0
        assert protocol._from_zigzag(1) == -1
        assert protocol._from_zigzag(2) == 1
        assert protocol._from_zigzag(3) == -2
        assert protocol._from_zigzag(4) == 2

    def test_varint_read_write(self):
        for value in [0, 1, 127, 128, 255, 16383, 16384, 2097151, 2097152]:
            transport = BytesIO()
            protocol = TCompactProtocol(transport)
            protocol._write_varint(value)
            transport.seek(0)
            assert protocol._read_varint() == value

    def test_skip_types(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_i32(12345)
        protocol.write_string("test")
        protocol.write_double(3.14)
        transport.seek(0)

        protocol2 = TCompactProtocol(transport)
        protocol2.skip(ThriftType.I32)
        protocol2.skip(ThriftType.STRING)
        protocol2.skip(ThriftType.DOUBLE)
        assert transport.read() == b""

    def test_read_message_begin_bad_protocol_raises(self):
        transport = BytesIO(b"\x00\x21\x00")
        protocol = TCompactProtocol(transport)
        with pytest.raises(Exception, match="Bad protocol id"):
            protocol.read_message_begin()

    def test_read_message_begin_bad_version_raises(self):
        transport = BytesIO(b"\x82\x00\x00")
        protocol = TCompactProtocol(transport)
        with pytest.raises(Exception, match="Bad version"):
            protocol.read_message_begin()

    def test_read_byte_eof_raises(self):
        transport = BytesIO(b"")
        protocol = TCompactProtocol(transport)
        with pytest.raises(Exception, match="Unexpected end of data"):
            protocol.read_byte()


class TestTBinaryProtocolSkip:
    """Tests for TBinaryProtocol skip method."""

    def test_skip_byte(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_byte(42)
        transport.seek(0)
        protocol.skip(ThriftType.BYTE)
        assert transport.read() == b""

    def test_skip_i16(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_i16(12345)
        transport.seek(0)
        protocol.skip(ThriftType.I16)
        assert transport.read() == b""

    def test_skip_i64(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_i64(123456789)
        transport.seek(0)
        protocol.skip(ThriftType.I64)
        assert transport.read() == b""

    def test_skip_double(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_double(3.14)
        transport.seek(0)
        protocol.skip(ThriftType.DOUBLE)
        assert transport.read() == b""

    def test_skip_struct(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        # Write a struct with one field
        protocol.write_field_begin("test", ThriftType.I32, 1)
        protocol.write_i32(100)
        protocol.write_field_end()
        protocol.write_field_stop()
        transport.seek(0)
        protocol.skip(ThriftType.STRUCT)
        assert transport.read() == b""

    def test_skip_map(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_map_begin(ThriftType.STRING, ThriftType.I32, 2)
        protocol.write_string("key1")
        protocol.write_i32(1)
        protocol.write_string("key2")
        protocol.write_i32(2)
        protocol.write_map_end()
        transport.seek(0)
        protocol.skip(ThriftType.MAP)
        assert transport.read() == b""

    def test_skip_list(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_list_begin(ThriftType.I32, 3)
        protocol.write_i32(1)
        protocol.write_i32(2)
        protocol.write_i32(3)
        protocol.write_list_end()
        transport.seek(0)
        protocol.skip(ThriftType.LIST)
        assert transport.read() == b""

    def test_skip_set(self):
        transport = BytesIO()
        protocol = TBinaryProtocol(transport)
        protocol.write_set_begin(ThriftType.BOOL, 2)
        protocol.write_bool(True)
        protocol.write_bool(False)
        protocol.write_set_end()
        transport.seek(0)
        protocol.skip(ThriftType.SET)
        assert transport.read() == b""


class TestTCompactProtocolSkip:
    """Tests for TCompactProtocol skip method."""

    def test_skip_byte(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_byte(42)
        transport.seek(0)
        protocol.skip(ThriftType.BYTE)
        assert transport.read() == b""

    def test_skip_i16(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_i16(12345)
        transport.seek(0)
        protocol.skip(ThriftType.I16)
        assert transport.read() == b""

    def test_skip_i64(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_i64(123456789)
        transport.seek(0)
        protocol.skip(ThriftType.I64)
        assert transport.read() == b""

    def test_skip_double(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_double(3.14)
        transport.seek(0)
        protocol.skip(ThriftType.DOUBLE)
        assert transport.read() == b""

    def test_skip_struct(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_struct_begin()
        protocol.write_field_begin("test", ThriftType.I32, 1)
        protocol.write_i32(100)
        protocol.write_field_end()
        protocol.write_field_stop()
        protocol.write_struct_end()
        transport.seek(0)
        protocol.skip(ThriftType.STRUCT)
        assert transport.read() == b""

    def test_skip_map(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_map_begin(ThriftType.STRING, ThriftType.I32, 2)
        protocol.write_string("key1")
        protocol.write_i32(1)
        protocol.write_string("key2")
        protocol.write_i32(2)
        protocol.write_map_end()
        transport.seek(0)
        protocol.skip(ThriftType.MAP)
        assert transport.read() == b""

    def test_skip_list(self):
        transport = BytesIO()
        protocol = TCompactProtocol(transport)
        protocol.write_list_begin(ThriftType.I32, 3)
        protocol.write_i32(1)
        protocol.write_i32(2)
        protocol.write_i32(3)
        protocol.write_list_end()
        transport.seek(0)
        protocol.skip(ThriftType.LIST)
        assert transport.read() == b""


class TestGenHeader:
    """Tests for header generation functions."""

    def test_gen_header_v3(self):
        header = gen_header_v3("test")
        assert header.startswith(bytes([0x80, 0x01, 0x00, 0x01]))
        assert b"test" in header

    def test_gen_header_v4(self):
        header = gen_header_v4("test")
        assert header.startswith(bytes([0x82, 0x21, 0x00]))
        assert b"test" in header

    def test_gen_header_v3_long_name_raises(self):
        long_name = "a" * 256
        with pytest.raises(ValueError, match="name too long"):
            gen_header_v3(long_name)

    def test_gen_header_v4_long_name_raises(self):
        long_name = "a" * 256
        with pytest.raises(ValueError, match="name too long"):
            gen_header_v4(long_name)

    def test_protocols_mapping(self):
        assert PROTOCOLS[3] == TBinaryProtocol
        assert PROTOCOLS[4] == TCompactProtocol

    def test_gen_header_mapping(self):
        assert GEN_HEADER[3] == gen_header_v3
        assert GEN_HEADER[4] == gen_header_v4
