"""Mock core banking system used to practice the integration safely.

It imitates a legacy core on purpose: upper-case field codes, YYYYMMDD dates,
one-letter status codes and 20-character references. It also has switches to
inject failures (see `faults.py`).
"""
