import pytest
import construct as c

from microwallet import formats


def test_compact_uint_build():
    assert formats.CompactUint.build(0) == b"\0"
    assert formats.CompactUint.build(252) == b"\xfc"
    assert formats.CompactUint.build(253) == b"\xfd\xfd\x00"
    assert formats.CompactUint.build(2 ** 32 - 1) == b"\xfe\xff\xff\xff\xff"
    assert formats.CompactUint.build(2 ** 32) == b"\xff\x00\x00\x00\x00\x01\x00\x00\x00"


def test_compact_uint_parse():
    assert formats.CompactUint.parse(b"\0") == 0
    assert formats.CompactUint.parse(b"\xfc") == 252
    assert formats.CompactUint.parse(b"\xfd\xfd\x00") == 253
    assert formats.CompactUint.parse(b"\xfe\xff\xff\xff\xff") == 2 ** 32 - 1
    assert formats.CompactUint.parse(b"\xff\x00\x00\x00\x00\x01\x00\x00\x00") == 2 ** 32

    with pytest.raises(c.StreamError):
        formats.CompactUint.parse(b"\xfd")


def test_const_flag():
    Flag = formats.ConstFlag(b"hello")
    assert Flag.build(False) == b""
    assert Flag.build(True) == b"hello"
    assert Flag.parse(b"hello") is True
    assert Flag.parse(b"hello world") is True
    assert Flag.parse(b"") is False
    assert Flag.parse(b"goodbye") is False
