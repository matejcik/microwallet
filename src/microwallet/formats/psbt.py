from collections import namedtuple
import io
import struct

import construct as c

from . import CompactUint
from .transaction import Transaction, TxOutput


class PsbtError(Exception):
    pass


def _read_or_raise(reader, n):
    res = reader.read(n)
    if len(res) < n:
        raise IOError("Not enough data read")
    return res


def read_compact_uint(reader):
    leader = _read_or_raise(reader, 1)[0]
    if leader < 0xFD:
        return leader

    num_bytes = 2 ** (leader - 0xFC)
    value_bytes = _read_or_raise(reader, num_bytes)
    return int.from_bytes(value_bytes, "little")


def write_compact_uint(writer, value):
    if value < 0xFD:
        out = struct.pack("<B", value)
    elif value <= 0xFFFF:
        out = struct.pack("<BH", 0xFD, value)
    elif value <= 0xFFFF_FFFF:
        out = struct.pack("<BL", 0xFE, value)
    elif value <= 0xFFFF_FFFF_FFFF_FFFF:
        out = struct.pack("<BQ", 0xFF, value)
    else:
        raise PsbtError("Value too big for compact uint")
    writer.write(out)


def read_keyvalues(reader):
    while True:
        keylen = read_compact_uint(reader)
        if keylen == 0:
            break
        keybytes = _read_or_raise(reader, keylen)
        b = io.BytesIO(keybytes)
        key = read_compact_uint(b)
        keydata = b.read()
        valuelen = read_compact_uint(reader)
        valuebytes = _read_or_raise(reader, valuelen)
        yield key, keydata, valuebytes


def write_keyvalue(writer, key, keydata, value):
    if keydata is None:
        keydata = b""
    b = io.BytesIO()
    write_compact_uint(b, key)
    b.write(keydata)
    key_bytes = b.getvalue()

    write_compact_uint(writer, len(key_bytes))
    writer.write(key_bytes)
    write_compact_uint(writer, len(value))
    writer.write(value)


# fmt: off
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
    def _decode_field(field_type, field_bytes):
        if field_type is None:
            return None
        if field_type is bytes:
            return field_bytes
        if isinstance(field_type, c.Construct):
            return field_type.parse(field_bytes)
        else:
            raise PsbtError("Unknown field type")

    @staticmethod
    def _encode_field(field_type, field_value):
        if field_type is bytes:
            return field_value
        if isinstance(field_type, c.Construct):
            return field_type.build(field_value)
        else:
            raise PsbtError("Unknown field type")

    @classmethod
    def read(cls, reader):
        psbt = cls()
        seen_keys = set()
        for key, keydata, value in read_keyvalues(reader):
            if (key, keydata) in seen_keys:
                raise PsbtError(f"Duplicate key type 0x{key:02x}")
            seen_keys.add((key, keydata))

            if key not in cls.FIELDS:
                raise PsbtError(f"Unknown field type 0x{key:02x}")
            name, keydata_type, value_type = cls.FIELDS[key]
            if keydata_type is None and keydata:
                raise PsbtError(f"Key data not allowed on '{name}'")
            if keydata_type is not None and not keydata:
                raise PsbtError(f"Key data missing on '{name}'")

            parsed_key = cls._decode_field(keydata_type, keydata)
            parsed_value = cls._decode_field(value_type, value)
            if keydata_type:
                getattr(psbt, name)[parsed_key] = parsed_value
            else:
                setattr(psbt, name, parsed_value)
        return psbt

    def write(self, writer):
        for key, (name, keydata_type, value_type) in self.FIELDS.items():
            if keydata_type is None:
                value = getattr(self, name)
                if value is None:
                    continue
                write_keyvalue(writer, key, None, self._encode_field(value_type, value))
            else:
                values = getattr(self, name)
                if values == {}:
                    continue
                for keydata, value in values.items():
                    write_keyvalue(
                        writer,
                        key,
                        self._encode_field(keydata_type, keydata),
                        self._encode_field(value_type, value),
                    )
        writer.write(b"\0")


class PsbtGlobalType(PsbtMapType):
    FIELDS = {0x00: ("transaction", None, Transaction)}

    def __init__(self, **kwargs):
        self.transaction = None
        super().__init__(**kwargs)


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

    def __init__(self, **kwargs):
        self.non_witnes_utxo = None
        self.witness_utxo = None
        self.signature = {}
        self.sighash_type = None
        self.redeem_script = None
        self.witness_script = None
        self.bip32_path = {}
        self.script_sig = None
        self.witness = None
        super().__init__(**kwargs)


class PsbtOutputType(PsbtMapType):
    FIELDS = {
        0x00: ("redeem_script", None, bytes),
        0x01: ("witness", None, bytes),
        0x02: ("bip32_path", bytes, Bip32Field),
    }

    def __init__(self, **kwargs):
        self.redeem_script = None
        self.witness = None
        self.bip32_path = {}
        super().__init__(**kwargs)


def read_psbt(psbt_bytes):
    reader = io.BytesIO(psbt_bytes)
    header = reader.read(5)
    if header != b"psbt\xff":
        raise PsbtError("Invalid PSBT header")

    try:
        tx_entry = PsbtGlobalType.read(reader)
        tx = tx_entry.transaction
        inputs = []
        outputs = []
        inputs = [PsbtInputType.read(reader) for _ in tx.inputs]
        outputs = [PsbtOutputType.read(reader) for _ in tx.outputs]
        return tx, inputs, outputs
    except IOError as e:
        raise PsbtError("Not enough data in PSBT") from e


def write_psbt(tx, inputs, outputs):
    writer = io.BytesIO()
    writer.write(b"psbt\xff")
    tx_entry = PsbtGlobalType(transaction=tx)
    tx_entry.write(writer)
    for inp in inputs:
        inp.write(writer)
    for out in outputs:
        out.write(writer)
    return writer.getvalue()
