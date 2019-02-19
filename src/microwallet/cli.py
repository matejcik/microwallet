"""Console script for microwallet."""
import os
import sys
from decimal import Decimal
import asyncio
import functools

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


def async_command(func):
    @click.command(name=func.__name__)
    @click.pass_obj
    @functools.wraps(func)
    def wrapper(obj, *args, **kwargs):
        loop = asyncio.get_event_loop()
        fut = asyncio.ensure_future(func(obj, *args, **kwargs))
        return loop.run_until_complete(fut)

    main.add_command(wrapper)
    return wrapper


def progress(addrs=None, txes=None):
    out = []
    if addrs is not None:
        out.append(f"{addrs} addresses")
    if txes is not None:
        out.append(f"{txes} transactions")
    click.echo("\033[KLoading, " + ", ".join(out) + "...\r", nl=False)


@async_command
@click.option("-u", "--utxo", is_flag=True, help="Show individual UTXOs")
async def show(obj, utxo):
    _, account = obj
    symbol = account.coin["shortcut"]
    if utxo:
        total = Decimal(0)
        async for u in account.find_utxos(progress=progress):
            val_out = u.value / SATOSHIS
            txid = u.tx["txid"]
            click.echo(f"{u.address.str}: {txid}:{u.vout} - {val_out:f} {symbol}")
            total += u.value
        click.echo("\r\033[K", nl=False)
    else:
        total = await account.balance()
    total /= SATOSHIS
    click.echo(f"Balance: {total:f} {symbol}")


@async_command
@click.option("-s/-S", "--show/--no-show", help="Display address on Trezor")
async def receive(obj, show):
    client, account = obj
    address = await account.get_unused_address()
    click.echo(address.str)
    if client and show:
        trezor.show_address(client, account, address)


async def do_fund(account, address, amount, verbose):
    try:
        recipients = [(address, amount)]
        utxos, change = await account.fund_tx(recipients)
    except exceptions.InsufficientFunds:
        die("Insufficient funds")

    if verbose:
        symbol = account.coin["shortcut"]
        click.echo("Spending from:", err=True)
        total_in = Decimal(0)
        total_out = amount + Decimal(change)
        for u in utxos:
            am_out = u.value / SATOSHIS
            click.echo(f"{u.tx['txid']}:{u.vout} - {am_out:f} {symbol}", err=True)
            total_in += u.value
        fee_rate = await account.estimate_fee()
        actual_fee = total_in - total_out
        fee_out = actual_fee / SATOSHIS
        click.echo(f"Fee: {fee_out:f} {symbol} (at {fee_rate} sat/KB)", err=True)

    change_rcpts = []
    if change > 0:
        change_addr = await account.get_unused_address(change=True)
        change_rcpts.append((change_addr, change))

    return trezor.signing_data(account, utxos, recipients, change_rcpts)


@async_command
# fmt: off
@click.option("-v", "--verbose", is_flag=True, help="Print transaction details to console")
@click.option("-j", "--json", "json_file", type=click.File("w"), help="Store a JSON transaction")
@click.option("-p", "--psbt", "psbt_file", type=click.File("wb"), help="Store as BIP-174 PSBT")
@click.argument("address")
@click.argument("amount", type=Decimal)
# fmt: on
async def fund(obj, address, amount, json_file, psbt_file, verbose):
    _, account = obj
    signing_data = await do_fund(account, address, amount, verbose)
    if json_file:
        json_file.write(signing_data.to_json())
        json_file.write("\n")
    if psbt_file:
        click.echo("PSBT not ready just yet")
    if not json_file and not psbt_file:
        click.echo(signing_data.to_json(indent=4))


@async_command
# fmt: off
@click.option("-v", "--verbose", is_flag=True, help="Print transaction details to console")
@click.option("-n", "--dry-run", is_flag=True, help="Do not sign with Trezor")
@click.option("-b", "--no-broadcast", is_flag=True, help="Do not broadcast signed transaction")
@click.option("-j", "--json", type=click.File("w"), help="Store unsigned transaction as JSON")
@click.option("-p", "--psbt", type=click.File("wb"), help="Store funded transa")
# fmt: on
@click.argument("address")
@click.argument("amount", type=Decimal)
async def send(obj, address, amount, verbose, dry_run, no_broadcast):
    client, account = obj
    signing_data = await do_fund(account, address, amount, verbose)

    if client and not dry_run:
        _, signed_tx = trezor.sign_tx(client, signing_data)
        if verbose:
            click.echo("Signed transaction hex:")
            click.echo(signed_tx.hex())
        if not no_broadcast:
            txhex = await account.broadcast(signed_tx)
            click.echo(f"Transaction {txhex} broadcast successfully")
        else:
            click.echo("Transaction not broadcast")


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover; pylint: disable=E1120
