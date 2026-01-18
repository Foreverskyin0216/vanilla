"""Tests for linepy/thrift/types.py."""

from src.linepy.thrift.types import ParsedThrift, ThriftType


class TestThriftType:
    """Tests for ThriftType enum."""

    def test_stop_value(self):
        assert ThriftType.STOP == 0

    def test_void_value(self):
        assert ThriftType.VOID == 1

    def test_bool_value(self):
        assert ThriftType.BOOL == 2

    def test_byte_value(self):
        assert ThriftType.BYTE == 3

    def test_i08_is_byte(self):
        assert ThriftType.I08 == ThriftType.BYTE

    def test_double_value(self):
        assert ThriftType.DOUBLE == 4

    def test_i16_value(self):
        assert ThriftType.I16 == 6

    def test_i32_value(self):
        assert ThriftType.I32 == 8

    def test_i64_value(self):
        assert ThriftType.I64 == 10

    def test_string_value(self):
        assert ThriftType.STRING == 11

    def test_utf7_is_string(self):
        assert ThriftType.UTF7 == ThriftType.STRING

    def test_struct_value(self):
        assert ThriftType.STRUCT == 12

    def test_map_value(self):
        assert ThriftType.MAP == 13

    def test_set_value(self):
        assert ThriftType.SET == 14

    def test_list_value(self):
        assert ThriftType.LIST == 15

    def test_utf8_value(self):
        assert ThriftType.UTF8 == 16

    def test_utf16_value(self):
        assert ThriftType.UTF16 == 17


class TestParsedThrift:
    """Tests for ParsedThrift class."""

    def test_init_with_data(self):
        data = {1: "value1", 2: 123}
        parsed = ParsedThrift(data)
        assert parsed.data == data

    def test_init_with_info(self):
        data = {1: "value1"}
        info = {"fname": "test_method", "mtype": 1, "rseqid": 42}
        parsed = ParsedThrift(data, info)
        assert parsed.method == "test_method"
        assert parsed.message_type == 1
        assert parsed.sequence_id == 42

    def test_init_without_info(self):
        data = {1: "value1"}
        parsed = ParsedThrift(data)
        assert parsed.method == ""
        assert parsed.message_type == 0
        assert parsed.sequence_id == 0

    def test_getitem(self):
        data = {1: "value1", 2: 123}
        parsed = ParsedThrift(data)
        assert parsed[1] == "value1"
        assert parsed[2] == 123
        assert parsed[3] is None

    def test_get_with_default(self):
        data = {1: "value1"}
        parsed = ParsedThrift(data)
        assert parsed.get(1) == "value1"
        assert parsed.get(2) is None
        assert parsed.get(2, "default") == "default"

    def test_method_property(self):
        data = {}
        info = {"fname": "getProfile"}
        parsed = ParsedThrift(data, info)
        assert parsed.method == "getProfile"

    def test_message_type_property(self):
        data = {}
        info = {"mtype": 2}
        parsed = ParsedThrift(data, info)
        assert parsed.message_type == 2

    def test_sequence_id_property(self):
        data = {}
        info = {"rseqid": 12345}
        parsed = ParsedThrift(data, info)
        assert parsed.sequence_id == 12345
