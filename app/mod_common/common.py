from flask import app, Blueprint, render_template

bp = Blueprint("common", __name__)

@bp.route('/')
def home():
    return render_template("layouts/base.html")