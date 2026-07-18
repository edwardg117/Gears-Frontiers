"""Flask app: serve the picker UI and the scan/search/generate JSON API."""

from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

_WEB_DIR = Path(__file__).parent / "web"


def create_app(scan_fn, generate_fn, pack_fn, search_fn, resolve_fn, versions_fn) -> Flask:
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

    @app.get("/api/pack")
    def pack():
        return jsonify({"mods": pack_fn()})

    @app.get("/api/search")
    def search():
        hits = search_fn(request.args.get("q", ""), request.args.get("platform", "both"))
        return jsonify({"hits": [h.to_dict() for h in hits]})

    @app.get("/api/resolve")
    def resolve():
        hit = resolve_fn(request.args.get("ref", ""))
        return jsonify({"hit": hit.to_dict() if hit else None})

    @app.get("/api/project-versions")
    def project_versions():
        return jsonify(versions_fn(request.args.get("platform", "modrinth"),
                                   request.args.get("id", "")))

    @app.post("/api/generate")
    def generate():
        payload = request.get_json(silent=True) or {}
        return jsonify(generate_fn(payload, cache["candidates"]))

    return app
