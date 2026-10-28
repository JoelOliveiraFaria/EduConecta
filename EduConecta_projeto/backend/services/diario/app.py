from flask import Flask

from controllers.diario_controller import bp as diario_bp
from controllers.health_controller import bp as health_bp

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

app.register_blueprint(health_bp)
app.register_blueprint(diario_bp)
