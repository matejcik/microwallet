from decimal import Decimal

from typing import Dict, Any, List, Tuple, Optional

from trezorlib.messages import TxInputType, TxOutputType, HDNodeType

from .account import Account, Utxo
from .address import Address, derive_output_script
from .formats import psbt, xpub


def make_transaction(
    account: Account,
    utxos: List[Utxo],
    recipients: List[Tuple[str, int]],
    change_address: Optional[Address],
    change_amount: int = 0,
) -> Dict[Any, Any]:
    def make_tx_input(utxo: Utxo) -> Dict[Any, Any]:
        return dict(
            tx=bytes.fromhex(utxo.tx["txid"])[::-1],
            index=utxo.vout,
            script_sig=b"",
            sequence=0xFFFF_FFFD,
        )

    def make_tx_output(address: str, amount: int) -> Dict[Any, Any]:
        return dict(
            value=int(amount), script_pubkey=derive_output_script(account.coin, address)
        )

    if change_address is not None:
        recipients.append((change_address.str, change_amount))

    return dict(
        version=2,
        segwit=False,
        inputs=[make_tx_input(utxo) for utxo in utxos],
        outputs=[make_tx_output(address, amount) for address, amount in recipients],
        witness=[],
        lock_time=0,
    )


def non_witness_utxo(utxo: Utxo) -> Dict[Any, Any]:
    tx = utxo.tx
    inputs = [
        dict(
            tx=bytes.fromhex(i["txid"])[::-1],
            index=int(i["vout"]),
            script_sig=bytes.fromhex(i["scriptSig"]["hex"]),
            sequence=int(i["sequence"]),
        )
        for i in tx["vin"]
    ]
    outputs = [
        dict(
            value=int(Decimal(o["value"]) * 100_000_000),
            script_pubkey=bytes.fromhex(o["scriptPubKey"]["hex"]),
        )
        for o in tx["vout"]
    ]
    return dict(
        version=int(tx["version"]),
        segwit=False,
        inputs=inputs,
        outputs=outputs,
        witness=[],
        lock_time=int(tx["locktime"]),
    )


def make_psbt(
    master_fingerprint: int,
    account: Account,
    utxos: List[Utxo],
    recipients: List[Tuple[str, int]],
    change_address: Optional[Address],
    change_amount: int = 0,
) -> bytes:
    psbt_inputs = [
        psbt.PsbtInputType(
            non_witness_utxo=non_witness_utxo(utxo),
            bip32_path={
                utxo.address.public_key: dict(
                    fingerprint=master_fingerprint, address_n=utxo.address.path
                )
            },
        )
        for utxo in utxos
    ]

    psbt_outputs = [psbt.PsbtOutputType() for _ in recipients]
    if change_address is not None:
        psbt_outputs.append(
            psbt.PsbtOutputType(
                bip32_path={
                    change_address.public_key: dict(
                        fingerprint=master_fingerprint, address_n=change_address.path
                    )
                }
            )
        )

    tx = make_transaction(account, utxos, recipients, change_address, change_amount)
    return psbt.write_psbt(tx, psbt_inputs, psbt_outputs,)
