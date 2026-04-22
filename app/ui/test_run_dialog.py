import sys

from app.ui.dialogs.test_run import dialog as _module

sys.modules[__name__] = _module
