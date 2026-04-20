"""Logging wrappers (Qt bridge + secret sanitizer).

Named ``log_ext`` to avoid any chance of shadowing the stdlib
:mod:`logging` module from an accidental bare ``import logging`` within
this package.
"""

from app.log_ext.qt_handler import QtLogHandler, get_handler, get_logger, setup
from app.log_ext.sanitizer import SecretFilter

__all__ = [
    "QtLogHandler",
    "SecretFilter",
    "get_handler",
    "get_logger",
    "setup",
]
