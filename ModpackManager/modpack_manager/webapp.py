"""Flask app: serve the picker UI and the scan/generate JSON API."""

from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

_WEB_DIR = Path(__file__).parent / "web"


def create_app(scan_fn, generate_fn) -> Flask:
    app = Flask(__name__, static_folder=None)
    cache = {"candidates": None}

    @app.get("/")
    def index():
        return send_from_directory(_WEB_DIR, "index.html")

    @app.get("/web/<path:filename>")
    def web_asset(filename):
        return send_from_directory(_WEB_DIR, filename)

    @app.get("/api/updates")
    def updates():
        if cache["candidates"] is None or request.args.get("refresh") == "1":
            cache["candidates"] = scan_fn()
        return jsonify({"candidates": [c.to_dict() for c in cache["candidates"]]})

    @app.post("/api/generate")
    def generate():
        selected = (request.get_json(silent=True) or {}).get("selected_mod_ids", [])
        # Reuse the already-scanned candidates so Generate doesn't re-hit the APIs.
        result = generate_fn(selected, cache["candidates"])
        return jsonify(result)

    return app
