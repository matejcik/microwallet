import pytest

from microwallet import address, coins

VECTORS_P2PKH = [
    # m/44h/0h/15h/0/3
    (
        "Bitcoin",
        "1HeVhjL5hm3m6YB46KPaVKCsUFQTPVXpbZ",
        "026b4fc8187155120547f9b2074bd8edb907c82edb0b0c00b7cff3a3b122072a49",
    ),
    # m/44h/0h/15h/0/14
    (
        "Bitcoin",
        "16F9YaNMpMXG44u3jCheMLDVpYqPP4D5i1",
        "03259227d6d0bc4b16ff88d39f216319b71ca357c6add40bc4b165a4691acdcaf4",
    ),
    # m/44h/0h/15h/0/15
    (
        "Bitcoin",
        "19ihXYkx8FemH5AbuBQiwz6nVaBhwKzZ5",
        "03c21d9c2359f0036ceb0202e07bbc95e493acaa354b4cea5e520eec57e498b40d",
    ),
    # m/44h/0h/15h/0/926
    (
        "Bitcoin",
        "1ukj5nLyWryHCx636qHio54qUyRBDLKeN",
        "02ff4477266b5590a009b63ccc5c07c2dcfa1f7065013b332086d31441f952f80b",
    ),
    ### Litecoin
    # m/44h/2h/15h/0/3
    (
        "Litecoin",
        "LcRHc9ajvPjWKyY5YiS5yarnPXiAf5tKgv",
        "02edc9f6f3572b4996b8d148ad0a4f99d0de559e66ea0ef451e945660b68cc6fbf",
    ),
    # m/44h/2h/15h/0/14
    (
        "Litecoin",
        "LQLywtK86KW3aJzF9r5ZjhsNPU2hFjKkwz",
        "02701fd9e336d72dca0d28cbdb518a5af0114461ad630252c9d99003eea9d9dc36",
    ),
    # m/44h/2h/15h/0/15
    (
        "Litecoin",
        "LSELVkJsF2mdWbHJaCN6HAarJJA2q1dzpQ",
        "0348fefe8d9c3a7d273deda45b0c2176eb9a78c532bdfc685ccd415393ca1860e6",
    ),
    # m/44h/2h/15h/0/926
    (
        "Litecoin",
        "LfFycQGb7GjTtdLXfet6ua1a7EjqbMPHF3",
        "024e225938ea0817d22e352417fb1a911cea6b3db689dcf25c4f5bba512a617896",
    ),
    ### Dogecoin
    # m/44h/3h/15h/0/3
    (
        "Dogecoin",
        "DJdz3zbN6etDuuwRjBLCZpVtD7PvJLzEF6",
        "0321d219e759bc69308d28c60200403d7027de43b1163dec633abf831373d32b2e",
    ),
    # m/44h/3h/15h/0/14
    (
        "Dogecoin",
        "DQjEiMmGYYRTbQscTFzN2qnsqthb2xXMbF",
        "039aff0f14640f6aa39765541e01cbfa99f101f137b0522a97363f5105402ea2b0",
    ),
    # m/44h/3h/15h/0/15
    (
        "Dogecoin",
        "D9NrQDbwE4KFTUstviyxEdpB3R8oVFq2er",
        "03e69c6a834c7c38212c7a3e36f0d6a5a07168d79e28e2a405aedf76aac8a7f6fe",
    ),
    # m/44h/3h/15h/0/926
    (
        "Dogecoin",
        "DCizKdugHQqS6xTdT5kmm5B25qZaGzRxkJ",
        "02fb7f3c73bd7905ee4575e363b98cc1e8cf53a572d90402d2b90dabb28c62441c",
    ),
    ### Zcash
    # m/44h/133h/15h/0/3
    (
        "Zcash",
        "t1PPye9msWGSi2wE5poLoJRypSRQcZ8s8Gi",
        "035bcb47f6cd203340e22a76c3464bd81cd41d67c74d18bf78d26e9ecabee24468",
    ),
    # m/44h/133h/15h/0/14
    (
        "Zcash",
        "t1dWjWnmMF1PPRUkva955oHSgzLifbtYSko",
        "02eec861888b17ce1e8411a00f4f85a58e542bda1728a2c1b0b5f69dfd10da2013",
    ),
    # m/44h/133h/15h/0/15
    (
        "Zcash",
        "t1Nu4rqweDNyMM3xyKe22QTf1N4YD2wcGYJ",
        "035e49c0ec2913cdad4389f9082b133a9c9820c30587c46d9291fef2459734bb57",
    ),
    # m/44h/133h/15h/0/926
    (
        "Zcash",
        "t1dDAPrECQyd9sBbprtiSx1pNegC7VwEsye",
        "02825331ed1c38f001d2a46fe01f633f129bfa0322b62c4fb989ee6ae5dcb9d144",
    ),
]

VECTORS_P2SH_SEGWIT = [
    # m/48h/0h/15h/0/3
    (
        "3BCKHw64xVF3SHbfkYca7Kx2QP9fLRMwZz",
        "0359218e4a91f97eb1f230ebc7774eae2c4cc957ef25592db51316c813d77d24f3",
    ),
    # m/48h/0h/15h/0/14
    (
        "3NtU23mxYxYgLVL99qsLHeJoPfqCmX8P4o",
        "02098f67bbae06daa8a341c5478f0677d9f00d79f2c22e9f0d0c3b567979a3eff9",
    ),
    # m/48h/0h/15h/0/15
    (
        "3BHcLyT9k8RdDfasjBbaWaeRzXAazZJdGo",
        "02ca709fd23f3382e15574e01145898aa4e5923606e7369058ab1bd35ed24dec2d",
    ),
    # m/48h/0h/15h/0/926
    (
        "3LC4UyBTeUpYuEwYnkX7j2zr5JKSCNQi8Z",
        "02edc987a65933bb037eeaf03fa7bc543733cd9f14393b96863cd5056405209830",
    ),
]

VECTORS_SEGWIT = [
    # m/84h/0h/15h/0/3
    (
        "bc1qvp7jgc5uyn62w34fywe4v6kpp2wy4k9yyv9hgw",
        "02b2740e316bc5736e9a4c6eff461a20ee16661ba22bd0cb6d715a9d51e46d685c",
    ),
    # m/84h/0h/15h/0/14
    (
        "bc1qjnnr5u9qq97sk0xw3n7lnpkdn86mcxf7hp3etl",
        "02e47422adf2523b377a5184e1cd0fa75b19965122779258faecba48e2d91c545d",
    ),
    # m/84h/0h/15h/0/15
    (
        "bc1qqhac7jdy58nz63683kysjvvgt656aqw9atlw48",
        "02ce1d9d5a347bd379804d1331e43776988cac5017c033fb1b6dda229f233f1e0b",
    ),
    # m/84h/0h/15h/0/926
    (
        "bc1qc7h05m8m7mp8n35qxmgxxprnkt4d872l86lg5w",
        "039e34bc56e5b10f263260b3d24af8458462d894b9b3e2a02014cc929fb3d4fdb0",
    ),
]


@pytest.mark.parametrize("coin_name, addr, pubkey", VECTORS_P2PKH)
def test_address_p2pkh(coin_name, addr, pubkey):
    version = coins.by_name[coin_name]["address_type"]
    pubkey_bytes = bytes.fromhex(pubkey)
    computed_addr = address.address_p2pkh(version, pubkey_bytes)
    assert computed_addr == addr


@pytest.mark.parametrize("addr, pubkey", VECTORS_P2SH_SEGWIT)
def test_address_p2sh_segwit(addr, pubkey):
    version = coins.by_name["Bitcoin"]["address_type_p2sh"]
    pubkey_bytes = bytes.fromhex(pubkey)
    computed_addr = address.address_p2sh_p2wpkh(version, pubkey_bytes)
    assert computed_addr == addr


@pytest.mark.parametrize("addr, pubkey", VECTORS_SEGWIT)
def test_address_segwit(addr, pubkey):
    version = coins.by_name["Bitcoin"]["bech32_prefix"]
    pubkey_bytes = bytes.fromhex(pubkey)
    computed_addr = address.address_p2wpkh(version, pubkey_bytes)
    assert computed_addr == addr
