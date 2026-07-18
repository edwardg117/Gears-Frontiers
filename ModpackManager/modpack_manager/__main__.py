"""Start the server and open the browser: python -m modpack_manager"""

import threading
import webbrowser

from .service import real_scan, real_generate
from .webapp import create_app

HOST, PORT = "127.0.0.1", 5178


def main():
    app = create_app(scan_fn=real_scan, generate_fn=real_generate)
    url = f"http://{HOST}:{PORT}/"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Modpack Manager running at {url} (Ctrl+C to stop)")
    app.run(host=HOST, port=PORT, threaded=True)


if __name__ == "__main__":
    main()
