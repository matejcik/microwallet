from typing import Any, Callable, List, Tuple

import attr

from trezorlib.messages import InputScriptType, OutputScriptType

from . import address


@attr.s(auto_attribs=True)
class AccountType:
    type_id: int
    segwit: bool
    address_str: Callable[[Any, bytes], str]
    script_sig: Callable[[address.Address, bytes], Tuple[bytes, List[bytes]]]
    # TODO script_pubkey
    input_script_type: int
    output_script_type: int
    address_version_field: str


ACCOUNT_TYPE_LEGACY = AccountType(
    type_id=44,
    segwit=False,
    address_str=address.address_p2pkh,
    script_sig=address.script_sig_p2pkh,
    input_script_type=InputScriptType.SPENDADDRESS,
    output_script_type=OutputScriptType.PAYTOADDRESS,
    address_version_field="address_type",
)

ACCOUNT_TYPE_DEFAULT = AccountType(
    type_id=49,
    segwit=True,
    address_str=address.address_p2sh_p2wpkh,
    script_sig=address.script_sig_p2sh_p2wpkh,
    input_script_type=InputScriptType.SPENDP2SHWITNESS,
    output_script_type=OutputScriptType.PAYTOP2SHWITNESS,
    address_version_field="address_type_p2sh",
)

ACCOUNT_TYPE_SEGWIT = AccountType(
    type_id=84,
    segwit=True,
    address_str=address.address_p2wpkh,
    script_sig=address.script_sig_p2wpkh,
    input_script_type=InputScriptType.SPENDWITNESS,
    output_script_type=OutputScriptType.PAYTOWITNESS,
    address_version_field="bech32_prefix",
)


def default_account_type(coin_data):
    if coin_data["segwit"]:
        return ACCOUNT_TYPE_DEFAULT
    else:
        return ACCOUNT_TYPE_LEGACY
