from time import time
from typing import Dict, Optional

import requests


def retrieve_ip_address(request):
    if request.headers.get("X-Forwarded-For"):
        ip = request.headers.get("X-Forwarded-For").split(",")[0]
    else:
        ip = request.remote_addr
    return ip


def get_minimum_transaction_value() -> int:
    return 10


def get_maximum_transaction_value() -> int:
    return 30000


def generate_reference() -> str:
    return f"MYK{int(time())}"


def get_fee(fee_endpoint: str, value: str, kind: str, client_domain: Optional[str]) -> Dict:
    try:
        response = requests.get(
            fee_endpoint,
            params={"value": value, "kind": kind, "client_domain": client_domain},
        )
        return response.json()
    except requests.exceptions.RequestException as e:
        raise ValueError("Error fetching fees: {e}")
