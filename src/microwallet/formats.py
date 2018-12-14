#!/usr/bin/env python3

import os
import sys

import construct as c


def Optional(subcon):
    select = c.Select(subcon, c.Pass)
    select.flagbuildnone = True
    return select


CompactUintStruct = c.Struct(
    "base" / c.Int8ul,
    "ext" / c.Switch(c.this.base, {0xFD: c.Int16ul, 0xFE: c.Int32ul, 0xFF: c.Int64ul}),
)


class CompactUintAdapter(c.Adapter):
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
BitcoinBytes = c.Prefixed(CompactUint, c.GreedyBytes)

TxInput = c.Struct(
    "tx" / c.Bytes(32),
    "index" / c.Int32ul,
    "script" / BitcoinBytes,
    "sequence" / c.Int32ul,
)

TxOutput = c.Struct(
    "value" / c.Int64ul, "pk_script" / BitcoinBytes
)

TxInputWitness = c.PrefixedArray(CompactUint, BitcoinBytes)

Transaction = c.Struct(
    "version" / c.Int32ul,
    "segwit" / ConstFlag(b"\x00\x01"),
    "inputs" / c.PrefixedArray(CompactUint, TxInput),
    "outputs" / c.PrefixedArray(CompactUint, TxOutput),
    "witness" / c.If(c.this.segwit, TxInputWitness[c.len_(c.this.inputs)]),
    "lock_time" / c.Int32ul,
    c.Terminated,
)
