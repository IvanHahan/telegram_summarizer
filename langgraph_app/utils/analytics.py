import os

import requests

GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID")
GA_API_SECRET   = os.getenv("GA_API_SECRET")
GA_ENDPOINT     = (
    f"https://www.google-analytics.com/mp/collect"
    f"?measurement_id={GA_MEASUREMENT_ID}&api_secret={GA_API_SECRET}"
)

def track_event(user_id: int | str, event_name: str) -> None:
    """
    Send a simple event to Google Analytics 4 via Measurement Protocol.
    """
    if not (GA_MEASUREMENT_ID and GA_API_SECRET):
        return

    payload = {
        "client_id": str(user_id),
        "events": [{"name": event_name}],
    }

    try:
        requests.post(GA_ENDPOINT, json=payload)
    except Exception:
        # silently ignore failures
        pass