"""Tests for linepy/thrift/read.py and write.py."""

import pytest

from src.linepy.thrift.read import (
    big_int,
    is_binary,
    read_thrift,
    read_thrift_struct,
)
from src.linepy.thrift.types import ThriftType
from src.linepy.thrift.write import write_struct, write_thrift


class TestIsBinary:
    """Tests for is_binary function."""

    def test_utf8_string_returns_false(self):
        assert is_binary(b"Hello, World!") is False

    def test_utf8_unicode_returns_false(self):
        assert is_binary("你好世界".encode("utf-8")) is False

    def test_binary_data_returns_true(self):
        assert is_binary(b"\xff\xfe\x00\x01") is True

    def test_invalid_utf8_returns_true(self):
        assert is_binary(b"\x80\x81\x82") is True


class TestBigInt:
    """Tests for big_int function."""

    def test_positive_number(self):
        data = b"\x00\x00\x00\x01"
        assert big_int(data) == 1

    def test_negative_number(self):
        data = b"\xff\xff\xff\xff"
        assert big_int(data) == -1

    def test_large_positive(self):
        data = b"\x7f\xff\xff\xff"
        assert big_int(data) == 2147483647

    def test_large_negative(self):
        data = b"\x80\x00\x00\x00"
        assert big_int(data) == -2147483648


class TestWriteAndReadThrift:
    """Tests for write_thrift and read_thrift roundtrip."""

    def test_simple_struct_compact(self):
        data = [
            (ThriftType.I32, 1, 42),
            (ThriftType.STRING, 2, "hello"),
        ]
        serialized = write_thrift(data, "testMethod", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed.method == "testMethod"
        assert parsed[1] == 42
        assert parsed[2] == "hello"

    def test_simple_struct_binary(self):
        data = [
            (ThriftType.I32, 1, 42),
            (ThriftType.STRING, 2, "hello"),
        ]
        serialized = write_thrift(data, "testMethod", protocol_key=3)
        parsed = read_thrift(serialized, protocol_key=3)
        assert parsed.method == "testMethod"
        assert parsed[1] == 42
        assert parsed[2] == "hello"

    def test_nested_struct(self):
        inner = [
            (ThriftType.I32, 1, 100),
            (ThriftType.STRING, 2, "inner"),
        ]
        data = [
            (ThriftType.I32, 1, 42),
            (ThriftType.STRUCT, 2, inner),
        ]
        serialized = write_thrift(data, "nested", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == 42
        assert parsed[2][1] == 100
        assert parsed[2][2] == "inner"

    def test_list_of_i32(self):
        data = [
            (ThriftType.LIST, 1, (ThriftType.I32, [1, 2, 3, 4, 5])),
        ]
        serialized = write_thrift(data, "listTest", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == [1, 2, 3, 4, 5]

    def test_list_of_strings(self):
        data = [
            (ThriftType.LIST, 1, (ThriftType.STRING, ["a", "b", "c"])),
        ]
        serialized = write_thrift(data, "listTest", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == ["a", "b", "c"]

    def test_map_string_to_i32(self):
        data = [
            (
                ThriftType.MAP,
                1,
                (ThriftType.STRING, ThriftType.I32, {"key1": 1, "key2": 2}),
            ),
        ]
        serialized = write_thrift(data, "mapTest", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == {"key1": 1, "key2": 2}

    def test_set_of_i32(self):
        data = [
            (ThriftType.SET, 1, (ThriftType.I32, [10, 20, 30])),
        ]
        serialized = write_thrift(data, "setTest", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == [10, 20, 30]

    def test_bool_values(self):
        data = [
            (ThriftType.BOOL, 1, True),
            (ThriftType.BOOL, 2, False),
        ]
        serialized = write_thrift(data, "boolTest", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] is True
        assert parsed[2] is False

    def test_double_value(self):
        data = [
            (ThriftType.DOUBLE, 1, 3.14159),
        ]
        serialized = write_thrift(data, "doubleTest", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == pytest.approx(3.14159)

    def test_i64_value(self):
        data = [
            (ThriftType.I64, 1, 9223372036854775807),
        ]
        serialized = write_thrift(data, "i64Test", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == 9223372036854775807

    def test_i16_value(self):
        data = [
            (ThriftType.I16, 1, 32767),
        ]
        serialized = write_thrift(data, "i16Test", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == 32767

    def test_byte_value(self):
        data = [
            (ThriftType.BYTE, 1, 127),
        ]
        serialized = write_thrift(data, "byteTest", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == 127

    def test_binary_value(self):
        data = [
            (ThriftType.STRING, 1, b"\x00\x01\x02\xff"),
        ]
        serialized = write_thrift(data, "binaryTest", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == b"\x00\x01\x02\xff"

    def test_empty_struct(self):
        data = []
        serialized = write_thrift(data, "emptyTest", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed.data == {}

    def test_none_items_skipped(self):
        data = [
            None,
            (ThriftType.I32, 1, 42),
            None,
        ]
        serialized = write_thrift(data, "noneTest", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == 42


class TestWriteAndReadThriftStruct:
    """Tests for write_struct and read_thrift_struct (no header)."""

    def test_simple_struct(self):
        data = [
            (ThriftType.I32, 1, 42),
            (ThriftType.STRING, 2, "test"),
        ]
        serialized = write_struct(data, protocol_key=4)
        parsed = read_thrift_struct(serialized, protocol_key=4)
        assert parsed[1] == 42
        assert parsed[2] == "test"

    def test_simple_struct_binary(self):
        data = [
            (ThriftType.I32, 1, 42),
            (ThriftType.STRING, 2, "test"),
        ]
        serialized = write_struct(data, protocol_key=3)
        parsed = read_thrift_struct(serialized, protocol_key=3)
        assert parsed[1] == 42
        assert parsed[2] == "test"

    def test_empty_struct(self):
        data = []
        serialized = write_struct(data, protocol_key=4)
        assert serialized == b""


class TestWriteTypeErrors:
    """Tests for write type validation."""

    def test_string_wrong_type_raises(self):
        data = [
            (ThriftType.STRING, 1, 123),
        ]
        with pytest.raises(TypeError, match="value is not string"):
            write_thrift(data, "test", protocol_key=4)

    def test_double_wrong_type_raises(self):
        data = [
            (ThriftType.DOUBLE, 1, "not a number"),
        ]
        with pytest.raises(TypeError, match="value is not number"):
            write_thrift(data, "test", protocol_key=4)

    def test_i64_wrong_type_raises(self):
        data = [
            (ThriftType.I64, 1, "not a number"),
        ]
        with pytest.raises(TypeError, match="value is not number"):
            write_thrift(data, "test", protocol_key=4)

    def test_i32_wrong_type_raises(self):
        data = [
            (ThriftType.I32, 1, "not a number"),
        ]
        with pytest.raises(TypeError, match="value is not number"):
            write_thrift(data, "test", protocol_key=4)

    def test_i16_wrong_type_raises(self):
        data = [
            (ThriftType.I16, 1, "not a number"),
        ]
        with pytest.raises(TypeError, match="value is not number"):
            write_thrift(data, "test", protocol_key=4)

    def test_byte_wrong_type_raises(self):
        data = [
            (ThriftType.BYTE, 1, "not a number"),
        ]
        with pytest.raises(TypeError, match="value is not number"):
            write_thrift(data, "test", protocol_key=4)

    def test_struct_wrong_type_raises(self):
        data = [
            (ThriftType.STRUCT, 1, "not a struct"),
        ]
        with pytest.raises(TypeError, match="value is not struct"):
            write_thrift(data, "test", protocol_key=4)

    def test_none_value_skipped(self):
        data = [
            (ThriftType.I32, 1, None),
            (ThriftType.I32, 2, 42),
        ]
        serialized = write_thrift(data, "test", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] is None
        assert parsed[2] == 42


class TestListMapSetEdgeCases:
    """Tests for edge cases in list, map, and set handling."""

    def test_empty_list(self):
        data = [
            (ThriftType.LIST, 1, (ThriftType.I32, [])),
        ]
        serialized = write_thrift(data, "test", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == []

    def test_empty_map(self):
        data = [
            (ThriftType.MAP, 1, (ThriftType.STRING, ThriftType.I32, {})),
        ]
        serialized = write_thrift(data, "test", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == {}

    def test_empty_set(self):
        data = [
            (ThriftType.SET, 1, (ThriftType.I32, [])),
        ]
        serialized = write_thrift(data, "test", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] == []

    def test_list_of_structs(self):
        struct1 = [(ThriftType.I32, 1, 100)]
        struct2 = [(ThriftType.I32, 1, 200)]
        data = [
            (ThriftType.LIST, 1, (ThriftType.STRUCT, [struct1, struct2])),
        ]
        serialized = write_thrift(data, "test", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert len(parsed[1]) == 2
        assert parsed[1][0][1] == 100
        assert parsed[1][1][1] == 200

    def test_list_with_none_data_skipped(self):
        data = [
            (ThriftType.LIST, 1, (ThriftType.I32, None)),
        ]
        serialized = write_thrift(data, "test", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] is None

    def test_map_with_none_data_skipped(self):
        data = [
            (ThriftType.MAP, 1, (ThriftType.STRING, ThriftType.I32, None)),
        ]
        serialized = write_thrift(data, "test", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] is None

    def test_set_with_none_data_skipped(self):
        data = [
            (ThriftType.SET, 1, (ThriftType.I32, None)),
        ]
        serialized = write_thrift(data, "test", protocol_key=4)
        parsed = read_thrift(serialized, protocol_key=4)
        assert parsed[1] is None
