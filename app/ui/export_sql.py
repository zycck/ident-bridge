# -*- coding: utf-8 -*-
"""SQL validation and formatting helpers for export-job editing."""

import re

import sqlglot
from sqlglot.errors import ParseError, TokenError


def validate_sql(sql: str) -> tuple[bool, str]:
    """Return whether the supplied SQL parses as full T-SQL."""
    sql = sql.strip()
    if not sql:
        return False, "Запрос пуст"

    try:
        statements = sqlglot.parse(
            sql,
            dialect="tsql",
            error_level=sqlglot.ErrorLevel.IMMEDIATE,
        )
    except (ParseError, TokenError) as exc:
        return False, format_sqlglot_error(exc)
    except Exception as exc:  # pragma: no cover — defensive
        return False, f"Ошибка парсера: {exc}"

    # sqlglot returns [None] for trailing/empty statements; require at least one real one
    if not any(stmt is not None for stmt in statements):
        return False, "Пустое выражение"

    return True, "SQL корректен"


def format_sqlglot_error(exc: Exception) -> str:
    """Take the first sqlglot error and make it short + Russian-friendly."""
    errors = getattr(exc, "errors", None)
    if errors:
        first = errors[0]
        desc = first.get("description") or ""
        line = first.get("line")
        col = first.get("col")
        # Translate a few common sqlglot phrases to Russian
        ru = (
            desc.replace("Expecting", "Ожидается")
            .replace("Expected", "Ожидается")
            .replace("Invalid expression", "Недопустимое выражение")
            .replace("Unexpected token", "неожиданный токен")
            .replace("but got", "—")
        )
        # Strip noisy <Token …> blob if present
        ru = re.sub(r"<Token[^>]*text:\s*([^,]+),[^>]*>", r"«\1»", ru)
        ru = re.sub(r"\s+", " ", ru).strip()
        if line and col:
            return f"стр {line}:{col} · {ru[:80]}"
        return ru[:100] or "Синтаксическая ошибка"
    return str(exc)[:100] or "Синтаксическая ошибка"


def format_sql_for_tsql_editor(sql: str) -> str:
    """Pretty-print SQL for the standalone editor without changing semantics."""
    sql = sql.strip()
    if not sql:
        return sql
    try:
        statements = sqlglot.transpile(sql, read="tsql", write="tsql", pretty=True)
        if statements:
            return ";\n\n".join(statements).rstrip(";\n") + ";"
    except Exception:
        pass
    return sql
