import hmac, hashlib
import struct

from trezorlib.tools import HARDENED_FLAG, hash_160
from trezorlib.messages import HDNodeType

from fastecdsa.curve import secp256k1
from fastecdsa.point import Point
from fastecdsa.encoding.sec1 import SEC1Encoder


def get_subnode(node, i):
    # Public Child key derivation (CKD) algorithm of BIP32
    i_as_bytes = struct.pack(">L", i)

    if i & HARDENED_FLAG:
        raise ValueError("Prime derivation not supported")

    # Public derivation
    data = node.public_key + i_as_bytes

    I64 = hmac.HMAC(key=node.chain_code, msg=data, digestmod=hashlib.sha512).digest()
    I_left_as_exponent = int.from_bytes(I64[:32], "big")

    # BIP32 magic converts old public key to new public point
    point = SEC1Encoder.decode_public_key(node.public_key, secp256k1)
    result = I_left_as_exponent * secp256k1.G + point

    if point == Point.IDENTITY_ELEMENT:
        raise ValueError("Point cannot be INFINITY")

    # Convert public point to compressed public key
    public_key = SEC1Encoder.encode_public_key(result)

    return HDNodeType(
        depth=node.depth + 1,
        child_num=i,
        chain_code=I64[32:],
        fingerprint=hash_160(node.public_key)[:4],
        public_key=public_key,
    )


def derive(node, path):
    for i in path:
        node = get_subnode(node, i)
    return node
