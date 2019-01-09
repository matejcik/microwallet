from trezorlib.tools import b58check_encode, hash_160


def address_p2pkh(address_type, pubkey):
    assert pubkey[0] != 4, "uncompressed pubkey"
    prefix_len = address_type.bit_length() // 8 + 1
    prefix_bytes = address_type.to_bytes(prefix_len, "little")
    pubkey_bytes = hash_160(pubkey)
    return b58check_encode(prefix_bytes + pubkey_bytes)


def address_p2sh_p2wpkh(address_type, pubkey):
    assert pubkey[0] != 4, "uncompressed pubkey"
    prefix_len = (address_type.bit_length() + 7) // 8
    prefix_bytes = address_type.to_bytes(prefix_len, "little")
    pubkey_bytes = hash_160(pubkey)
    witness = b"\x00\x14" + pubkey_bytes
    witness_bytes = hash_160(witness)
    return b58check_encode(prefix_bytes + witness_bytes)
