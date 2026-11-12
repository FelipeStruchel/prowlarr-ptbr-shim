"""Logging minimo: um logger compartilhado ("shim"), arquivo rotativo + stdout."""
import logging
import logging.handlers


def setup_logging(log_path):
    log = logging.getLogger("shim")
    handler = logging.handlers.RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)
    return log
