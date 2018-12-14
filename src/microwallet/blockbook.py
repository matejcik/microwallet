import random
from decimal import Decimal

import requests

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

    def fetch_json(self, *path, **params):
        backend = random.choice(self.urls)
        url = backend + "/api/" + "/".join(map(str, path))
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json(parse_float=Decimal)

    def get_txdata(self, txhash):
        data = self.fetch_json("tx", txhash)
        if tx_api.is_zcash(self.coin) and data.get("vjoinsplit") and "hex" not in data:
            j = self.fetch_json("rawtx", txhash)
            data["hex"] = j["rawtx"]
        return data

    def decode_txdata(self, txdata):
        return tx_api.json_to_tx(self.coin, txdata)

    def get_tx(self, txhash):
        txdata = self.get_txdata(txhash)
        return self.decode_txdata(txdata)

    def get_address_data(self, address):
        address_data = self.fetch_json("address", address)
        try:
            for key in ("balance", "totalReceived", "totalSent"):
                if key in address_data:
                    address_data[key] = Decimal(address_data[key] or 0)
        except:
            print(address_data)
            raise
        return address_data

    def find_utxos(self, address_data):
        txos = []
        spent_vouts = set()
        # TODO transaction pagination
        address = address_data["addrStr"]
        for txhash in address_data["transactions"]:
            txdata = self.get_txdata(txhash)
            for vin in txdata["vin"]:
                spent_vouts.add((vin["txid"], vin["vout"]))
            for vout in txdata["vout"]:
                if address in vout["scriptPubKey"]["addreses"]:
                    txo = (txhash, vout["n"]), vout["value"]
                    txos.append(txo)

        return [(*vout, value) for vout, value in txos if vout not in spent_vouts]

