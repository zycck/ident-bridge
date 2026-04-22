__all__ = ["SqlEditor", "SqlEditorDialog"]


def __getattr__(name: str):
    if name in {"SqlEditor", "SqlEditorDialog"}:
        from app.ui.sql_editor.editor import SqlEditor, SqlEditorDialog

        return {"SqlEditor": SqlEditor, "SqlEditorDialog": SqlEditorDialog}[name]
    raise AttributeError(name)
