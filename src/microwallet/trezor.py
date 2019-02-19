import json
import typing

import attr
from trezorlib.transport import enumerate_devices, get_transport
from trezorlib.client import TrezorClient
from trezorlib.ui import ClickUI
from trezorlib import coins, btc, tools, messages, protobuf
from trezorlib.messages import SignTx, TxInputType, TxOutputType, OutputScriptType

from . import account, tx_api
from .address import Address

SATOSHIS = account.SATOSHIS


@attr.s(auto_attribs=True)
class TrezorSigningData:
    coin_name: str
    details: SignTx
    inputs: typing.List[TxInputType]
    outputs: typing.List[TxOutputType]
    prev_txes: typing.Dict[bytes, messages.TransactionType]

    def to_dict(self):
        return {
            "coin_name": self.coin_name,
            "details": protobuf.to_dict(self.details),
            "inputs": [protobuf.to_dict(i) for i in self.inputs],
            "outputs": [protobuf.to_dict(o) for o in self.outputs],
            "prev_txes": {
                key.hex(): protobuf.to_dict(value)
                for key, value in self.prev_txes.items()
            },
        }

    def to_json(self):
        return json.dumps(self.to_dict())


def get_all_clients(ui_factory=None):
    if ui_factory is None:
        ui_factory = ClickUI

    return [TrezorClient(device, ui_factory()) for device in enumerate_devices()]


def get_client(path=None, ui=None):
    if ui is None:
        ui = ClickUI()
    device = get_transport(path)
    return TrezorClient(device, ui)


def get_account(client, coin_name, number, account_type):
    coin = coins.by_name[coin_name]
    slip44 = coin["slip44"]
    path_prefix = tools.parse_path(f"m/{account_type.type_id}h/{slip44}h/{number}h")
    n = btc.get_public_node(
        client,
        path_prefix,
        coin_name=coin_name,
        script_type=account_type.input_script_type,
    )
    return account.Account(coin_name, n.node, account_type, path=path_prefix)


def show_address(client, account, address):
    return btc.get_address(
        client,
        account.coin_name,
        address.path,
        script_type=account.account_type.input_script_type,
        show_display=True,
    )


def utxo_to_input(utxo, script_type):
    return TxInputType(
        amount=int(utxo.value),
        address_n=utxo.address.path,
        script_type=script_type,
        prev_hash=bytes.fromhex(utxo.tx["txid"]),
        prev_index=utxo.vout,
        sequence=0xFFFF_FFFD,
    )


def recipient_to_output(address, amount, script_type=OutputScriptType.PAYTOADDRESS):
    if isinstance(address, Address):
        address = address.str
    return TxOutputType(address=address, amount=int(amount), script_type=script_type)


def signing_data(account, utxos, recipients, change):
    details = SignTx(version=2)
    prev_txes = {
        bytes.fromhex(u.tx["txid"]): tx_api.json_to_tx(account.coin, u.tx)
        for u in utxos
    }
    inputs = [utxo_to_input(u, account.account_type.input_script_type) for u in utxos]
    outputs = [recipient_to_output(address, amount) for address, amount in recipients]
    change_outputs = [
        recipient_to_output(address, amount, account.account_type.output_script_type)
        for address, amount in change
    ]

    return TrezorSigningData(
        coin_name=account.coin_name,
        details=details,
        inputs=inputs,
        outputs=outputs + change_outputs,
        prev_txes=prev_txes,
    )


def sign_tx(client, data):
    return btc.sign_tx(
        client, data.coin_name, data.inputs, data.outputs, data.details, data.prev_txes
    )
