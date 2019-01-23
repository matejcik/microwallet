import construct as c
from trezorlib.tools import b58check_encode, b58check_decode
from trezorlib.messages import HDNodeType

XpubStruct = c.Struct(
    "version" / c.Int32ub,
    "depth" / c.Int8ub,
    "fingerprint" / c.Int32ub,
    "child_num" / c.Int32ub,
    "chain_code" / c.Bytes(32),
    "key" / c.Bytes(33),
    c.Terminated,
)


def deserialize(xpubstr):
    xpub_bytes = b58check_decode(xpubstr)
    data = XpubStruct.parse(xpub_bytes)
    node = HDNodeType(
        depth=data.depth,
        fingerprint=data.fingerprint,
        child_num=data.child_num,
        chain_code=data.chain_code,
    )
    if data.key[0] == 0:
        node.private_key = data.key[1:]
    else:
        node.public_key = data.key

    return data.version, node


def serialize(version, node):
    data = dict(
        version=version,
        depth=node.depth,
        fingerprint=node.fingerprint,
        child_num=node.child_num,
        chain_code=node.chain_code,
    )
    if node.private_key:
        data["key"] = b"\0" + node.private_key
    else:
        data["key"] = node.public_key
    xpub_bytes = XpubStruct.build(data)
    return b58check_encode(xpub_bytes)
