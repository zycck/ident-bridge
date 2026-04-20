"""Compatibility package for the Google Apps Script sink."""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request

from .ack import GasAck, parse_gas_ack
from .chunking import (
    GasChunkPlan,
    build_chunk_records,
    build_gas_chunk_payload,
    canonicalize_column_name,
    plan_gas_chunks,
)
from .delivery import GoogleAppsScriptDeliveryError, GoogleAppsScriptSink, build_user_delivery_error

__all__ = [
    "GasAck",
    "GasChunkPlan",
    "GoogleAppsScriptDeliveryError",
    "GoogleAppsScriptSink",
    "build_chunk_records",
    "build_gas_chunk_payload",
    "build_user_delivery_error",
    "canonicalize_column_name",
    "parse_gas_ack",
    "plan_gas_chunks",
]
