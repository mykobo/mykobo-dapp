from datetime import datetime


def currency(value, asset):
    if asset.startswith("iso4217:EUR") or asset.startswith("stellar:EURC"):
        symbol = "€"
    else:
        symbol = "$"

    return f"{symbol}{float(value):,.2f}"


def transaction_status(value: str):
    match value.lower():
        case "pending_payer" | "pending_payee":
            return "Waiting for you"
        case "completed":
            return "Transaction Complete"
        case "failed":
            return "Transaction Failed"
        case _:
            return "We are working on it"


def transaction_status_to_label(value: str):
    if value.lower().startswith("pending"):
        return "warning"
    if value.lower() == "completed":
        return "success"
    if value.lower() == "failed":
        return "danger"
    return "primary"


def datetime_from_string(value):
    timestamp_dt = datetime.fromisoformat(value)
    return timestamp_dt


def format_datetime_human(value):
    if value:
        return datetime_from_string(value).strftime("%d %B, %Y at %H:%M:%S")


def truncated_account(account):
    return f"{account[:6]}...{account[-6:]}"


def asset(value):
    if value.startswith("iso4217:"):
        return value.split(":")[1]
    if value.startswith("stellar:"):
        return value.split(":")[1]
    return value
