import struct

import construct as c


def Optional(subcon):
    """Custom version of Optional which fixes construct issue #760"""
    select = c.Select(subcon, c.Pass)
    select.flagbuildnone = True
    return select


CompactUintStruct = c.Struct(
    "base" / c.Int8ul,
    "ext" / c.Switch(c.this.base, {0xFD: c.Int16ul, 0xFE: c.Int32ul, 0xFF: c.Int64ul}),
)
"""Struct for Bitcoin's Compact uint / varint"""


class CompactUintAdapter(c.Adapter):
    """Adapter for Bitcoin's Compact uint / varint"""

    def _encode(self, obj, context, path):
        if obj < 0xFD:
            return {"base": obj, "ext": None}
        if obj < 2 ** 16:
            return {"base": 0xFD, "ext": obj}
        if obj < 2 ** 32:
            return {"base": 0xFE, "ext": obj}
        if obj < 2 ** 64:
            return {"base": 0xFF, "ext": obj}
        raise ValueError("Value too big for compact uint")

    def _decode(self, obj, context, path):
        return obj["ext"] or obj["base"]


class ConstFlag(c.Adapter):
    """Constant value that might or might not be present.

    When parsing, if the appropriate value is found, it is consumed and
    this field set to True.
    When building, if True, the constant is inserted, otherwise it is omitted.
    """

    def __init__(self, const):
        self.const = const
        super().__init__(
            c.IfThenElse(
                c.this._building,
                c.Select(c.Bytes(len(self.const)), c.Pass),
                Optional(c.Const(const)),
            )
        )

    def _encode(self, obj, context, path):
        return self.const if obj else None

    def _decode(self, obj, context, path):
        return obj is not None


CompactUint = CompactUintAdapter(CompactUintStruct)
"""Bitcoin Compact uint construct.

Encodes an int as either:
- a single byte the value is smaller than 253 (0xFD)
- 0xFD + uint16 if the value fits into uint16
- 0xFE + uint32 if the value fits into uint32
- 0xFF + uint64 if the value is bigger.
"""


def op_push(data):
    n = len(data)
    if n > 0xFFFF_FFFF:
        raise ValueError("data too big for OP_PUSH")
    if n < 0x4C:
        return struct.pack("<B", n)
    elif n < 0xFF:
        return struct.pack("<BB", 0x4C, n)
    elif n < 0xFFFF:
        return struct.pack("<BS", 0x4D, n)
    else:
        return struct.pack("<BL", 0x4E, n)
