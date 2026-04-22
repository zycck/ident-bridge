import sys

from app.ui.export_jobs.editor.google_sheets import setup_wizard as _module

sys.modules[__name__] = _module
