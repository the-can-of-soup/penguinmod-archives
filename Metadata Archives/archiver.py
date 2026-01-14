from __future__ import annotations

import threading
import requests
import snapshot

BASE_URL: str = 'https://projects.penguinmod.com'
MAX_SIMULTANEOUS_LIGHT_REQUESTS: int = 4
MAX_SIMULTANEOUS_HEAVY_REQUESTS: int = 1

... # TODO
