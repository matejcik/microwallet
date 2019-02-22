from decimal import Decimal
from urllib.parse import urlparse

import pytest

from microwallet.blockbook import BlockbookWebsocketBackend
from trezorlib import coins

# Doge transactions and addresses
BURN_ADDRESS = "D8microwa11etxxxxxxxxxxxxxxxwHnove"
BURN_TX = "7fd7ae813d65a00c7cf593ed354eedd71698473b0f7d7f1780f246ed340cf291"
COINBASE_TX = "b45db0667e5d7b80d867581d976f6735eb96d95baa3259cdfb91e13fd243caad"


def doge_backend():
    return BlockbookWebsocketBackend("Dogecoin", url="https://doge1.trezor.io")


@pytest.fixture
async def backend():
    async with doge_backend() as backend:
        yield backend


def test_backend_from_coin():
    VALID_COIN = "Bitcoin"
    INVALID_COIN = "FakeCoin$$$"
    if VALID_COIN not in coins.by_name:
        raise RuntimeError("Bad coin data in trezorlib (Bitcoin is missing)")
    if INVALID_COIN in coins.by_name:
        raise RuntimeError(
            "Someone added a coin with a ridiculous name. "
            "Pick a different ridiculous name for tests."
        )

    bitcoin_backend = BlockbookWebsocketBackend(VALID_COIN)
    assert bitcoin_backend
    allowed_hosts = [urlparse(h).netloc for h in coins.by_name[VALID_COIN]["blockbook"]]
    backend_host = urlparse(bitcoin_backend.url).netloc
    assert backend_host in allowed_hosts

    with pytest.raises(ValueError):
        BlockbookWebsocketBackend(INVALID_COIN)


def test_backend_from_url():
    wss_url = "wss://btc1.trezor.io/websocket"
    wss_backend = BlockbookWebsocketBackend("Bitcoin", url=wss_url)
    assert wss_backend.url == wss_url

    https_url = "https://btc1.trezor.io"
    https_backend = BlockbookWebsocketBackend("Bitcoin", url=https_url)
    # https url should be converted to wss version:
    assert https_backend.url == wss_url


@pytest.mark.network
@pytest.mark.asyncio
async def test_connect():
    backend = doge_backend()
    async with backend as b:
        assert b is backend
        assert b.socket is not None

    # proper nesting
    async with backend:
        connected_socket = backend.socket
        assert connected_socket is not None
        async with backend:
            # should not reconnect when nesting
            assert connected_socket is backend.socket
        # should not disconnect after inner with-block
        assert backend.socket is not None
    # should disconnect after outer with-block
    assert backend.socket is None


@pytest.mark.network
@pytest.mark.asyncio
async def test_fetch_json(backend):
    info = await backend.fetch_json("getInfo")
    assert isinstance(info, dict)
    assert "name" in info

    with pytest.raises(Exception):
        await backend.fetch_json("completelyFakeMethodThatIJustMadeUp")


@pytest.mark.network
@pytest.mark.asyncio
async def test_get_txdata(backend):
    txdata = await backend.get_txdata(BURN_TX)

    assert txdata["txid"] == BURN_TX
    for key in (
        "vin",
        "vout",
        "version",
        "locktime",
        "hex",
        "confirmations",
        "blocktime",
        "time",
    ):
        assert key in txdata

    vins = txdata["vin"]
    vouts = txdata["vout"]
    assert len(vins) == 1
    assert len(vouts) == 2

    for key in ("txid", "vout", "scriptSig", "sequence"):
        assert key in vins[0]
    assert "hex" in vins[0]["scriptSig"]

    for vout in vouts:
        for key in ("value", "n", "scriptPubKey"):
            assert key in vout
        assert "hex" in vout["scriptPubKey"]

    assert BURN_ADDRESS in vouts[0]["scriptPubKey"]["addresses"]


@pytest.mark.network
@pytest.mark.asyncio
async def test_get_txdata_coinbase(backend):
    txdata = await backend.get_txdata(COINBASE_TX)
    vins = txdata["vin"]
    assert len(vins) == 1
    assert "coinbase" in vins[0]


@pytest.mark.network
@pytest.mark.asyncio
async def test_get_address_data(backend):
    addr_data = await backend.get_address_data(BURN_ADDRESS)
    for key in ("address", "balance", "totalReceived", "totalSent"):
        assert key in addr_data

    assert addr_data["address"] == BURN_ADDRESS
    assert isinstance(addr_data["balance"], Decimal)
    assert isinstance(addr_data["totalReceived"], Decimal)
    assert addr_data["balance"] == addr_data["totalReceived"] - addr_data["totalSent"]


@pytest.mark.network
@pytest.mark.asyncio
async def test_get_utxos(backend):
    utxos = await backend.get_utxos(BURN_ADDRESS)
    assert utxos
    my_utxo = next(u for u in utxos if u["txid"] == BURN_TX)
    assert my_utxo
    assert my_utxo["vout"] == 0
    assert my_utxo["value"] == "314159265"
