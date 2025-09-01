import os
from flask import Flask
from .db import init_db, get_db_path
from .routes import register_routes

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True, template_folder="templates", static_folder="static")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
        DATABASE=os.environ.get("DATABASE_URL", "sqlite:///instance/app.db"),
    )

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    init_db(app)

    register_routes(app)
    return app
