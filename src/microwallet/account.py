import asyncio
from decimal import Decimal
from enum import Enum
import functools
import typing
from concurrent.futures import ThreadPoolExecutor

import attr

from trezorlib import coins, tools
from trezorlib.messages import InputScriptType, OutputScriptType
from trezorlib.ckd_public import public_ckd, get_subnode

from .blockbook import WebsocketBackend
from .formats import transaction, xpub
from . import exceptions
from .address import Address, derive_output_script
from .account_type import ACCOUNT_TYPE_LEGACY, ACCOUNT_TYPE_DEFAULT, ACCOUNT_TYPE_SEGWIT


RBF_SEQUENCE_NUMBER = 0xFFFF_FFFD
SATOSHIS = Decimal(1e8)


def NULL_PROGRESS(addrs=None, txes=None):
    pass


class Account:
    def __init__(
        self, coin_name, node, account_type=ACCOUNT_TYPE_LEGACY, path=None, backend=None
    ):
        self.coin_name = coin_name
        try:
            self.coin = coins.by_name[coin_name]
        except KeyError as e:
            raise ValueError(f"Unknown coin: {coin_name}") from e
        self.decimals = SATOSHIS

        self.account_type = account_type
        self.path = path or []

        if backend is None:
            self.backend = WebsocketBackend(coin_name)
        else:
            self.backend = backend

        self.node = node
        self.addr_node = get_subnode(node, 0)
        self.change_node = get_subnode(node, 1)
        self.segwit = account_type is not ACCOUNT_TYPE_LEGACY

    @classmethod
    def from_xpub(cls, coin_name, xpubstr):
        try:
            coin = coins.by_name[coin_name]
        except KeyError as e:
            raise ValueError(f"Unknown coin: {coin_name}") from e

        version, node = xpub.deserialize(xpubstr)
        if node.private_key:
            raise ValueError("Private key supplied, please use public key")

        if version == coin["xpub_magic"]:
            account_type = ACCOUNT_TYPE_LEGACY
        elif version == coin["xpub_magic_segwit_p2sh"]:
            account_type = ACCOUNT_TYPE_DEFAULT
        elif version == coin["xpub_magic_segwit_native"]:
            account_type = ACCOUNT_TYPE_SEGWIT
        else:
            raise ValueError("Unrecognized xpub magic (wrong coin maybe?)")

        return cls(coin_name, node, account_type)

    def _await(self, awaitable):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(awaitable)

    def addresses(self, change=False):
        i = 0
        master_node = self.addr_node if not change else self.change_node
        address_version = self.coin[self.account_type.address_version_field]
        address_func = self.account_type.address_str
        while True:
            node = get_subnode(master_node, i)
            address_str = address_func(address_version, node.public_key)
            path = self.path + [int(change), i]
            yield Address(path, change, node.public_key, address_str)
            i += 1

    async def _address_data(self, change=False):
        addr_iter = self.addresses(change)
        while True:
            chunk = []
            try:
                for _ in range(20):
                    chunk.append(next(addr_iter))
            except StopIteration:
                pass
            if not chunk:
                return

            batch = [
                asyncio.ensure_future(self.backend.get_address_data(a.str))
                for a in chunk
            ]
            # await asyncio.wait(batch)
            for address, data in zip(chunk, batch):
                address.data = await data
                yield address

    async def active_address_data(self, change=False):
        unused_counter = 0
        async for address in self._address_data(change):
            if address.data["totalReceived"] > 0:
                unused_counter = 0
                yield address
            else:
                unused_counter += 1

            if unused_counter > 20:
                break

    def get_unused_address(self, change=False):
        async def do():
            async for address in self._address_data(change):
                if address.data["totalReceived"] == 0:
                    return address

        return self._await(do())

    def balance(self):
        async def do():
            balance = Decimal(0)
            for change in (False, True):
                async for addr in self.active_address_data(change):
                    balance += addr.data["balance"]
            return balance

        return self._await(do())

    def find_utxos(self, progress=NULL_PROGRESS):
        async def do():
            result = []
            addrs = 0
            txes = 0

            # XXX interleave main/change?
            for change in (False, True):
                async for address in self.active_address_data(change):
                    utxos = await self.backend.get_utxos(address.str)
                    addrs += 1
                    progress(addrs=addrs, txes=txes)
                    for utxo in utxos:
                        txdata = await self.backend.get_txdata(utxo["txid"])
                        result.append(
                            (address, txdata, utxo["vout"], Decimal(utxo["value"]))
                        )
                        txes += 1
                        progress(addrs=addrs, txes=txes)
            return result

        return self._await(do())

    def estimate_fee(self):
        # TODO properly estimate fee
        try:
            backend_estimate = self._await(self.backend.estimate_fee(5))
            result = int(backend_estimate)
            if result > 0:
                return result
        except Exception as e:
            print(e)
            return int(self.coin["default_fee_b"]["Normal"]) * 1000

    def fund_tx(self, recipients):
        utxos = []
        total = 0
        required = int(sum(amount for _, amount in recipients))
        fee_rate_kb = self.estimate_fee()

        inputs = []
        witness = []
        outputs = []

        for addr, amount in recipients:
            script_pubkey = derive_output_script(self.coin, addr)
            outputs.append(dict(value=int(amount), script_pubkey=script_pubkey))

        tx_data = dict(
            version=2,
            segwit=self.segwit,
            inputs=inputs,
            outputs=outputs,
            witness=witness,
            lock_time=0,
        )

        # pick any address, this will not actually be used in the transaction
        change_address = next(self.addresses(change=True))

        change_script = derive_output_script(self.coin, change_address.str)
        change_output = dict(value=0, script_pubkey=change_script)
        tx_data_with_change = tx_data.copy()
        tx_data_with_change["outputs"] = outputs[:] + [change_output]

        for utxo in self.find_utxos():
            utxos.append(utxo)
            _, _, _, amount = utxo
            total += int(amount)
            inp, wit = self._make_input(*utxo)
            inputs.append(inp)
            witness.append(wit)
            if total < required:
                continue

            fee_without_change = self._calculate_fee(tx_data, fee_rate_kb)
            overfunds = total - required

            if overfunds == fee_without_change:
                return utxos, None

            if overfunds > fee_without_change:
                fee_with_change = self._calculate_fee(tx_data_with_change, fee_rate_kb)
                change_amount = overfunds - fee_with_change
                if change_amount < self.coin["dust_limit"]:
                    change_amount = 0
                return utxos, max(0, change_amount)

        raise exceptions.InsufficientFunds

    def _calculate_fee(self, tx_data, fee_rate_kb):
        base_tx_data = tx_data.copy()
        base_tx_data["segwit"] = False
        base_tx_data["witness"] = None
        base_tx = len(transaction.Transaction.build(base_tx_data)) + 2

        if not self.segwit:
            tx_len = base_tx
        else:
            total_tx = len(transaction.Transaction.build(tx_data))
            tx_len = (base_tx * 3 + total_tx) // 4

        return tx_len * fee_rate_kb // 1000

    def _make_input(self, address, prevtx, prevout, _):
        fake_sig = b"\0" * 71
        script_sig, witness = self.account_type.script_sig(address, fake_sig)
        return (
            dict(
                tx=bytes.fromhex(prevtx["txid"]),
                index=prevout,
                script_sig=script_sig,
                sequence=RBF_SEQUENCE_NUMBER,
            ),
            witness,
        )

    def broadcast(self, signed_tx_bytes):
        return self._await(self.backend.broadcast(signed_tx_bytes))

