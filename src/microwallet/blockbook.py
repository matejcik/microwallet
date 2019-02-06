import asyncio
import json
import random
from decimal import Decimal
import logging

import aiohttp
import websockets

from trezorlib import coins, tx_api

import ssl

SSL_UNVERIFIED_CONTEXT = ssl.SSLContext()
SSL_UNVERIFIED_CONTEXT.verify_mode = ssl.CERT_NONE

DEV_BACKENDS = {
    "Bitcoin": "wss://blockbook-dev.corp.sldev.cz:9130/websocket",
    "Testnet": "wss://blockbook-dev.corp.sldev.cz:19130/websocket",
    "Litecoin": "wss://blockbook-dev.corp.sldev.cz:9134/websocket",
    "Zcash": "wss://blockbook-dev.corp.sldev.cz:9132/websocket",
    "Dogecoin": "wss://blockbook-dev.corp.sldev.cz:9138/websocket",
}

LOG = logging.getLogger(__name__)


class WebsocketBackend:
    def __init__(self, coin_name, urls=None):
        try:
            self.coin = coins.by_name[coin_name]
        except KeyError as e:
            raise ValueError(f"Unknown coin: {coin_name}") from e

        if urls is None:
            # urls = self.coin["blockbook"]
            urls = [DEV_BACKENDS[coin_name]]
        if not urls:
            raise ValueError("No backend URLs found")

        self.url = random.choice(urls)
        self.socket = None
        self._responder = None
        self._ws_response_cache = {}
        self._connections = 0

    async def __aenter__(self):
        if self._connections > 0:
            self._connections += 1
            return self

        self._connections += 1
        self.socket = await websockets.connect(self.url, ssl=SSL_UNVERIFIED_CONTEXT)
        self._ws_response_cache = {}

        # utility subroutines
        def run_responder():
            """Call next recv() and assign callback"""
            self._responder = asyncio.ensure_future(self.socket.recv())
            self._responder.add_done_callback(responder_func)

        def responder_func(fut):
            """Callback. Process WS response and resume the appropriate id."""
            if fut.cancelled():
                self._responder = None
            try:
                response = fut.result()
                data = json.loads(response, parse_float=Decimal)
                to_resume = self._ws_response_cache.pop(data["id"])
                to_resume.set_result(data)
            except Exception as e:
                LOG.error(f"Exception when reading websocket: {e}")

            run_responder()

        run_responder()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._connections == 0:
            return
        elif self._connections == 1:
            self._responder.cancel()
            await self.socket.close()
            self.socket = None
            for fut in self._ws_response_cache.values():
                fut.set_exception(RuntimeError("Connection was closed"))
            self._ws_response_cache = {}
            self._connections = 0
        else:
            self._connections -= 1

    async def fetch_json(self, method, **params):
        if not self.socket:
            raise RuntimeError("Backend not connected")

        # prepare a Future that will resume when *our* response comes,
        # insert reference into response cache
        fut = asyncio.Future()
        request_id = str(id(fut))
        self._ws_response_cache[request_id] = fut

        # send a request packet
        packet = dict(id=request_id, method=method, params=params)
        packet_str = json.dumps(packet)
        await self.socket.send(packet_str)

        # await resumption when our response arrives
        data = await fut
        if "error" in data["data"]:
            # TODO custom exception handling
            raise Exception(data["data"]["error"]["message"])
        return data["data"]

    async def get_txdata(self, txhash):
        return await self.fetch_json("getTransaction", txid=txhash)

    async def get_address_data(self, address):
        data = await self.fetch_json(
            "getAccountInfo", descriptor=address, details="basic"
        )
        for key in ("balance", "totalReceived", "totalSent"):
            if key in data:
                data[key] = Decimal(data[key] or 0)
        return data

    async def get_utxos(self, address):
        return await self.fetch_json("getAccountUtxo", descriptor=address)

    async def estimate_fee(self, blocks):
        est = await self.fetch_json("estimateFee", blocks=[blocks])
        return est[0]["feePerUnit"]

    async def close(self):
        if self.socket:
            await self.socket.close()
            self.socket = None

    async def broadcast(self, signed_tx_bytes):
        result = await self.fetch_json("sendTransaction", hex=signed_tx_bytes.hex())
        if "error" in result:
            # TODO better handling
            raise Exception(result["error"])
        return result["result"]


class BlockbookBackend:
    def __init__(self, coin_name, urls=None):
        try:
            self.coin = coins.by_name[coin_name]
        except KeyError as e:
            raise ValueError(f"Unknown coin: {coin_name}") from e

        if urls is not None:
            self.urls = urls
        else:
            self.urls = self.coin["blockbook"]

        if not self.urls:
            raise ValueError("No backend URLs found")

        self.session = aiohttp.ClientSession()

    async def fetch_json(self, *path, **params):
        backend = random.choice(self.urls)
        url = backend + "/api/" + "/".join(map(str, path))
        r = await self.session.get(url, params=params)
        r.raise_for_status()
        json_loads = lambda s: json.loads(s, parse_float=Decimal)
        return await r.json(loads=json_loads)

    async def get_txdata(self, txhash):
        data = await self.fetch_json("tx", txhash)
        if tx_api.is_zcash(self.coin) and data.get("vjoinsplit") and "hex" not in data:
            j = await self.fetch_json("rawtx", txhash)
            data["hex"] = j["rawtx"]
        return data

    def decode_txdata(self, txdata):
        return tx_api.json_to_tx(self.coin, txdata)

    async def get_tx(self, txhash):
        txdata = await self.get_txdata(txhash)
        return self.decode_txdata(txdata)

    async def get_address_data(self, address, all_pages=False):
        async def get_page(page):
            address_data = await self.fetch_json("address", address, page=page)
            for key in ("balance", "totalReceived", "totalSent"):
                if key in address_data:
                    address_data[key] = Decimal(address_data[key] or 0)
            return address_data

        first_page = await get_page(1)
        if all_pages and first_page["totalPages"] > 1:
            pages = [get_page(n) for n in range(2, first_page["totalPages"] + 1)]
            for fut in asyncio.as_completed(pages):
                page = await fut
                first_page["transactions"] += page["transactions"]

        return first_page

    async def estimate_fee(self, blocks):
        result = await self.fetch_json("estimatefee", blocks)
        return Decimal(result["result"])

    async def get_utxos(self, address_data, progress=lambda: None):
        txos = []
        spent_vouts = set()
        # TODO transaction pagination
        address = address_data["addrStr"]
        transactions = [self.get_txdata(tx) for tx in address_data["transactions"]]
        for fut in asyncio.as_completed(transactions):
            txdata = await fut
            progress()
            for vin in txdata["vin"]:
                spent_vouts.add((vin["txid"], vin["vout"]))
            for vout in txdata["vout"]:
                if address in vout["scriptPubKey"]["addresses"]:
                    txo = txdata, vout["n"], Decimal(vout["value"])
                    txos.append(txo)

        return [
            (prevtx, prevout, value)
            for prevtx, prevout, value in txos
            if (prevtx["txid"], prevout) not in spent_vouts
        ]

