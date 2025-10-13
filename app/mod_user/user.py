from flask import current_app, Blueprint, request, make_response

from app.decorators import require_wallet_auth

bp = Blueprint("user", __name__, url_prefix="/user")

@bp.route("/lobby", methods=("GET", "POST"))
@require_wallet_auth
def lobby():
    wallet_address = request.wallet_address
    print(wallet_address)
    return make_response("YOU ARE AT THE LOBBY")