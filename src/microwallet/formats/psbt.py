from collections import namedtuple

import construct as c

from . import CompactUint
from .transaction import Transaction, TxOutput


class PsbtError(Exception):
    pass


# fmt: off
PsbtKeyValue = c.Struct(
    "key" / c.Prefixed(CompactUint, c.Struct(
        "type" / CompactUint,
        "data" / c.GreedyBytes
    )),
    "value" / c.Prefixed(CompactUint, c.GreedyBytes),
)

PsbtSequence = c.FocusedSeq("content",
    "content" / c.GreedyRange(
        c.FocusedSeq("keyvalue",
            "terminator" / c.Peek(c.Byte),
            c.StopIf(c.this.terminator == 0),
            "keyvalue" / PsbtKeyValue,
        )
    ),
    c.Const(b"\0"),
)

PsbtBase = c.Struct(
    "magic" / c.Const(b"psbt"),
    c.Const(b"\xff"),
    "sequences" / c.GreedyRange(PsbtSequence),
)

Bip32Field = c.Struct(
    "fingerprint" / c.Int32ul,
    "address_n" / c.GreedyRange(c.Int32ul),
)
# fmt: on


class PsbtMapType:
    FIELDS = {}

    def __init__(self, **kwargs):
        for name, keytype, _ in self.FIELDS.values():
            if name in kwargs:
                value = kwargs[name]
                if keytype is not None and not isinstance(value, dict):
                    raise PsbtError("must supply dict for multi-key fields")
                setattr(self, name, value)
            elif keytype is None:
                setattr(self, name, None)
            else:
                setattr(self, name, {})

    def __repr__(self):
        d = {}
        for key, value in self.__dict__.items():
            if value is None or value == {}:
                continue
            d[key] = value
        return "<%s: %s>" % (self.__class__.__name__, d)

    @staticmethod
    def _decode_field(name, field_type, field_bytes):
        if field_type is None:
            if field_bytes:
                raise PsbtError(f"Field '{name}' has non-empty key data.")
            return None
        if field_type is bytes:
            return field_bytes
        if isinstance(field_type, c.Construct):
            return field_type.parse(field_bytes)
        else:
            raise PsbtError("Unknown field type")

    @classmethod
    def from_sequence(cls, sequence):
        psbt = cls()
        for kv in sequence:
            key = kv["key"]["type"]
            keydata = kv["key"]["data"]
            value = kv["value"]
            if key not in cls.FIELDS:
                raise PsbtError(f"Unknown field type 0x{key:02x}")
            name, key_type, value_type = cls.FIELDS[key]
            parsed_key = cls._decode_field(name, key_type, keydata)
            parsed_value = cls._decode_field(name, value_type, value)
            if key_type:
                getattr(psbt, name)[parsed_key] = parsed_value
            else:
                setattr(psbt, name, parsed_value)
        return psbt


class PsbtGlobalType(PsbtMapType):
    FIELDS = {0x00: ("transaction", None, Transaction)}


class PsbtInputType(PsbtMapType):
    FIELDS = {
        0x00: ("non_witness_utxo", None, Transaction),
        0x01: ("witness_utxo", None, TxOutput),
        0x02: ("signature", bytes, bytes),
        0x03: ("sighash_type", None, c.Int32ul),
        0x04: ("redeem_script", None, bytes),
        0x05: ("witness_script", None, bytes),
        0x06: ("bip32_path", bytes, Bip32Field),
        0x07: ("script_sig", None, bytes),
        0x08: ("witness", None, bytes),
    }


class PsbtOutputType(PsbtMapType):
    FIELDS = {
        0x00: ("redeem_script", None, bytes),
        0x01: ("witness", None, bytes),
        0x02: ("bip32_path", bytes, Bip32Field),
    }


def ensure(what, error):
    if not what:
        raise PsbtError(error)


def _check_map(sequence):
    keyset = {(e.key.type, e.key.data) for e in sequence}
    ensure(len(keyset) == len(sequence), "Duplicate keys are not allowed in PSBT")
    # for whatever reason


def parse_psbt(psbt_bytes):
    psbt = PsbtBase.parse(psbt_bytes)
    ensure(len(psbt.sequences) >= 3, "Not enough data in PSBT")
    global_map = psbt.sequences[0]
    tx_entry = PsbtGlobalType.from_sequence(global_map)
    tx = tx_entry.transaction

    try:
        input_maps = psbt.sequences[1 : len(tx.inputs) + 1]
        output_ofs = 1 + len(input_maps)
        output_maps = psbt.sequences[output_ofs : output_ofs + len(tx.outputs)]
        ensure(
            len(input_maps) + len(output_maps) + 1 == len(psbt.sequences),
            "Unmatched maps in PSBT",
        )
    except IndexError as e:
        raise PsbtError("Not enough maps in PSBT") from e

    inputs = [PsbtInputType.from_sequence(s) for s in input_maps]
    outputs = [PsbtOutputType.from_sequence(s) for s in output_maps]
    return tx, inputs, outputs
