"""Console script for microwallet."""
import os
import sys
from decimal import Decimal

import click
from trezorlib import btc

from . import account, account_type, trezor, exceptions
from .blockbook import BlockbookBackend, WebsocketBackend
from .account import SATOSHIS


class ChoiceType(click.Choice):
    def __init__(self, typemap):
        super(ChoiceType, self).__init__(typemap.keys())
        self.typemap = typemap

    def convert(self, value, param, ctx):
        value = super(ChoiceType, self).convert(value, param, ctx)
        return self.typemap[value]


ACCOUNT_TYPES = {
    "legacy": account_type.ACCOUNT_TYPE_LEGACY,
    "default": account_type.ACCOUNT_TYPE_DEFAULT,
    "segwit": account_type.ACCOUNT_TYPE_SEGWIT,
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


def select_trezor(trezor_path):
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
        return selected_trezors[0]
    elif len(trezors) > 1:
        click.echo("Multiple Trezor devices are connected.")
        click.echo("Please specify one with the -p <path> argument:")
        print_trezors(trezors)
        die()
    else:
        return trezors[0]


@click.group()
# fmt: off
@click.option("-c", "--coin-name", default="Bitcoin", help="Coin name")
@click.option("-u", "--url", default=os.environ.get("BLOCKBOOK_URL"), help="Blockbook backend URL")
@click.option("-a", "--account", "account_num", type=int, default=0, help="Account number")
@click.option("-t", "--type", "account_type", type=ChoiceType(ACCOUNT_TYPES), default="default", help="Account type")
@click.option("-p", "--trezor-path", default=os.environ.get("TREZOR_PATH"), help="Path to Trezor device")
@click.option("-x", "--xpub", help="Use this xpub instead of retrieving an account from Trezor")
@click.pass_context
# fmt: on
def main(ctx, coin_name, account_num, account_type, trezor_path, xpub, url):
    """Console script for microwallet."""
    if not xpub:
        client = select_trezor(trezor_path)
        acc = trezor.get_account(client, coin_name, account_num, account_type)
    else:
        client = None
        acc = account.Account.from_xpub(coin_name, xpub)

    if url:
        if url.startswith("wss:"):
            acc.backend = WebsocketBackend(coin_name, urls=[url])
        else:
            acc.backend = BlockbookBackend(coin_name, urls=[url])
    ctx.obj = client, acc


def progress(addrs=None, txes=None):
    out = []
    if addrs is not None:
        out.append(f"{addrs} addresses")
    if txes is not None:
        out.append(f"{txes} transactions")
    click.echo("\033[KLoading, " + ", ".join(out) + "...\r", nl=False)


@main.command()
@click.pass_obj
@click.option("-u", "--utxo", is_flag=True, help="Show individual UTXOs")
def show(obj, utxo):
    _, account = obj
    symbol = account.coin["shortcut"]
    if utxo:
        total = Decimal(0)
        for address, tx, vout, value in account.find_utxos(progress=progress):
            val_out = value / SATOSHIS
            click.echo(f"{address.str}: {tx['txid']}:{vout} - {val_out:f} {symbol}")
            total += value
        click.echo("\r\033[K", nl=False)
    else:
        total = account.balance()
    total /= SATOSHIS
    click.echo(f"Balance: {total:f} {symbol}")


@main.command()
@click.pass_obj
@click.option("-s/-S", "--show/--no-show", help="Display address on Trezor")
def receive(obj, show):
    client, account = obj
    address = account.get_unused_address()
    click.echo(address.str)
    if client and show:
        trezor.show_address(client, account, address)


@main.command()
@click.pass_obj
# fmt: off
@click.option("-v", "--verbose", is_flag=True, help="Print transaction details to console")
@click.option("-n", "--dry-run", is_flag=True, help="Do not sign with Trezor")
@click.option("-b", "--no-broadcast", is_flag=True, help="Do not broadcast signed transaction")
# fmt: on
@click.argument("address")
@click.argument("amount", type=Decimal)
def send(obj, address, amount, verbose, dry_run, no_broadcast):
    client, account = obj
    try:
        recipients = [(address, amount)]
        utxos, change = account.fund_tx(recipients)
        if verbose:
            symbol = account.coin["shortcut"]
            click.echo("Spending from:")
            total_in = Decimal(0)
            total_out = amount + Decimal(change)
            for _, tx, prevout, amount in utxos:
                am_out = amount / SATOSHIS
                click.echo(f"{tx['txid']}:{prevout} - {am_out:f} {symbol}")
                total_in += amount
            fee_rate = account.estimate_fee()
            actual_fee = total_in - total_out
            fee_out = actual_fee / SATOSHIS
            click.echo(f"Fee: {fee_out:f} {symbol} (at {fee_rate} sat/KB)")

        if client and not dry_run:
            _, signed_tx = trezor.sign_tx(client, account, utxos, recipients, change)
            if verbose:
                click.echo("Signed transaction hex:")
                click.echo(signed_tx.hex())
            if not no_broadcast:
                account.broadcast(signed_tx)

    except exceptions.InsufficientFunds:
        die("Insufficient funds")


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
