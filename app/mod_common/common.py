from flask import current_app as app, Blueprint, render_template, make_response, request

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

