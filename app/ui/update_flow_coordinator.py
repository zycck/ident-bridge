import sys

from app.ui.main_window import update_flow_coordinator as _module

sys.modules[__name__] = _module
