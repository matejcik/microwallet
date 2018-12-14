from trezorlib.transport import get_transport
from trezorlib.client import TrezorClient
from trezorlib.ui import ClickUI
from trezorlib import coins, btc, tools

from . import account


def get_client(path=None, ui=None):
    transport = get_transport(path)
    if ui is None:
        ui = ClickUI()
    return TrezorClient(transport, ui)


def get_account(client, coin_name, number, legacy=False):
    if legacy:
        account_type = account.AccountType.LEGACY
    else:
        account_type = account.AccountType.P2SH_SEGWIT

    coin = coins.by_name[coin_name]
    slip44 = coin["slip44"]
    path_prefix = tools.parse_path(f"m/{account_type.value}h/{slip44}h/{number}h")
    script_type = account.INPUT_SCRIPTS[account_type]
    n = btc.get_public_node(
        client, path_prefix, coin_name=coin_name, script_type=script_type
    )
    return account.Account(coin_name, n.node, account_type)
