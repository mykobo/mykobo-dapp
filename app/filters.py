from datetime import datetime
from flask_humanize import Humanize


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


def humanize_time(value):
    """
    Convert a datetime string or datetime object to human-readable relative time
    e.g., "2 hours ago", "5 minutes ago", "just now"
    """
    if not value:
        return ""

    # Convert string to datetime if needed
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            return value
    else:
        dt = value

    # Calculate time difference
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    diff = now - dt

    seconds = diff.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m ago" if minutes > 1 else "1m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago" if hours > 1 else "1h ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days}d ago" if days > 1 else "1d ago"
    elif seconds < 2592000:
        weeks = int(seconds / 604800)
        return f"{weeks}w ago" if weeks > 1 else "1w ago"
    else:
        months = int(seconds / 2592000)
        return f"{months}mo ago" if months > 1 else "1mo ago"
