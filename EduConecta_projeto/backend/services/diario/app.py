"""Ponto de entrada do serviço diario.

Cria a app Flask e regista os blueprints (health, diario). Não deve crescer
com lógica de negócio — isso vive em controllers/, models/ e utils/.
"""

from flask import Flask

from controllers.diario_controller import bp as diario_bp
from controllers.docs_controller import bp as docs_bp
from controllers.health_controller import bp as health_bp

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

app.register_blueprint(health_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(diario_bp)
