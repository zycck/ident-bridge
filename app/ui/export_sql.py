import sys

from app.ui.export_jobs.editor import sql as _module

sys.modules[__name__] = _module
