"""Optional, bounded traffic producer. Control authorization applies to internal calls too."""

import json
import logging
import os
import signal
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from opspilot.config import get_settings
from opspilot.logging import configure_logging


def main():
    settings = get_settings()
    configure_logging(settings.log_level)
    endpoint = os.environ.get("OPSPILOT_API_URL", "http://127.0.0.1:8084")
    headers = {
        "Authorization": f"Bearer {settings.control_token.get_secret_value()}",
        "Content-Type": "application/json",
    }
    stopping = threading.Event()

    def request_shutdown(signum, frame):
        stopping.set()

    # Python as container PID 1 needs an explicit handler for graceful Compose stop.
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    while not stopping.is_set():
        for name in ("checkout-service", "payment-service", "inventory-service"):
            if stopping.is_set():
                break
            request = Request(
                f"{endpoint}/api/v1/simulator/{name}/workloads",
                data=json.dumps({"count": 12, "arrival_interval_ms": 25}).encode(),
                headers=headers,
                method="POST",
            )
            try:
                with urlopen(request, timeout=15) as response:
                    response.read()
                logging.info("traffic_batch_completed")
            except (HTTPError, URLError, TimeoutError):
                logging.error("traffic_batch_unavailable")
        stopping.wait(3)
    logging.info("traffic_worker_stopped")


if __name__ == "__main__":
    main()
