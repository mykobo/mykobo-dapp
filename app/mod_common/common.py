from flask import app, Blueprint, render_template

bp = Blueprint("common", __name__)

@bp.route('/')
def hello_world():
    return render_template("base.html")