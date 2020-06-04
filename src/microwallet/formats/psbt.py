import warnings

import construct as c

from . import CompactUint, Optional
from .transaction import Transaction, TxOutput


PSBT_PROPRIETARY_BYTE = 0xFC


class PsbtError(Exception):
    pass


# fmt: off
PsbtKeyValue = c.Struct(
    "key" / c.Prefixed(CompactUint, c.Struct(
        "type" / CompactUint,
        "data" / Optional(c.GreedyBytes),
    )),
    "value" / c.Prefixed(CompactUint, c.GreedyBytes),
)

PsbtProprietaryKey = c.Struct(
    "prefix" / c.CString("utf-8"),
    "subtype" / CompactUint,
    "data" / Optional(c.GreedyBytes),
)

PsbtSequence = c.FocusedSeq("content",
    "content" / c.GreedyRange(PsbtKeyValue),
    c.Const(b"\0"),
)

PsbtEnvelope = c.FocusedSeq("sequences",
    "magic" / c.Const(b"psbt\xff"),
    "sequences" / c.GreedyRange(PsbtSequence),
    c.Terminated,
)


Bip32Field = c.Struct(
    "fingerprint" / c.Bytes(4),
    "address_n" / c.GreedyRange(c.Int32ul),
)
# fmt: on


class PsbtMapType:
    FIELDS = {}

    def __init__(self, **kwargs):
        self._proprietary = {}
        self._unknown = {}
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

    def __bool__(self):
        """Return False if no fields are set, True otherwise"""
        return any(v is not None and v != {} for v in self.__dict__.values())

    @staticmethod
    def _decode_field(field_type, field_bytes):
        if field_type is None:
            return None
        if field_type is bytes:
            return field_bytes
        if field_type is str:
            return field_bytes.decode()
        if isinstance(field_type, c.Construct):
            return field_type.parse(field_bytes)
        else:
            raise PsbtError("Unknown field type")

    @staticmethod
    def _encode_field(field_type, field_value):
        if field_type is bytes:
            return field_value
        if field_type is str:
            return field_value.encode()
        if isinstance(field_type, c.Construct):
            return field_type.build(field_value)
        else:
            raise PsbtError("Unknown field type")

    @classmethod
    def from_sequence(cls, sequence):
        psbt = cls()
        seen_keys = set()
        for v in sequence:
            key = v.key.type
            if (key, v.key.data) in seen_keys:
                raise PsbtError(f"Duplicate key type 0x{key:02x}")
            seen_keys.add((key, v.key.data))

            if key == PSBT_PROPRIETARY_BYTE:
                prop_key = PsbtProprietaryKey.parse(v.key.data)
                prop_dict = psbt._proprietary.setdefault(prop_key.prefix, {})
                prop_dict[prop_key.subtype, prop_key.data] = v.value
                continue

            if key not in cls.FIELDS:
                warnings.warn(f"Unknown field type 0x{key:02x}")
                psbt._unknown[key, v.key.data] = v.value
                continue

            name, keydata_type, value_type = cls.FIELDS[key]
            if keydata_type is None and v.key.data:
                raise PsbtError(f"Key data not allowed on '{name}'")
            if keydata_type is not None and not v.key.data:
                raise PsbtError(f"Key data missing on '{name}'")

            parsed_key = cls._decode_field(keydata_type, v.key.data)
            parsed_value = cls._decode_field(value_type, v.value)
            if keydata_type:
                getattr(psbt, name)[parsed_key] = parsed_value
            else:
                setattr(psbt, name, parsed_value)
        return psbt

    def to_sequence(self):
        sequence = []
        for key, (name, keydata_type, value_type) in self.FIELDS.items():
            if keydata_type is None:
                value = getattr(self, name)
                if value is None:
                    continue
                value_bytes = self._encode_field(value_type, value)
                v = dict(key=dict(type=key, data=None), value=value_bytes)
                sequence.append(v)
            else:
                values = getattr(self, name)
                if values == {}:
                    continue
                for keydata, value in values.items():
                    keydata_bytes = self._encode_field(keydata_type, keydata)
                    value_bytes = self._encode_field(value_type, value)
                    v = dict(key=dict(type=key, data=keydata_bytes), value=value_bytes)
                    sequence.append(v)
        for (key_type, key_data), value in self._unknown.items():
            v = dict(key=dict(type=key_type, data=key_data), value=value)
            sequence.append(v)
        for prefix, proprietary in self._proprietary.items():
            for (key_subtype, key_data), value in proprietary.items():
                data = PsbtProprietaryKey.build(
                    dict(prefix=prefix, subtype=key_subtype, data=key_data)
                )
                v = dict(key=dict(type=PSBT_PROPRIETARY_BYTE, data=data), value=value)
                sequence.append(v)
        return sequence


class PsbtGlobalType(PsbtMapType):
    FIELDS = {
        0x00: ("transaction", None, Transaction),
        0x01: ("global_xpub", None, bytes),
        0x02: ("version", None, c.Int32ul),
    }

    def __init__(self, **kwargs):
        self.transaction = None
        self.global_xpub = None
        self.version = None
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
        0x09: ("por_commitment", None, str),
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
    try:
        psbt = PsbtEnvelope.parse(psbt_bytes)
        if not psbt:
            raise PsbtError("Empty PSBT envelope")
        main = PsbtGlobalType.from_sequence(psbt[0])
        tx = main.transaction
        if len(psbt) != 1 + len(tx.inputs) + len(tx.outputs):
            raise PsbtError("PSBT length does not match embedded transaction")

        input_seqs = psbt[1 : 1 + len(tx.inputs)]
        output_seqs = psbt[1 + len(tx.inputs) :]
        inputs = [PsbtInputType.from_sequence(s) for s in input_seqs]
        outputs = [PsbtOutputType.from_sequence(s) for s in output_seqs]
        return main, inputs, outputs

    except c.ConstructError as e:
        raise PsbtError("Could not parse PBST") from e


def write_psbt(main, inputs, outputs):
    sequences = (
        [main.to_sequence()]
        + [inp.to_sequence() for inp in inputs]
        + [out.to_sequence() for out in outputs]
    )
    return PsbtEnvelope.build(sequences)
