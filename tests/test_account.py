import asyncio
import itertools
import typing

import attr
import pytest
from asynctest import MagicMock, patch

from microwallet import account_type
from microwallet.account import Account, BIP32_ADDRESS_DISCOVERY_LIMIT
from microwallet.formats import xpub


@attr.s(auto_attribs=True)
class AccountVector:
    coin_name: str
    xpub: str
    type: account_type.AccountType
    addresses: typing.List[str]
    change: typing.List[str]


VECTORS = [
    AccountVector(
        # m/49h/2h/15h
        coin_name="Litecoin",
        type=account_type.ACCOUNT_TYPE_DEFAULT,
        xpub=(
            "Mtub2syZtptY6mWDbfUYxStNwpWfnC1GCjgn94i7LACu9euPviukSSVp"
            "tfWu8kC7LKjD2pEUAf4Tk78zEG3eNEeFp1vdCuEaWu4thgYCiTP5fiA"
        ),
        addresses=[
            "MCbzx1zB9ArzrcW5ZRmynMXEjLaYrxp33h",
            "M9uuC491JF577P7A2BF7kRQSqC3kqKgP2y",
            "MMprCCHpMqS5nGUUQP5LqXp1CnkMG3taUD",
            "MAKwjwSPUsrjkWopYEQTCdu9HVkaGNV8Ja",
            "MBKL4t23XGNPw7Jyr8Ke9F9Ahg4qRFKENL",
            "MDh73owzDmsrH5ZY2KAHvGxThqcXxMBxCG",
        ],
        change=[
            "MMq3nsjgxSmo567SY9onBE7mZZLzF7d7oa",
            "MAo8xpMwAkbnvY7dh6YNzonGtgfh9o1RrB",
            "MLj692LwqUEXpwwgMcTKtZ4rJiL3DzDRB5",
            "MX7gwUHoj4SwTrub33JGFzBZDpz1aXkEJF",
            "MMDPB89YZ6Tk98UTAayh2WuLqHjJBpZBc7",
            "MGpveTP4Qh4tV29sSFjjz6fj9MkVU2Wedn",
        ],
    ),
    AccountVector(
        # m/44h/3h/15h
        coin_name="Dogecoin",
        type=account_type.ACCOUNT_TYPE_LEGACY,
        xpub=(
            "dgub8sbe5Mi8LA4eBLHDvNhQWYu8awPXZThRPr4B4o3yzUYx4HswUunt"
            "8C5pTCQS45ZGcEaTbeJ1NuwyTfD8hERktZw3r3r3iypBnAAxhNxQLFM"
        ),
        addresses=[
            "DBvD76yuDdqSRKXh65pyFbL3bJuqY2jnbX",
            "D7vFBCNtnsZXtK2TshbqUzgvHT7GXWo8Yq",
            "DRsuGwVTp9opR3qRqkPgyMQrQfAjwRpiX3",
            "DJdz3zbN6etDuuwRjBLCZpVtD7PvJLzEF6",
            "DJCZozyYBrhgyvzaueeMjCSmYswGZRZJMn",
            "DMjbi5E6GUtC8g4R4dURPhs27i9R6bQXjU",
        ],
        change=[
            "DBnLen5bVcRDFAeYJ4ny4G1anM1L3zSJjN",
            "D5xbVbJQu927azLUvg7NvBYu97okexqtEw",
            "DEWMAwjRL49WaebYK1i6b6ApHjZEC82fpM",
            "D6pzpuU3ipBGPp7N8ATAnH3AX26jFpXGFz",
            "D6R2dNLJwPzurajb5F5HwVGbmyq8H22CQe",
            "DESENMRPbVNZTW1zcjz98c9xbYVJFDbxAj",
        ],
    ),
    AccountVector(
        # m/84h/0h/15h
        coin_name="Bitcoin",
        type=account_type.ACCOUNT_TYPE_SEGWIT,
        xpub=(
            "zpub6rszzdAK6RubKxxKxydVq6Bpjz1mt8BBitik5JMBy3QZeegBLHYp"
            "9Nw5UR6xa6PrMdn4hfF79rQcfri7pvqo5jJdrYj1WowiVDtGBjD9nbS"
        ),
        addresses=[
            "bc1q9yjrygcxx93ur9jgmjle60l8kqwwcxllld3d7s",
            "bc1qdpupdw26jrhav4hflaljgvk8r7c0z284prlpwe",
            "bc1q2lx2fd2zw774cnmxk5mwe5r4c723wvdpxs3r25",
            "bc1qvp7jgc5uyn62w34fywe4v6kpp2wy4k9yyv9hgw",
            "bc1qdc5cdv3m9t9w9w9ee4qmaeaqztk7rja02tyrjy",
            "bc1q085kywupqv5uascm64cqjkaj9alw4866ux02cr",
        ],
        change=[
            "bc1qa9rdzekzgzykr73aswftf0pxwng5xpryklyd9l",
            "bc1qut7auk2zsr790qhzf7y4wfq5sts5urvuzzmc88",
            "bc1qyzz8ukgm7fnu6gquzvc7t4ztzyukrgxll0r56t",
            "bc1qn9lxvsn5hjsay3qx8fwwvm3tkde8h8vwp6xm5y",
            "bc1q0hx5pxl07u540fy5758827garkll5cqwth4f4a",
            "bc1q7cxyt4ttvkl8n6mq6dzhckeg67y9hfc7yvlvd6",
        ],
    ),
]


@pytest.mark.parametrize("vector", VECTORS)
def test_from_xpub(vector):
    account = Account.from_xpub(vector.coin_name, vector.xpub)
    _, node = xpub.deserialize(vector.xpub)
    assert account.node == node
    assert account.account_type is vector.type


@pytest.mark.parametrize("vector", VECTORS)
def test_addresses(vector):
    account = Account.from_xpub(vector.coin_name, vector.xpub)
    n = len(vector.addresses)
    generated = itertools.islice(account.addresses(), n)
    for i, expected, address in zip(range(n), vector.addresses, generated):
        assert address.str == expected
        assert address.path == [0, i]

    n = len(vector.change)
    generated = itertools.islice(account.addresses(change=True), n)
    for i, expected, address in zip(range(n), vector.change, generated):
        assert address.str == expected
        assert address.path == [1, i]


@pytest.mark.asyncio
async def test_unused_address():
    vector = VECTORS[0]
    backend = MagicMock()
    account = Account.from_xpub(vector.coin_name, vector.xpub, backend=backend)

    async def empty_address(addr):
        return {"addressStr": addr, "totalReceived": 0}

    backend.get_address_data = empty_address
    assert (await account.get_unused_address()).str == vector.addresses[0]

    counter = 0

    async def first_three_not_empty(addr):
        nonlocal counter
        total = 100 if counter < 3 else 0
        counter += 1
        return {"addressStr": addr, "totalReceived": total}

    backend.get_address_data = first_three_not_empty
    assert (await account.get_unused_address()).str == vector.addresses[3]


@pytest.mark.asyncio
async def test_active_addresses():
    vector = VECTORS[0]
    backend = MagicMock()
    account = Account.from_xpub(vector.coin_name, vector.xpub, backend=backend)
    counter = 0
    ACTIVE_ADDRESSES = 3

    async def mock_address_data(addr):
        nonlocal counter
        total = 100 if counter < ACTIVE_ADDRESSES else 0
        counter += 1
        return {"addressStr": addr, "totalReceived": total}

    backend.get_address_data = mock_address_data
    active_addresses = [a async for a in account.active_address_data()]

    assert len(active_addresses) == ACTIVE_ADDRESSES
    assert counter > BIP32_ADDRESS_DISCOVERY_LIMIT

