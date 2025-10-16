from flask import app, Blueprint, render_template, make_response

bp = Blueprint("common", __name__)

@bp.route('/')
def home():
    return render_template("layouts/base.html")

@bp.route('/health')
def health():
    return make_response({"status": "OK"}, 200)