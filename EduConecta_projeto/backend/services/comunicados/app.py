"""Ponto de entrada do serviço comunicados: cria a app Flask e regista os
controllers (comunicados, chat e anexos/fotografias/vídeos).

Sem lógica de negócio aqui — só configuração da app e os dois handlers
globais (cache e tamanho de pedido), que se aplicam a todas as rotas.
"""

from flask import Flask
from werkzeug.exceptions import RequestEntityTooLarge

from controllers.anexo_controller import bp as anexos_bp
from controllers.chat_controller import bp as chat_bp
from controllers.comunicado_controller import bp as comunicados_bp
from controllers.docs_controller import bp as docs_bp
from controllers.health_controller import bp as health_bp
from utils.service_client import erro

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 26 * 1024 * 1024

app.register_blueprint(health_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(comunicados_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(anexos_bp)


@app.after_request
def impedir_cache(resposta):
    """Aplica Cache-Control: no-store a todas as respostas (dados sensíveis/pessoais)."""
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.errorhandler(RequestEntityTooLarge)
def pedido_demasiado_grande(_erro):
    """Converte o 413 automático do Flask (MAX_CONTENT_LENGTH) no formato de erro da API."""
    return erro(
        "request_too_large",
        "O pedido excede o tamanho permitido.",
        413,
    )
