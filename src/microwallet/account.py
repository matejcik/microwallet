from decimal import Decimal
from enum import Enum
import functools
import typing

import attr

from trezorlib import coins, tools
from trezorlib.messages import InputScriptType, OutputScriptType
from trezorlib.ckd_public import public_ckd, get_subnode

from .blockbook import BlockbookBackend
from .formats import address
from . import exceptions


class AccountType(Enum):
    LEGACY = 44
    P2SH_SEGWIT = 49
    SEGWIT = 84


INPUT_SCRIPTS = {
    AccountType.LEGACY: InputScriptType.SPENDADDRESS,
    AccountType.P2SH_SEGWIT: InputScriptType.SPENDP2SHWITNESS,
    AccountType.SEGWIT: InputScriptType.SPENDWITNESS,
}

OUTPUT_SCRIPTS = {
    AccountType.LEGACY: OutputScriptType.PAYTOADDRESS,
    AccountType.P2SH_SEGWIT: OutputScriptType.PAYTOP2SHWITNESS,
    AccountType.SEGWIT: OutputScriptType.PAYTOWITNESS,
}


@attr.s(auto_attribs=True)
class Address:
    path: typing.List[int]
    change: bool
    type: AccountType
    public_key: bytes
    str: str
    data: typing.Dict[str, typing.Any] = {}


class Account:
    def __init__(
        self, coin_name, node, account_type=AccountType.LEGACY, path=None, backend=None
    ):
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

        if account_type == AccountType.LEGACY:
            self.address_func = functools.partial(
                address.address_p2pkh, self.coin["address_type"]
            )
        elif account_type == AccountType.P2SH_SEGWIT:
            self.address_func = functools.partial(
                address.address_p2sh_p2wpkh, self.coin["address_type_p2sh"]
            )
        else:
            raise RuntimeError("Address type unsupported (yet)")

    def _addresses(self, change=False):
        i = 0
        master_node = self.addr_node if not change else self.change_node
        while True:
            node = get_subnode(master_node, i)
            address_str = self.address_func(node.public_key)
            path = self.path + [int(change), i]
            yield Address(path, change, self.account_type, node.public_key, address_str)
            i += 1

    def active_address_data(self, change=False):
        unused_counter = 0
        for address in self._addresses(change):
            data = self.backend.get_address_data(address.str)
            if data["totalReceived"] > 0:
                unused_counter = 0
                address.data = data
                yield address
            else:
                unused_counter += 1

            if unused_counter > 20:
                break

    def get_unused_address(self, change=False):
        for address in self._addresses(change):
            data = self.backend.get_address_data(address.str)
            if data["totalReceived"] == 0:
                return address

    def balance(self):
        addresses = []
        for change in (False, True):
            for address in self.active_address_data(change):
                addresses.append(address)
        return sum(address.data["balance"] for address in addresses)

    def find_utxos(self):
        # XXX interleave main/change?
        for change in (False, True):
            for address in self.active_address_data(change):
                for utxo in self.backend.find_utxos(address.data):
                    yield (address, *utxo)

    def fund(self, amount):
        utxos = []
        total = Decimal(0)
        for utxo in self.find_utxos():
            _, _, _, value = utxo
            utxos.append(utxo)
            total += value
            if total >= amount:
                break
        if total < amount:
            raise exceptions.InsufficientFunds
        return utxos
