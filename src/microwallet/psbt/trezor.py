import typing

from trezorlib import messages as m

from microwallet.address import (
    derive_address,
    script_is_p2pkh,
    script_is_p2sh,
    script_is_witness,
    get_op_return_data,
)


def make_transaction(tx) -> m.TransactionType:
    return m.TransactionType(
        version=tx.version,
        inputs=[make_input(txi) for txi in tx.inputs],
        outputs=[make_binoutput(txo) for txo in tx.outputs],
        lock_time=tx.lock_time,
    )


def find_address_n(bip32_paths, fingerprint) -> typing.List[int]:
    return next(
        (p.address_n for p in bip32_paths.values() if p.fingerprint == fingerprint),
        None,
    )


def make_signing_details(tx) -> m.SignTx:
    details_dict = {
        "version": tx.version,
        "lock_time": tx.lock_time,
    }
    return m.SignTx(**details_dict)


def make_input(tx_in, psbt_in=None, fingerprint=None) -> m.TxInputType:
    trezor_in = m.TxInputType(
        prev_hash=tx_in.tx,
        prev_index=tx_in.index,
        sequence=tx_in.sequence,
        script_sig=tx_in.script_sig,
    )

    if psbt_in is None and fingerprint is None:
        # input for prevtx
        return trezor_in

    # input for tx being signed

    if not psbt_in.non_witness_utxo:
        raise ValueError("Previous transaction not provided")

    trezor_in.script_sig = None
    trezor_in.amount = psbt_in.non_witness_utxo.outputs[tx_in.index].value
    trezor_in.address_n = find_address_n(psbt_in.bip32_path, fingerprint)

    if trezor_in.address_n is None:
        raise ValueError("Signing path not provided")

    script_pubkey = psbt_in.non_witness_utxo.outputs[tx_in.index].script_pubkey
    if script_is_p2pkh(script_pubkey):
        trezor_in.script_type = m.InputScriptType.SPENDADDRESS
    elif script_is_p2sh(script_pubkey):
        trezor_in.script_type = m.InputScriptType.SPENDP2SHWITNESS
    elif script_is_witness(script_pubkey):
        trezor_in.script_type = m.InputScriptType.SPENDWITNESS
    else:
        raise ValueError("Unsupported script type for input")

    return trezor_in


def make_output(tx_out, psbt_out, fingerprint, coin) -> m.TxOutputType:
    # TODO coin passthrough?
    trezor_out = m.TxOutputType(
        amount=tx_out.value,
        address=derive_address(coin, tx_out.script_pubkey),
        script_type=m.OutputScriptType.PAYTOADDRESS,
        op_return_data=get_op_return_data(tx_out.script_pubkey),
    )
    if trezor_out.op_return_data is not None:
        trezor_out.address = None
        trezor_out.script_type = m.OutputScriptType.PAYTOOPRETURN

    trezor_out.address_n = find_address_n(psbt_out.bip32_path, fingerprint)
    if trezor_out.address_n is not None:
        if trezor_out.op_return_data:
            raise ValueError("OP_RETURN must not have a BIP32 path")

        trezor_out.address = None
        if script_is_p2pkh(tx_out.script_pubkey):
            trezor_out.script_type = m.OutputScriptType.PAYTOADDRESS
        elif script_is_p2sh(tx_out.script_pubkey):
            trezor_out.script_type = m.OutputScriptType.PAYTOP2SHWITNESS
        elif script_is_witness(tx_out.script_pubkey):
            trezor_out.script_type = m.OutputScriptType.PAYTOWITNESS
        else:
            raise ValueError("Unsupported script type")

    return trezor_out


def make_binoutput(tx_out) -> m.TxOutputBinType:
    return m.TxOutputBinType(amount=tx_out.value, script_pubkey=tx_out.script_pubkey)
