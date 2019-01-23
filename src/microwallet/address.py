import typing
import attr

from trezorlib.tools import b58check_encode, b58check_decode, hash_160

from .formats import op_push, bech32


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
        return witver.to_bytes(1, "little") + witprog

    address_bytes = b58check_decode(address)
    p2sh_version = version_to_bytes(coin["address_type_p2sh"])
    p2pkh_version = version_to_bytes(coin["address_type"])
    if address_bytes.startswith(p2sh_version):
        script_hash = address_bytes[len(p2sh_version) :]
        return b"\xA9\x14" + script_hash + b"\x87"
    elif address_bytes.startswith(p2pkh_version):
        pk_hash = address_bytes[len(p2pkh_version) :]
        return b"\x76\xA9\x14" + pk_hash + b"\x88\xAC"
    else:
        raise ValueError("Unrecognized address")
