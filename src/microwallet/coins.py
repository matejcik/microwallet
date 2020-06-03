import json
from pathlib import Path

from trezorlib.btc import from_json

COINS_JSON_FILE = Path(__file__).parent.resolve() / "coins.json"
COINS_JSON = json.loads(COINS_JSON_FILE.read_text())

by_name = {coin["coin_name"]: coin for coin in COINS_JSON}


def json_to_tx(coin_data, tx_data):
    # TODO
    return from_json(tx_data)
