import asyncio
import json
import logging
import random
from decimal import Decimal
from urllib.parse import urlparse

import websockets

from . import coins

LOG = logging.getLogger(__name__)


class BlockbookWebsocketBackend:
    def __init__(self, coin_name, url=None, ssl_context=None):
        try:
            self.coin = coins.by_name[coin_name]
        except KeyError as e:
            raise ValueError(f"Unknown coin: {coin_name}") from e

        if url is None:
            try:
                url = random.choice(self.coin["blockbook"])
                # url = self.coin["blockbook"][0]
            except IndexError:
                raise ValueError("No backend URLs found") from None
            # urls = [DEV_BACKENDS[coin_name]]

        parsed_url = urlparse(url)
        if parsed_url.scheme in ("ws", "wss"):
            self.url = url
        else:
            # assume http link to blockbook endpoint
            self.url = f"wss://{parsed_url.netloc}{parsed_url.path}/websocket"

        self.ssl_context = ssl_context
        self.socket = None
        self._responder = None
        self._ws_response_cache = {}
        self._connections = 0

    async def __aenter__(self):
        if self._connections > 0:
            self._connections += 1
            return self

        self._connections += 1
        try:
            if self.ssl_context is not None:
                ssl = self.ssl_context
            else:
                ssl = True
            self.socket = await websockets.connect(self.url, ssl=ssl)
        except Exception as e:
            raise RuntimeError(f"Failed to connect to blockbook via {self.url}") from e
        else:
            LOG.info(f"Connected to {self.url}: {self.socket}")
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
                return
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
        return await self.fetch_json("getTransactionSpecific", txid=txhash)

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

    async def broadcast(self, signed_tx_bytes):
        return await self.fetch_json("sendTransaction", hex=signed_tx_bytes.hex())
