"""Settings module for ``rq worker -c src.workflow.rq_settings``.

Keeps the Redis password out of the worker's command line: rq reads
``REDIS_URL`` from here instead of ``--url``.
"""

import os

from src.workflow.redis_auth import redis_url_with_password

REDIS_URL = redis_url_with_password(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
