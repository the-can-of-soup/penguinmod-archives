from __future__ import annotations

import threading
import requests
import snapshot

BASE_URL: str = 'https://projects.penguinmod.com'
MAX_SIMULTANEOUS_REQUESTS: int = 4


