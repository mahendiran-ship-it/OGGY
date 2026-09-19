"""
OGGY entrypoint.

    python app.py

Serves the frontend (the Orb + chat UI) and the /api/* routes.
"""

from flask import Flask, send_from_directory

from api.routes import api_bp
from config import config
from tools import register_all_tools

FRONTEND_DIR = "frontend"

import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)

def create_app() -> Flask:
    config.ensure_dirs()
    register_all_tools()

    app = Flask(__name__, static_folder=None)
    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.route("/<path:filename>")
    def frontend_assets(filename):
        return send_from_directory(FRONTEND_DIR, filename)

    return app


app = create_app()

if __name__ == "__main__":
    print(f"OGGY is running at http://{config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
