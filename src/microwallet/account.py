from enum import Enum
import functools

from trezorlib import coins, tools
from trezorlib.messages import InputScriptType, OutputScriptType
from trezorlib.ckd_public import public_ckd, get_subnode

from .blockbook import BlockbookBackend
from . import address


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


class Account:
    def __init__(self, coin_name, node, account_type=AccountType.LEGACY, backend=None):
        try:
            self.coin = coins.by_name[coin_name]
        except KeyError as e:
            raise ValueError(f"Unknown coin: {coin_name}") from e

        self.account_type = account_type

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
            yield self.address_func(node.public_key)
            i += 1

    def balance(self):
        addresses = []
        for change in (False, True):
            unused_counter = 0
            for address in self._addresses(change):
                address_data = self.backend.get_address_data(address)
                # XXX there should be a rich address type
                if address_data["totalReceived"] > 0:
                    unused_counter = 0
                    addresses.append(address_data)
                else:
                    unused_counter += 1

                if unused_counter > 20:
                    break
        return sum(address["balance"] for address in addresses)
