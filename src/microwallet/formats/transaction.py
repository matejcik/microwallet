import construct as c

from . import Optional, ConstFlag, CompactUint

BitcoinBytes = c.Prefixed(CompactUint, c.GreedyBytes)
"""Bitcoin string of bytes.

Encoded as a CompactUint length followed by that many bytes.
"""

TxInput = c.Struct(
    "tx" / c.Bytes(32),
    "index" / c.Int32ul,
    "script_sig" / BitcoinBytes,
    "sequence" / c.Int32ul,
)
"""Transaction input."""

TxOutput = c.Struct("value" / c.Int64ul, "script_pubkey" / BitcoinBytes)
"""Transaction output."""

TxInputWitness = c.PrefixedArray(CompactUint, BitcoinBytes)
"""Array of witness records."""

Transaction = c.Struct(
    "version" / c.Int32ul,
    "segwit" / ConstFlag(b"\x00\x01"),
    "inputs" / c.PrefixedArray(CompactUint, TxInput),
    "outputs" / c.PrefixedArray(CompactUint, TxOutput),
    "witness" / c.If(c.this.segwit, TxInputWitness[c.len_(c.this.inputs)]),
    "lock_time" / c.Int32ul,
    c.Terminated,
)
"""Bitcoin transaction.

If the `segwit` flag is present (which would otherwise mean 0 inputs, 1 output),
we expect a `witness` field with entries corresponding to each input.
"""
