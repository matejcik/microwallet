import asyncio
import json
import random
from decimal import Decimal

import aiohttp

from trezorlib import coins, tx_api


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

