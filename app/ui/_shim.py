import sys
from importlib import import_module


def alias(namespace: dict[str, object], module_name: str):
    module = import_module(module_name)
    sys.modules[namespace["__name__"]] = module
    return module
