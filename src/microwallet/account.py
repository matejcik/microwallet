from decimal import Decimal
from enum import Enum
import functools
import typing
from concurrent.futures import ThreadPoolExecutor

import attr

from trezorlib import coins, tools
from trezorlib.messages import InputScriptType, OutputScriptType
from trezorlib.ckd_public import public_ckd, get_subnode

from .blockbook import BlockbookBackend
from .formats import transaction
from . import exceptions
from .address import Address, derive_output_script
from .account_type import ACCOUNT_TYPE_LEGACY, ACCOUNT_TYPE_DEFAULT, ACCOUNT_TYPE_SEGWIT


RBF_SEQUENCE_NUMBER = 0xFFFF_FFFD
SATOSHIS = Decimal(1e8)

THREAD_POOL = ThreadPoolExecutor(max_workers=100)


class Account:
    def __init__(
        self, coin_name, node, account_type=ACCOUNT_TYPE_LEGACY, path=None, backend=None
    ):
        self.coin_name = coin_name
        try:
            self.coin = coins.by_name[coin_name]
        except KeyError as e:
            raise ValueError(f"Unknown coin: {coin_name}") from e

        self.account_type = account_type
        self.path = path

        if backend is None:
            self.backend = BlockbookBackend(coin_name)
        else:
            self.backend = backend

        self.node = node
        self.addr_node = get_subnode(node, 0)
        self.change_node = get_subnode(node, 1)
        self.segwit = account_type is not ACCOUNT_TYPE_LEGACY

    def _addresses(self, change=False):
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

    def _address_data(self, change=False):
        address_source = self._addresses(change)
        while True:
            chunk = [next(address_source) for _ in range(20)]
            address_strs = [address.str for address in chunk]
            data = THREAD_POOL.map(self.backend.get_address_data, address_strs)
            for address, data in zip(chunk, data):
                address.data = data
            yield from chunk

    def active_address_data(self, change=False):
        unused_counter = 0
        for address in self._address_data(change):
            if address.data["totalReceived"] > 0:
                unused_counter = 0
                yield address
            else:
                unused_counter += 1

            if unused_counter > 20:
                break

    def get_unused_address(self, change=False):
        for address in self._address_data(change):
            if address.data["totalReceived"] == 0:
                return address

    def balance(self):
        addresses = []
        for change in (False, True):
            addresses += self.active_address_data(change)
        return sum(address.data["balance"] for address in addresses)

    def find_utxos(self):
        # XXX interleave main/change?
        for change in (False, True):
            for address in self.active_address_data(change):
                for utxo in self.backend.find_utxos(THREAD_POOL, address.data):
                    yield (address, *utxo)

    def estimate_fee(self):
        # TODO properly estimate fee
        try:
            result = int(self.backend.estimate_fee(5) * SATOSHIS)
            if result > 0:
                return result
        except Exception as e:
            print(e)

        return int(self.coin["default_fee_b"]["Normal"]) * 1024

    def fund_tx(self, recipients):
        utxos = []
        total = 0
        required = int(sum(amount for _, amount in recipients) * SATOSHIS)
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

        change_address = next(self._addresses(change=True))
        change_script = derive_output_script(self.coin, change_address.str)
        change_output = dict(value=0, script_pubkey=change_script)
        tx_data_with_change = tx_data.copy()
        tx_data_with_change["outputs"] = outputs[:] + [change_output]

        for utxo in self.find_utxos():
            utxos.append(utxo)
            _, _, _, amount = utxo
            total += int(amount * SATOSHIS)
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

        return tx_len * fee_rate_kb // 1024

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

