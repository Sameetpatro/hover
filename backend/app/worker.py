#!/usr/bin/env python3
"""Redis worker entrypoint: python -m app.worker"""

from app.services.worker import worker_loop

if __name__ == "__main__":
    worker_loop()
