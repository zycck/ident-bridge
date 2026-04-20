"""Google Sheets options panel for Google Apps Script export targets."""

import json
import urllib.error
import urllib.parse
import urllib.request

from typing import override

from PySide6.QtCore import QEvent, QObject, QRegularExpression, QSignalBlocker, QSortFilterProxyModel, QStringListModel, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QHideEvent
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.app_logger import get_logger
from app.core.constants import GOOGLE_SCRIPT_HOSTS, USER_AGENT
from app.ui.theme import Theme
from app.ui.threading import run_worker
from app.ui.widgets import HeaderLabel

_log = get_logger(__name__)


class _SheetOptionsFetchError(RuntimeError):
    def __init__(self, user_message: str, *, debug_message: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.debug_message = debug_message or user_message


def _looks_like_gas_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit((url or "").strip())
    return (parsed.hostname or "").lower() in GOOGLE_SCRIPT_HOSTS


def _build_action_url(url: str, *, action: str) -> str:
    parsed = urllib.parse.urlsplit((url or "").strip())
    query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    filtered_query = [(key, value) for key, value in query_items if key != "action"]
    filtered_query.append(("action", action))
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(filtered_query),
            parsed.fragment,
        )
    )


def _preview_sheet_options_body(raw_body: bytes) -> str:
    preview = raw_body.decode("utf-8", errors="replace").strip()
    if not preview:
        return ""
    return " ".join(preview.split())[:240]


def _build_sheet_options_user_message(*, error_code: str = "", message: str = "", fallback: str) -> str:
    code = str(error_code or "").strip().upper()
    text = str(message or "").strip()

    if code == "UNAUTHORIZED":
        return "Доступ к обработчику запрещён. Проверьте публикацию проекта Apps Script и права доступа."
    if code in {"INVALID_ACTION", "INVALID_REQUEST_METHOD"}:
        return (
            "Адрес обработки настроен неверно. Проверьте, что указан адрес /exec "
            "опубликованного веб-приложения Apps Script."
        )
    if code == "MALFORMED_JSON":
        return (
            "Адрес обработки ответил некорректно. Проверьте, что указан адрес /exec "
            "опубликованного веб-приложения Apps Script."
        )
    if text:
        return text
    return fallback


def _parse_sheet_options_payload(raw_body: bytes, *, target_url: str) -> dict[str, object]:
    if not raw_body or not raw_body.strip():
        raise _SheetOptionsFetchError(
            "Адрес обработки вернул пустой ответ. Проверьте, что указан адрес /exec "
            "опубликованного веб-приложения Apps Script.",
            debug_message=f"URL={target_url}; response_preview=<empty>",
        )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        preview = _preview_sheet_options_body(raw_body) or "<empty>"
        raise _SheetOptionsFetchError(
            "Адрес обработки вернул не JSON. Проверьте, что указан адрес /exec "
            "опубликованного веб-приложения Apps Script.",
            debug_message=f"URL={target_url}; response_preview={preview}",
        ) from exc

    if not isinstance(payload, dict):
        raise _SheetOptionsFetchError(
            "Адрес обработки вернул неожиданный ответ. Проверьте публикацию проекта Apps Script.",
            debug_message=f"URL={target_url}; payload_type={type(payload).__name__}",
        )

    if payload.get("ok") is False:
        error_code = str(payload.get("error_code") or "").strip()
        message = str(payload.get("message") or "").strip()
        user_message = _build_sheet_options_user_message(
            error_code=error_code,
            message=message,
            fallback="Не удалось получить список листов от Apps Script.",
        )
        raise _SheetOptionsFetchError(
            user_message,
            debug_message=(
                f"URL={target_url}; error_code={error_code or '<none>'}; "
                f"message={message or '<empty>'}"
            ),
        )

    return payload


def _fetch_sheet_action_payload(target_url: str, *, timeout: float) -> dict[str, object]:
    request = urllib.request.Request(
        target_url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _parse_sheet_options_payload(response.read(), target_url=target_url)
    except urllib.error.HTTPError as exc:
        raw_body = exc.read()
        preview = _preview_sheet_options_body(raw_body) or "<empty>"
        try:
            payload = _parse_sheet_options_payload(raw_body, target_url=target_url)
        except _SheetOptionsFetchError as payload_exc:
            raise _SheetOptionsFetchError(
                payload_exc.user_message,
                debug_message=f"HTTP {exc.code}; {payload_exc.debug_message}",
            ) from exc
        raise _SheetOptionsFetchError(
            "Не удалось открыть адрес обработки. Проверьте, что скрипт опубликован как веб-приложение и указан адрес /exec.",
            debug_message=f"HTTP {exc.code}; URL={target_url}; response_preview={preview}; payload={payload}",
        ) from exc
    except urllib.error.URLError as exc:
        raise _SheetOptionsFetchError(
            "Не удалось подключиться к адресу обработки. Проверьте ссылку и доступ к сети.",
            debug_message=f"URL={target_url}; reason={exc.reason}",
        ) from exc


def fetch_google_sheet_options(url: str, *, timeout: float = 5.0) -> list[str]:
    parsed = urllib.parse.urlsplit((url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return []

    _fetch_sheet_action_payload(_build_action_url(url, action="ping"), timeout=timeout)
    payload = _fetch_sheet_action_payload(_build_action_url(url, action="sheets"), timeout=timeout)

    raw = payload.get("sheets")
    values: list[str] = []
    if isinstance(raw, str) and raw.strip():
        values.append(raw.strip())
    elif isinstance(raw, list):
        values.extend(str(item).strip() for item in raw if str(item).strip())

    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


class _SheetOptionsWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url

    @Slot()
    def run(self) -> None:
        try:
            self.result.emit(fetch_google_sheet_options(self._url))
        except _SheetOptionsFetchError as exc:
            _log.warning(
                "Не удалось обновить список листов Google Таблиц: %s; url=%s; details=%s",
                exc.user_message,
                self._url,
                exc.debug_message,
            )
            self.error.emit(exc.user_message)
        except Exception:  # noqa: BLE001
            _log.exception(
                "Не удалось обновить список листов Google Таблиц: url=%s",
                self._url,
            )
            self.error.emit("Не удалось обновить список листов. Подробности есть в окне отладки.")
        finally:
            self.finished.emit()


class _SheetNameField(QWidget):
    """Editable sheet picker with a persistent overlay suggestion list."""

    textChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._all_options: list[str] = []
        self._show_all_matches = True
        self._shutdown = False
        self._model = QStringListModel(self)
        self._filter_model = QSortFilterProxyModel(self)
        self._filter_model.setSourceModel(self._model)
        self._filter_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._filter_model.setFilterRole(Qt.ItemDataRole.DisplayRole)
        self._overlay_parent: QWidget | None = None

        self._build_ui()
        self._apply_filter("")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._edit = QLineEdit(self)
        self._edit.setPlaceholderText("Лист назначения")
        self._edit.textChanged.connect(self._on_text_changed)
        self._edit.installEventFilter(self)
        root.addWidget(self._edit)

        self._count_badge = QLabel("0", self._edit)
        self._count_badge.setStyleSheet(
            f"color: {Theme.gray_500};"
            f"background: transparent;"
            f"border: none;"
            f"padding: 0 2px;"
            f"font-size: {Theme.font_size_xs}pt;"
            f"font-weight: {Theme.font_weight_semi};"
        )
        self._count_badge.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._count_badge.show()

        # Overlay popup: не добавлять в layout, иначе список начнёт ломать верстку поля.
        self._suggestions_frame = QFrame(self)
        self._suggestions_frame.setObjectName("sheetSuggestionsFrame")
        self._suggestions_frame.setStyleSheet(
            f"QFrame#sheetSuggestionsFrame {{"
            f"  background-color: {Theme.surface};"
            f"  border: 1px solid {Theme.border_strong};"
            f"  border-radius: {Theme.radius}px;"
            f"}}"
            f"QLabel {{"
            f"  color: {Theme.gray_500};"
            f"  border: none;"
            f"  padding: 8px 12px;"
            f"}}"
            f"QListView {{"
            f"  background-color: transparent;"
            f"  color: {Theme.gray_900};"
            f"  border: none;"
            f"  outline: 0;"
            f"  padding: 4px;"
            f"}}"
            f"QListView::item {{"
            f"  background-color: {Theme.surface};"
            f"  color: {Theme.gray_900};"
            f"  padding: 8px 12px;"
            f"  margin: 1px 0;"
            f"  border-radius: {Theme.radius_sm}px;"
            f"}}"
            f"QListView::item:hover {{"
            f"  background-color: {Theme.primary_50};"
            f"  color: {Theme.primary_900};"
            f"}}"
            f"QListView::item:selected {{"
            f"  background-color: {Theme.primary_100};"
            f"  color: {Theme.primary_900};"
            f"}}"
        )
        frame_layout = QVBoxLayout(self._suggestions_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        self._empty_label = QLabel("Нет подходящих листов", self._suggestions_frame)
        self._empty_label.setVisible(False)
        frame_layout.addWidget(self._empty_label)

        self._list_view = QListView(self._suggestions_frame)
        self._list_view.setModel(self._filter_model)
        self._list_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._list_view.setUniformItemSizes(True)
        self._list_view.clicked.connect(self._apply_selected_index)
        self._list_view.installEventFilter(self)
        frame_layout.addWidget(self._list_view)

        self._suggestions_frame.hide()
        self._sync_badge_geometry()
        self.installEventFilter(self)

    def text(self) -> str:
        return self._edit.text().strip()

    def setText(self, value: str) -> None:
        self._edit.setText((value or "").strip())
        self._apply_filter(self._edit.text())

    def set_options(self, options: list[str]) -> None:
        self._all_options = [str(option).strip() for option in options if str(option).strip()]
        self._model.setStringList(self._all_options)
        self._update_count_badge()
        self._apply_filter(self._edit.text())

    def clear(self) -> None:
        self._edit.clear()
        self._apply_filter("")

    @override
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if self._shutdown:
            return super().eventFilter(watched, event)
        if watched is self._edit:
            if event.type() in (QEvent.Type.FocusIn, QEvent.Type.MouseButtonPress):
                self._show_all_matches = True
                QTimer.singleShot(0, self._show_suggestions)
            elif event.type() == QEvent.Type.FocusOut:
                QTimer.singleShot(0, self._sync_suggestions_visibility)
            elif event.type() == QEvent.Type.Resize:
                self._sync_badge_geometry()
                if self._suggestions_frame.isVisible():
                    self._position_suggestions()
            elif event.type() == QEvent.Type.KeyPress:
                key = getattr(event, "key", lambda: None)()
                if key in (
                    Qt.Key.Key_Down,
                    Qt.Key.Key_Up,
                    Qt.Key.Key_PageDown,
                    Qt.Key.Key_PageUp,
                ):
                    self._show_all_matches = False
                    self._show_suggestions()
                    self._move_selection(1 if key in (Qt.Key.Key_Down, Qt.Key.Key_PageDown) else -1)
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if self._list_view.currentIndex().isValid():
                        self._apply_selected_index(self._list_view.currentIndex())
                        return True
        elif watched is self._list_view:
            if event.type() == QEvent.Type.FocusOut:
                QTimer.singleShot(0, self._sync_suggestions_visibility)
            elif event.type() == QEvent.Type.KeyPress:
                key = getattr(event, "key", lambda: None)()
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if self._list_view.currentIndex().isValid():
                        self._apply_selected_index(self._list_view.currentIndex())
                        return True
        elif watched is self:
            if event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show):
                if self._suggestions_frame.isVisible():
                    self._position_suggestions()
            elif event.type() == QEvent.Type.Hide:
                self._suggestions_frame.hide()
        elif watched is self._overlay_parent:
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
                if self._suggestions_frame.isVisible():
                    self._position_suggestions()
            elif event.type() in (QEvent.Type.Hide, QEvent.Type.WindowDeactivate):
                self._suggestions_frame.hide()
            elif event.type() == QEvent.Type.Close:
                self.shutdown()
        return super().eventFilter(watched, event)

    def _on_text_changed(self, text: str) -> None:
        self._show_all_matches = False
        self._apply_filter(text)
        self.textChanged.emit(text)
        if self._edit.hasFocus():
            self._show_suggestions()

    def _apply_filter(self, text: str) -> None:
        pattern_text = "" if self._show_all_matches else text.strip()
        pattern = QRegularExpression.escape(pattern_text)
        self._filter_model.setFilterRegularExpression(
            QRegularExpression(
                pattern,
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            )
        )
        self._sync_selection()
        self._refresh_suggestions_state()

    def _sync_selection(self) -> None:
        if self._filter_model.rowCount() <= 0:
            self._list_view.clearSelection()
            return

        desired = self.text().casefold()
        for row in range(self._filter_model.rowCount()):
            index = self._filter_model.index(row, 0)
            value = str(index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
            if desired and value.casefold() == desired:
                self._list_view.setCurrentIndex(index)
                self._list_view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtTop)
                return

        first_index = self._filter_model.index(0, 0)
        self._list_view.setCurrentIndex(first_index)
        self._list_view.scrollTo(first_index, QAbstractItemView.ScrollHint.PositionAtTop)

    def _refresh_suggestions_state(self) -> None:
        if self._shutdown:
            return
        has_matches = self._filter_model.rowCount() > 0
        self._empty_label.setVisible(not has_matches)
        self._list_view.setVisible(has_matches)
        self._update_list_height()

    def _update_list_height(self) -> None:
        if self._shutdown:
            return
        visible_rows = min(max(self._filter_model.rowCount(), 1), 6)
        row_height = self._list_view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 38
        frame_height = (row_height * visible_rows) + 12
        if self._empty_label.isVisible():
            frame_height = 42
        self._suggestions_frame.resize(max(self._edit.width(), 280), frame_height)

    def _move_selection(self, step: int) -> None:
        count = self._filter_model.rowCount()
        if count <= 0:
            return

        current_row = self._list_view.currentIndex().row()
        if current_row < 0:
            current_row = 0
        next_row = max(0, min(count - 1, current_row + step))
        next_index = self._filter_model.index(next_row, 0)
        self._list_view.setCurrentIndex(next_index)
        self._list_view.scrollTo(next_index, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _apply_selected_index(self, index) -> None:
        if not index or not index.isValid():
            return

        value = str(index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        if not value:
            return

        with QSignalBlocker(self._edit):
            self._edit.setText(value)
        self._show_all_matches = True
        self._apply_filter(value)
        self.textChanged.emit(value)
        self._edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self._edit.end(False)
        self._show_suggestions()

    def _show_suggestions(self) -> None:
        if self._shutdown:
            return
        self._ensure_overlay_parent()
        if self._shutdown:
            return
        self._refresh_suggestions_state()
        self._position_suggestions()
        self._suggestions_frame.show()
        self._suggestions_frame.raise_()

    def _sync_suggestions_visibility(self) -> None:
        if self._shutdown or self._overlay_parent is None:
            return
        focus_widget = QApplication.focusWidget()
        keep_visible = focus_widget is self._edit
        if not keep_visible and focus_widget is not None:
            keep_visible = self._list_view.isAncestorOf(focus_widget) or self._suggestions_frame.isAncestorOf(focus_widget)
        self._suggestions_frame.setVisible(keep_visible)

    def _update_count_badge(self) -> None:
        self._count_badge.setText(f"{len(self._all_options)} листов")
        self._sync_badge_geometry()

    def _sync_badge_geometry(self) -> None:
        self._count_badge.adjustSize()
        badge_width = self._count_badge.width()
        badge_height = self._count_badge.height()
        x = max(8, self._edit.width() - badge_width - 10)
        y = max(0, (self._edit.height() - badge_height) // 2)
        self._count_badge.move(x, y)
        self._edit.setTextMargins(0, 0, badge_width + 18, 0)

    def _ensure_overlay_parent(self) -> None:
        if self._shutdown:
            return
        top_level = self.window()
        if top_level is None:
            return
        if self._overlay_parent is top_level:
            return

        if self._overlay_parent is not None:
            self._overlay_parent.removeEventFilter(self)

        self._suggestions_frame.hide()
        self._suggestions_frame.setParent(top_level)
        self._overlay_parent = top_level
        self._overlay_parent.installEventFilter(self)

    def _position_suggestions(self) -> None:
        if self._shutdown:
            return
        overlay_parent = self._overlay_parent or self.window()
        if overlay_parent is None:
            return

        pos = self._edit.mapTo(overlay_parent, self._edit.rect().bottomLeft())
        self._suggestions_frame.move(pos)

    def has_overlay_parent(self) -> bool:
        return self._overlay_parent is not None

    def shutdown(self) -> None:
        if self._overlay_parent is None:
            self._shutdown = True
            return

        self._shutdown = True
        self._suggestions_frame.hide()
        try:
            self._overlay_parent.removeEventFilter(self)
        except (TypeError, RuntimeError):
            pass
        self._suggestions_frame.setParent(None)
        self._overlay_parent = None
        try:
            self._suggestions_frame.deleteLater()
        except RuntimeError:
            pass


class ExportGoogleSheetsPanel(QWidget):
    """Optional Google Sheets settings shown for GAS webhook targets."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target_url = ""
        self._loading = False
        self._loading_tick = 0
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(220)
        self._refresh_timer.timeout.connect(self._advance_loading_animation)
        self._build_ui()
        self.setVisible(False)

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        self._sheet_name_field.shutdown()
        super().closeEvent(event)

    @override
    def hideEvent(self, event: QHideEvent) -> None:
        if self._sheet_name_field.has_overlay_parent():
            window = self.window()
            if window is None or not window.isVisible():
                self._sheet_name_field.shutdown()
        super().hideEvent(event)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        root.addWidget(HeaderLabel("Google Таблицы"))

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        form.setHorizontalSpacing(12)
        root.addLayout(form)

        sheet_row = QHBoxLayout()
        sheet_row.setSpacing(8)

        # Не возвращать отдельный popup через QCompleter или native QComboBox popup:
        # на Win11 это снова приносит чёрную системную рамку и рваный ввод.
        self._sheet_name_field = _SheetNameField(self)
        self._sheet_name_field.textChanged.connect(self.changed)
        sheet_row.addWidget(self._sheet_name_field, stretch=1)

        self._refresh_btn = QPushButton("Обновить", self)
        self._refresh_btn.clicked.connect(self._refresh_sheet_options)
        sheet_row.addWidget(self._refresh_btn)
        form.addRow("Лист", sheet_row)

        self._alias_hint_label = QLabel(
            "В SQL задавайте алиасы столбцов, чтобы имена в листе были понятнее.",
            self,
        )
        self._alias_hint_label.setWordWrap(True)
        self._alias_hint_label.setStyleSheet(
            f"color: {Theme.gray_500}; font-size: {Theme.font_size_xs}pt;"
        )
        root.addWidget(self._alias_hint_label)

        self._status_label = QLabel("", self)
        self._status_label.setStyleSheet(
            f"color: {Theme.gray_500}; font-size: {Theme.font_size_xs}pt;"
        )
        root.addWidget(self._status_label)

    def set_target_url(self, url: str) -> None:
        self._target_url = (url or "").strip()
        visible = _looks_like_gas_url(self._target_url)
        self.setVisible(visible)
        self._refresh_btn.setEnabled(visible and not self._loading)
        if not visible:
            self._status_label.setText("")

    def sheet_name(self) -> str:
        return self._sheet_name_field.text()

    def set_gas_options(
        self,
        *,
        sheet_name: str,
    ) -> None:
        with QSignalBlocker(self._sheet_name_field):
            self._sheet_name_field.setText(sheet_name)

    def set_sheet_options(self, options: list[str]) -> None:
        current = self.sheet_name()
        normalized = [option for option in options if option]
        self._sheet_name_field.set_options(normalized)
        if current:
            self._sheet_name_field.setText(current)
        else:
            self._sheet_name_field.clear()

    @Slot()
    def _refresh_sheet_options(self) -> None:
        if not _looks_like_gas_url(self._target_url):
            self._status_label.setText("URL Google Apps Script не задан.")
            return
        if self._loading:
            return

        self._set_loading(True)
        self._status_label.setText("Обновляем список листов…")
        worker = _SheetOptionsWorker(self._target_url)
        run_worker(
            self,
            worker,
            pin_attr="_sheet_options_worker",
            on_error=self._on_refresh_error,
            connect_signals=lambda current_worker, _thread: current_worker.result.connect(
                self._on_refresh_result
            ),
        )

    def _set_loading(self, loading: bool) -> None:
        self._loading = loading
        if loading:
            self._loading_tick = 0
            self._refresh_btn.setEnabled(False)
            self._refresh_timer.start()
            self._advance_loading_animation()
            return

        self._refresh_timer.stop()
        self._refresh_btn.setText("Обновить")
        self._refresh_btn.setEnabled(_looks_like_gas_url(self._target_url))

    @Slot()
    def _advance_loading_animation(self) -> None:
        frames = ("Обновляем", "Обновляем.", "Обновляем..", "Обновляем...")
        self._refresh_btn.setText(frames[self._loading_tick % len(frames)])
        self._loading_tick += 1

    @Slot(object)
    def _on_refresh_result(self, options: object) -> None:
        self._set_loading(False)
        values = [str(option).strip() for option in list(options or []) if str(option).strip()]
        self.set_sheet_options(values)
        if values:
            self._status_label.setText(f"Найдено листов: {len(values)}")
        else:
            self._status_label.setText(
                "Список листов пуст. Можно ввести имя листа вручную."
            )

    @Slot(str)
    def _on_refresh_error(self, message: str) -> None:
        self._set_loading(False)
        self._status_label.setText(f"Не удалось обновить список листов: {message}")
