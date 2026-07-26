"""Start the server and open the browser: python -m modpack_manager"""

import threading
import webbrowser

from .service import (real_scan, generate_events, real_pack, real_search,
                      real_resolve, real_project_versions, real_project_changelog,
                      real_commit, real_discard)
from .webapp import create_app

HOST, PORT = "127.0.0.1", 5178


def main():
    app = create_app(scan_fn=real_scan, generate_fn=generate_events, pack_fn=real_pack,
                     search_fn=real_search, resolve_fn=real_resolve,
                     versions_fn=real_project_versions,
                     changelog_fn=real_project_changelog,
                     commit_fn=real_commit, discard_fn=real_discard)
    url = f"http://{HOST}:{PORT}/"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Modpack Manager running at {url} (Ctrl+C to stop)")
    app.run(host=HOST, port=PORT, threaded=True)


if __name__ == "__main__":
    main()
