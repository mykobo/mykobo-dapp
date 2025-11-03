from flask import current_app as app, Blueprint, render_template, make_response, request
from mykobo_py.business.compliance.countries import WHITELISTED_COUNTRIES
from schwifty import IBAN

from app.util import get_fee

bp = Blueprint("common", __name__)


@bp.route('/')
def home():
    return render_template("layouts/base.html")


@bp.route('/health')
def health():
    return make_response({"status": "OK"}, 200)


@bp.route("/fees", methods=["GET"])
def fee_proxy():
    value = request.args.get("value")
    kind = request.args.get("kind")
    client_domain = request.args.get("client_domain")
    try:
        return make_response(get_fee(app.config["FEE_ENDPOINT"], value, kind, client_domain))
    except ValueError as e:
        return make_response({"error": str(e)}, 400)

@bp.route("/iban_check", methods=["GET"])
def iban_check():
    """
    Check if the provided IBAN is valid.
    """
    iban = request.args.get("iban")
    if not iban:
        return "IBAN is required", 400

    try:
        valid_iban = IBAN(iban, allow_invalid=True)
        if valid_iban.is_valid:
            if valid_iban.country_code not in WHITELISTED_COUNTRIES:
                return {
                    "valid": False,
                    "bic": valid_iban.bic,
                    "message": "IBAN from unsupported country"
                }, 400
            return {"valid": True, "bic": valid_iban.bic, "bank_name": valid_iban.bank_name}, 200
        else:
            return {"valid": False, "bic": None, "message": "IBAN format is not valid"}, 400
    except Exception as e:
        app.logger.exception(f"Invalid IBAN format: {e}")
        return "Invalid IBAN format", 400