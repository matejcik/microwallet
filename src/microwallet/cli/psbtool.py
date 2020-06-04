import base64
import sys
from typing import Any

import click
import construct as c

from trezorlib import messages as m
from trezorlib.tools import HARDENED_FLAG
from microwallet.formats import psbt


def unparse_path(address_n):
    path_components = ["m"]
    for n in address_n:
        if n & HARDENED_FLAG:
            path_components.append(f"{n - HARDENED_FLAG}'")
        else:
            path_components.append(str(n))
    return "/".join(path_components)


def format_map(pb: psbt.PsbtMapType, indent: int = 0, sep: str = " " * 4,) -> str:
    def mostly_printable(bytes: bytes) -> bool:
        if not bytes:
            return True
        printable = sum(1 for byte in bytes if 0x20 <= byte <= 0x7E)
        return printable / len(bytes) > 0.8

    def pformat(name: str, value: Any, indent: int) -> str:
        level = sep * indent
        leadin = sep * (indent + 1)

        if isinstance(value, list):
            # short list of simple values
            if name == "address_n":
                return unparse_path(value)

            if not value or isinstance(value[0], int):
                return repr(value)

            # long list, one line per entry
            lines = ["[", level + "]"]
            lines[1:1] = [leadin + pformat(name, x, indent + 1) + "," for x in value]
            return "\n".join(lines)

        if isinstance(value, dict):
            lines = ["{"]
            for key, val in sorted(value.items()):
                if key == "_io":
                    continue
                if val is None or val == {}:
                    continue
                if not isinstance(key, str):
                    key = pformat(key, key, indent + 1)
                lines.append(leadin + key + ": " + pformat(key, val, indent + 1) + ",")
            lines.append(level + "}")
            return "\n".join(lines)

        if isinstance(value, (bytes, bytearray)):
            if mostly_printable(value):
                output = repr(value)
            else:
                output = value.hex()
            return f"{output} ({len(value)} bytes)"

        return repr(value)

    return pformat("", pb.__dict__, indent)


def get_psbt_bytes(psbt_base64, psbt_file):
    if psbt_file is not None:
        psbt_data = psbt_file.read()
        try:
            # try to decode base64. if this failed, interpret as raw bytes
            return base64.b64decode(psbt_data)
        except Exception:
            return psbt_data
    else:
        return base64.b64decode(psbt_base64)


@click.group()
def main():
    pass


@main.command(name="read")
@click.argument("psbt_base64", required=False)
@click.option("-f", "--file", "psbt_file", type=click.File("rb"))
def psbt_read(psbt_base64, psbt_file):
    """Print PSBT in a human-readable format.

    Provide either a Base64-encoded PSBT on the command line, or specify a path to
    a PSBT file with -f.
    """
    psbt_bytes = get_psbt_bytes(psbt_base64, psbt_file)
    header, inputs, outputs = psbt.read_psbt(psbt_bytes)
    click.echo("==== Transaction data:")
    click.echo(format_map(header))
    for i, inp in enumerate(inputs, 1):
        if inp:
            click.echo(f"==== Additional data for input #{i}:")
            click.echo(format_map(inp))
    for i, outp in enumerate(outputs, 1):
        if outp:
            click.echo(f"==== Additional data for output #{i}:")
            click.echo(format_map(outp))


@main.command()
@click.argument("psbt_base64", required=False)
@click.option("-f", "--file", "psbt_file", type=click.File("rb"))
@click.option("-c", "--coin-name", default="Bitcoin")
def to_json(psbt_base64, psbt_file):
    """Convert PSBT to Trezor-compatible JSON transaction.
    
    You can use `trezorctl btc sign-tx <file>` to sign it."""
    psbt_bytes = get_psbt_bytes(psbt_base64, psbt_file)
    header, inputs, outputs = psbt.read_psbt(psbt_bytes)

    fingerprints = set()
    for inout in inputs + outputs:
        for path in inout.bip32_path.values:
            fingerprints.add(path.fingerprint)

    if not fingerprints:
        raise click.ClickException("Nothing to sign!")

    if len(fingerprints) > 1:
        fingerprint_str = ", ".join(f.hex() for f in fingerprints)
        raise click.ClickException(
            f"More than one signer fingerprint found: {fingerprint_str}"
        )
        # TODO allow specifying or allow using all

    tx_details = {
        "version": header.transaction.version,
        "lock_time": header.transaction.lock_time,
    }
    details = m.SignTx(**tx_details)

    inputs = [
        m.TxInputType(prev_hash=txi.tx, prev_index=txi.index, sequence=txi.sequence)
        for txi in header.transaction.inputs
    ]
    outputs = [m.TxOutputType(amount=txo.value) for txo in header.transaction.outputs]


if __name__ == "__main__":
    sys.exit(main())
