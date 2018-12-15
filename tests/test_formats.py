import pytest
import construct as c

from microwallet.formats import CompactUint, ConstFlag


def test_compact_uint_build():
    assert CompactUint.build(0) == b"\0"
    assert CompactUint.build(252) == b"\xfc"
    assert CompactUint.build(253) == b"\xfd\xfd\x00"
    assert CompactUint.build(2 ** 32 - 1) == b"\xfe\xff\xff\xff\xff"
    assert CompactUint.build(2 ** 32) == b"\xff\x00\x00\x00\x00\x01\x00\x00\x00"


def test_compact_uint_parse():
    assert CompactUint.parse(b"\0") == 0
    assert CompactUint.parse(b"\xfc") == 252
    assert CompactUint.parse(b"\xfd\xfd\x00") == 253
    assert CompactUint.parse(b"\xfe\xff\xff\xff\xff") == 2 ** 32 - 1
    assert CompactUint.parse(b"\xff\x00\x00\x00\x00\x01\x00\x00\x00") == 2 ** 32

    with pytest.raises(c.StreamError):
        CompactUint.parse(b"\xfd")


def test_const_flag():
    Flag = ConstFlag(b"hello")
    assert Flag.build(False) == b""
    assert Flag.build(True) == b"hello"
    assert Flag.parse(b"hello") is True
    assert Flag.parse(b"hello world") is True
    assert Flag.parse(b"") is False
    assert Flag.parse(b"goodbye") is False
