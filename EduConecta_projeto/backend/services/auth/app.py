from quart import Quart

from controllers.auth_controller import bp as auth_bp
from controllers.health_controller import bp as health_bp

app = Quart(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

app.register_blueprint(health_bp)
app.register_blueprint(auth_bp)
