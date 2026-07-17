from __future__ import annotations

import os

from waitress import serve

from backend.server import app


def main() -> None:
    port = int(os.getenv("AUTHGUARD_API_PORT", "5105"))
    serve(app, host="127.0.0.1", port=port, threads=4)


if __name__ == "__main__":
    main()
