"""Ponto de entrada do serviço escolar: cria a app Flask e regista os blueprints.

Não tem lógica de negócio — só importa os controllers (para que as suas rotas se
registem no blueprint partilhado `escolar_bp`) e liga tudo à app.
"""

from flask import Flask

from controllers.health_controller import bp as health_bp
from controllers.docs_controller import bp as docs_bp
from controllers.blueprint import bp as escolar_bp

import controllers.aluno_controller  # noqa: F401  (regista rotas no escolar_bp)
import controllers.turma_controller  # noqa: F401
import controllers.encarregado_controller  # noqa: F401
import controllers.profissional_controller  # noqa: F401
import controllers.chat_controller  # noqa: F401

app = Flask(__name__)
app.json.ensure_ascii = False

app.register_blueprint(health_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(escolar_bp)
