import asyncio
import json
import os
from decimal import Decimal
from unittest import mock
from urllib.parse import urlparse

import asynctest
import pytest

from microwallet import coins
from microwallet.blockbook import BlockbookWebsocketBackend

# Doge transactions and addresses
BURN_ADDRESS = "D8microwa11etxxxxxxxxxxxxxxxwHnove"
BURN_TX = "7fd7ae813d65a00c7cf593ed354eedd71698473b0f7d7f1780f246ed340cf291"
COINBASE_TX = "b45db0667e5d7b80d867581d976f6735eb96d95baa3259cdfb91e13fd243caad"

USE_DEV_BACKEND = int(os.environ.get("MICROWALLET_DEV_BACKEND", "0"))


def doge_backend():
    if not USE_DEV_BACKEND:
        return BlockbookWebsocketBackend("Dogecoin", url="https://doge1.trezor.io")

    else:
        import ssl

        ctx = ssl.SSLContext()
        ctx.verify_mode = ssl.CERT_NONE

        return BlockbookWebsocketBackend(
            "Dogecoin",
            url="wss://blockbook-dev.corp.sldev.cz:9138/websocket",
            ssl_context=ctx,
        )


@pytest.fixture
async def backend():
    async with doge_backend() as backend:
        yield backend


class EchoSocket:
    def __init__(self):
        self.send_queue = []
        self.recv_queue = []

    async def send(self, datastr):
        data = json.loads(datastr)
        result = dict(id=data["id"], data=data["method"])
        resultstr = json.dumps(result)
        if self.recv_queue:
            fut = self.recv_queue.pop(0)
            fut.set_result(resultstr)
        else:
            self.send_queue.append(resultstr)

    def recv(self):
        fut = asyncio.Future()
        if self.send_queue:
            result = self.send_queue.pop(0)
            fut.set_result(result)
        else:
            self.recv_queue.append(fut)
        return fut

    async def close(self):
        pass


class ReverseEchoSocket:
    def __init__(self, trigger="run"):
        self.send_queue = []
        self.recv_queue = []
        self.trigger = trigger
        self.recving = False
        self.idx = 0

    async def send(self, datastr):
        data = json.loads(datastr)
        result = dict(id=data["id"], data=data["method"])
        resultstr = json.dumps(result)
        self.send_queue.append(resultstr)

        if data["method"] == self.trigger:
            self.recving = True
            for fut, resultstr in zip(reversed(self.recv_queue), self.send_queue):
                fut.set_result(resultstr)

    def recv(self):
        fut = asyncio.Future()
        if self.recving and self.send_queue:
            result = self.send_queue.pop(0)
            fut.set_result(result)
        else:
            self.recv_queue.append(fut)
        return fut

    async def close(self):
        pass


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


@pytest.mark.asyncio
@pytest.mark.parametrize("websocket", (EchoSocket, ReverseEchoSocket))
async def test_echo(websocket):
    fut = asyncio.Future()
    fut.set_result(websocket())
    websockets_connect = asynctest.Mock(return_value=fut)
    with mock.patch("websockets.connect", websockets_connect):
        backend = BlockbookWebsocketBackend("Dogecoin")
        async with backend:
            futures = []
            for n in range(6):
                method = f"method{n}"
                futures.append(
                    (method, asyncio.ensure_future(backend.fetch_json(method)))
                )
            futures.append(("run", asyncio.ensure_future(backend.fetch_json("run"))))

            for method, fut in futures:
                returned = await fut
                assert returned == method


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


@pytest.mark.xfail(not USE_DEV_BACKEND, reason="method not on public servers yet")
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


@pytest.mark.xfail(not USE_DEV_BACKEND, reason="method not on public servers yet")
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


@pytest.mark.network
@pytest.mark.asyncio
async def test_estimate_fee(backend):
    fee = await backend.estimate_fee(10)
    assert fee
    assert int(fee)
