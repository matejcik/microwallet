from trezorlib.transport import enumerate_devices, get_transport
from trezorlib.client import TrezorClient
from trezorlib.ui import ClickUI
from trezorlib import coins, btc, tools

from . import account


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
    path_prefix = tools.parse_path(f"m/{account_type.value}h/{slip44}h/{number}h")
    script_type = account.INPUT_SCRIPTS[account_type]
    n = btc.get_public_node(
        client, path_prefix, coin_name=coin_name, script_type=script_type
    )
    return account.Account(coin_name, n.node, account_type, path=path_prefix)
