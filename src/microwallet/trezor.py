from trezorlib.transport import enumerate_devices, get_transport
from trezorlib.client import TrezorClient
from trezorlib.ui import ClickUI
from trezorlib import coins, btc, tools, tx_api
from trezorlib.messages import SignTx, TxInputType, TxOutputType, OutputScriptType

from . import account

SATOSHIS = account.SATOSHIS


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


def sign_tx(client, account, utxos, recipients, change):
    details = SignTx(version=2)
    prev_txes = {
        bytes.fromhex(tx["txid"]): tx_api.json_to_tx(account.coin, tx)
        for _, tx, _, _ in utxos
    }
    inputs = [
        TxInputType(
            address_n=address.path,
            prev_hash=bytes.fromhex(tx["txid"]),
            prev_index=prevout,
            sequence=0xFFFF_FFFD,
            script_type=account.account_type.input_script_type,
            amount=int(amount * SATOSHIS),
        )
        for address, tx, prevout, amount in utxos
    ]
    outputs = [
        TxOutputType(
            address=address,
            amount=int(amount * SATOSHIS),
            script_type=OutputScriptType.PAYTOADDRESS,
        )
        for address, amount in recipients
    ]
    if change > 0:
        # XXX this should not be here
        change_address = account.get_unused_address(change=True)
        outputs.append(
            TxOutputType(
                address_n=change_address.path,
                amount=change,
                script_type=account.account_type.output_script_type,
            )
        )

    return btc.sign_tx(client, account.coin_name, inputs, outputs, details, prev_txes)
