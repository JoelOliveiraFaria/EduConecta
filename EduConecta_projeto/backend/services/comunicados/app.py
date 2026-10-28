from flask import Flask
from werkzeug.exceptions import RequestEntityTooLarge

from controllers.anexo_controller import bp as anexos_bp
from controllers.chat_controller import bp as chat_bp
from controllers.comunicado_controller import bp as comunicados_bp
from controllers.health_controller import bp as health_bp
from utils.service_client import erro

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 26 * 1024 * 1024

app.register_blueprint(health_bp)
app.register_blueprint(comunicados_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(anexos_bp)


@app.after_request
def impedir_cache(resposta):
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.errorhandler(RequestEntityTooLarge)
def pedido_demasiado_grande(_erro):
    return erro(
        "request_too_large",
        "O pedido excede o tamanho permitido.",
        413,
    )
