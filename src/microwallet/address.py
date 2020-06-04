import typing

import attr

from trezorlib.tools import b58check_decode, b58check_encode, hash_160

from .formats import bech32, op_push


SCRIPT_PREFIX_P2PKH = b"\x76\xA9\x14"
SCRIPT_SUFFIX_P2PKH = b"\x88\xAC"
SCRIPT_LENGTH_P2PKH = 25

SCRIPT_PREFIX_P2SH = b"\xA9\x14"
SCRIPT_SUFFIX_P2SH = b"\x87"
SCRIPT_LENGTH_P2SH = 23

SCRIPT_PREFIX_OP_RETURN = b"\x6A\x76"


@attr.s(auto_attribs=True)
class Address:
    path: typing.List[int]
    change: bool
    public_key: bytes
    str: str
    data: typing.Dict[str, typing.Any] = {}


def version_to_bytes(version):
    vlen = max(1, (version.bit_length() + 7) // 8)
    return version.to_bytes(vlen, "big")


def address_p2pkh(version, pubkey):
    assert pubkey[0] != 4, "uncompressed pubkey"
    prefix_bytes = version_to_bytes(version)
    pubkey_bytes = hash_160(pubkey)
    return b58check_encode(prefix_bytes + pubkey_bytes)


def address_p2sh_p2wpkh(version, pubkey):
    assert pubkey[0] != 4, "uncompressed pubkey"
    prefix_bytes = version_to_bytes(version)
    pubkey_bytes = hash_160(pubkey)
    witness = b"\x00\x14" + pubkey_bytes
    witness_bytes = hash_160(witness)
    return b58check_encode(prefix_bytes + witness_bytes)


def address_p2wpkh(version, pubkey):
    assert pubkey[0] != 4, "uncompressed pubkey"
    witver = 0
    witprog = hash_160(pubkey)
    return bech32.encode(version, witver, witprog)


def script_sig_p2pkh(address, signature):
    script_sig = (
        op_push(signature)
        + signature
        + op_push(address.public_key)
        + address.public_key
    )
    return script_sig, []


def script_sig_p2sh_p2wpkh(address, signature):
    script_sig = b"\x16\x00\x14" + hash_160(address.public_key)
    return script_sig, [signature, address.public_key]


def script_sig_p2wpkh(address, signature):
    return b"", [signature, address.public_key]


def derive_output_script(coin, address):
    bech32_prefix = coin.get("bech32_prefix", "---")
    witver, witprog = bech32.decode(bech32_prefix, address)
    if witver is not None and witprog is not None:
        witver = witver + 0x50 if witver else 0  # convert 1..16 to OP_1..OP_16
        return (
            witver.to_bytes(1, "little") + len(witprog).to_bytes(1, "little") + witprog
        )

    address_bytes = b58check_decode(address)
    p2sh_version = version_to_bytes(coin["address_type_p2sh"])
    p2pkh_version = version_to_bytes(coin["address_type"])
    if address_bytes.startswith(p2sh_version):
        script_hash = address_bytes[len(p2sh_version) :]
        return SCRIPT_PREFIX_P2SH + script_hash + SCRIPT_SUFFIX_P2SH
    elif address_bytes.startswith(p2pkh_version):
        pk_hash = address_bytes[len(p2pkh_version) :]
        return SCRIPT_PREFIX_P2PKH + pk_hash + SCRIPT_SUFFIX_P2PKH
    else:
        raise ValueError("Unrecognized address")


def script_is_p2pkh(output_script):
    return (
        len(output_script) == SCRIPT_LENGTH_P2PKH
        and output_script.startswith(SCRIPT_PREFIX_P2PKH)
        and output_script.endswith(SCRIPT_SUFFIX_P2PKH)
    )


def script_is_p2sh(output_script):
    return (
        len(output_script) == SCRIPT_LENGTH_P2SH
        and output_script.startswith(SCRIPT_PREFIX_P2SH)
        and output_script.endswith(SCRIPT_SUFFIX_P2SH)
    )


def script_is_witness(output_script):
    return (
        # possible script lengths
        4 <= len(output_script) <= 42
        # first byte is OP_0 .. OP_16 (0x00 or 0x51..0x60)
        and (output_script[0] == 0 or 0x51 <= output_script[0] <= 0x60)
        # second byte is length of rest of data
        and len(output_script) - 2 == output_script[1]
    )


def get_op_return_data(output_script: bytes) -> typing.Optional[bytes]:
    prefix_len = len(SCRIPT_PREFIX_OP_RETURN) + 1
    try:
        prefix, data = output_script[:prefix_len], output_script[prefix_len:]
        if (
            # maximum allowed (standard) OPRETURN output
            len(output_script) <= 83
            and prefix.startswith(SCRIPT_PREFIX_OP_RETURN)
            # byte after prefix is length of rest
            and len(data) == prefix[-1]
        ):
            return data

    except Exception:
        pass

    return None


def derive_address(coin, output_script: bytes) -> str:
    if script_is_p2pkh(output_script):
        pk_hash = output_script[len(SCRIPT_PREFIX_P2PKH) : -len(SCRIPT_SUFFIX_P2PKH)]
        version_bytes = version_to_bytes(coin["address_type"])
        return b58check_encode(version_bytes + pk_hash)

    elif script_is_p2sh(output_script):
        script_hash = output_script[len(SCRIPT_PREFIX_P2SH) : -len(SCRIPT_SUFFIX_P2SH)]
        version_bytes = version_to_bytes(coin["address_type_p2sh"])
        return b58check_encode(version_bytes + script_hash)

    elif script_is_witness(output_script):
        witver = output_script[0] - 0x50 if output_script[0] else 0
        witprog = output_script[2:]
        assert len(witprog) == output_script[1], "invalid witness script"
        return bech32.encode(coin["bech32_prefix"], witver, witprog)

    else:
        raise ValueError("unrecognized output script")
