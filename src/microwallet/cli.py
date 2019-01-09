"""Console script for microwallet."""
import os
import sys
from decimal import Decimal

import click

from . import account, trezor


class ChoiceType(click.Choice):
    def __init__(self, typemap):
        super(ChoiceType, self).__init__(typemap.keys())
        self.typemap = typemap

    def convert(self, value, param, ctx):
        value = super(ChoiceType, self).convert(value, param, ctx)
        return self.typemap[value]


ACCOUNT_TYPES = {
    "legacy": account.AccountType.LEGACY,
    "default": account.AccountType.P2SH_SEGWIT,
    "segwit": account.AccountType.SEGWIT,
}


def print_trezors(trezors):
    for t in trezors:
        f = t.features
        path = t.transport.get_path()
        click.echo(f"{f.label} (Trezor {f.model or '1'}, ID {f.device_id}): {path}")


def die(message=None, code=1):
    if message is not None:
        click.echo(message)
    sys.exit(code)


@click.group()
# fmt: off
@click.option("-c", "--coin-name", default="Bitcoin", help="Coin name")
@click.option("-a", "--account", "account_num", type=int, default=0, help="Account number")
@click.option("-t", "--type", "account_type", type=ChoiceType(ACCOUNT_TYPES), default="default", help="Account type")
@click.option("-p", "--trezor-path", default=os.environ.get("TREZOR_PATH"), help="Path to Trezor device")
@click.pass_context
# fmt: on
def main(ctx, coin_name, account_num, account_type, trezor_path):
    """Console script for microwallet."""
    trezors = trezor.get_all_clients()
    if not trezors:
        die("Please connect your Trezor device")
    if trezor_path:
        selected_trezors = [
            t for t in trezors if t.transport.get_path().startswith(trezor_path)
        ]
        if not selected_trezors:
            click.echo(f"Could not find Trezor by path: {trezor_path}")
            click.echo("Please connect the device or pick one of:")
            print_trezors(trezors)
            die()
        if len(selected_trezors) > 1:
            click.echo(f"More than one Trezor matches {trezor_path}:")
            print_trezors(selected_trezors)
            die("Please refine your selection")
        client = selected_trezors[0]
    elif len(trezors) > 1:
        click.echo("Multiple Trezor devices are connected.")
        click.echo("Please specify one with the -p <path> argument:")
        print_trezors(trezors)
        die()
    else:
        client = trezors[0]

    account = trezor.get_account(client, coin_name, account_num, account_type)
    ctx.obj = client, account


@main.command()
@click.pass_obj
@click.option("-u", "--utxo", is_flag=True, help="Show individual UTXOs")
def show(obj, utxo):
    _, account = obj
    symbol = account.coin["shortcut"]
    if utxo:
        total = Decimal(0)
        for address, tx, vout, value in account.find_utxos():
            click.echo(f"{address.str}: {tx}:{vout} - {value} {symbol}")
            total += value
    else:
        total = account.balance()
    click.echo(f"Balance: {total} {symbol}")


@main.command()
@click.pass_obj
def history(obj):
    _, account = obj


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
