import attr
import pytest

from microwallet import coins
from microwallet.formats import xpub
from trezorlib.tools import H_

BITCOIN = coins.by_name["Bitcoin"]


@attr.s(auto_attribs=True)
class XpubVector:
    xpub: str
    magic: int
    depth: int
    fingerprint: int = attr.ib(converter=lambda x: int(x, 16))
    child_num: int
    chain_code: bytes = attr.ib(converter=bytes.fromhex)
    public_key: bytes = attr.ib(converter=bytes.fromhex)


VECTORS = [
    # all-all-all, m/44'/0'/15'
    XpubVector(
        xpub=(
            "xpub6BiVtCpG9fQQdziwDT8EyYPLnuXs14FwNZqGHhMzPDMdLKc97agw"
            "FKMb3FfiweRsnqkeHYymF31RJc9EozZxHUSHzkjQ2H9SKGe7GmRDGPM"
        ),
        magic=BITCOIN["xpub_magic"],
        depth=3,
        fingerprint="08bfd412",
        child_num=H_(15),
        chain_code="af5ed0988782329136b4d8434cd5f725189b225657048f44c2981f2c39cd3a5c",
        public_key="0204dabaaf7a74a20b75cd9054bdf1f26c68246d142f5be6fd99d8eb5726bb4bf2",
    ),
    # all-all-all, m/49'/0'/15'
    XpubVector(
        xpub=(
            "ypub6XKbB5DSkq8SWEHg7jdPKN3971PGEs69oD5yVVD4y9GeA2z1FiMA"
            "iACbD92qPtJ7hLoiLGDoFABSDT5A5VbZVfJHEwGTaLKnvnMPRdu3PPV"
        ),
        magic=BITCOIN["xpub_magic_segwit_p2sh"],
        depth=3,
        fingerprint="71e6b564",
        child_num=H_(15),
        chain_code="d2261151028e68ef286b70d193ca6dd7fa0b6d29c136af48567ee8aa1ba3c144",
        public_key="020095061a98b3bfe9aef9775a87e664ab6efe9f913d7910c2e0be2e27a19f837b",
    ),
    # all-all-all, m/84'/0'/15'
    XpubVector(
        xpub=(
            "zpub6rszzdAK6RubKxxKxydVq6Bpjz1mt8BBitik5JMBy3QZeegBLHYp"
            "9Nw5UR6xa6PrMdn4hfF79rQcfri7pvqo5jJdrYj1WowiVDtGBjD9nbS"
        ),
        magic=BITCOIN["xpub_magic_segwit_native"],
        depth=3,
        fingerprint="d4c3eca0",
        child_num=H_(15),
        chain_code="13293b1ae222a6957f49ec4349eb69dd712eb12f88070f3fd7a6efc20490cf94",
        public_key="02e3532e592c6052819482cf388dd2dd309ccac78f319fa6ffd74ffd91e11ce48b",
    ),
]


@pytest.mark.parametrize("vector", VECTORS)
def test_xpub_roundtrip(vector):
    version, node = xpub.deserialize(vector.xpub)
    assert version == vector.magic
    assert node.depth == vector.depth
    assert node.fingerprint == vector.fingerprint
    assert node.child_num == vector.child_num
    assert node.chain_code == vector.chain_code
    assert node.public_key == vector.public_key
    xpub_str = xpub.serialize(vector.magic, node)
    assert xpub_str == vector.xpub
