from flask import app, Blueprint


bp = Blueprint("common", __name__)

@bp.route('/')
def hello_world():
    return 'Hello World!'