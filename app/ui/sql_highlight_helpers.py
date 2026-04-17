"""Shared T-SQL highlighting helpers used by the SQL editor."""

from functools import lru_cache

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QTextCharFormat

from app.ui.theme import Theme

TSQL_KEYWORDS = {
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "VALUES",
    "INTO",
    "OUTPUT",
    "RETURNING",
    "CREATE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "TABLE",
    "VIEW",
    "INDEX",
    "PROCEDURE",
    "FUNCTION",
    "TRIGGER",
    "DATABASE",
    "SCHEMA",
    "FROM",
    "WHERE",
    "GROUP",
    "HAVING",
    "ORDER",
    "BY",
    "LIMIT",
    "OFFSET",
    "TOP",
    "DISTINCT",
    "ALL",
    "UNION",
    "INTERSECT",
    "EXCEPT",
    "WITH",
    "JOIN",
    "INNER",
    "LEFT",
    "RIGHT",
    "FULL",
    "OUTER",
    "CROSS",
    "ON",
    "USING",
    "AS",
    "ASC",
    "DESC",
    "AND",
    "OR",
    "NOT",
    "IN",
    "EXISTS",
    "BETWEEN",
    "LIKE",
    "IS",
    "NULL",
    "TRUE",
    "FALSE",
    "ANY",
    "SOME",
    "CASE",
    "WHEN",
    "THEN",
    "ELSE",
    "END",
    "IF",
    "BEGIN",
    "WHILE",
    "RETURN",
    "DECLARE",
    "SET",
    "PRINT",
    "EXEC",
    "EXECUTE",
    "GO",
    "PRIMARY",
    "FOREIGN",
    "KEY",
    "REFERENCES",
    "DEFAULT",
    "CHECK",
    "UNIQUE",
    "CONSTRAINT",
    "IDENTITY",
    "CASCADE",
}

TSQL_FUNCTIONS = {
    "COUNT",
    "SUM",
    "AVG",
    "MIN",
    "MAX",
    "COALESCE",
    "ISNULL",
    "NULLIF",
    "CAST",
    "CONVERT",
    "TRY_CAST",
    "TRY_CONVERT",
    "FORMAT",
    "LEN",
    "LEFT",
    "RIGHT",
    "SUBSTRING",
    "REPLACE",
    "TRIM",
    "LTRIM",
    "RTRIM",
    "UPPER",
    "LOWER",
    "CONCAT",
    "CHAR",
    "ASCII",
    "GETDATE",
    "SYSDATETIME",
    "DATEADD",
    "DATEDIFF",
    "DATEPART",
    "YEAR",
    "MONTH",
    "DAY",
    "ROW_NUMBER",
    "RANK",
    "DENSE_RANK",
    "PARTITION",
    "OVER",
    "ABS",
    "ROUND",
    "FLOOR",
    "CEILING",
    "POWER",
    "SQRT",
}


@lru_cache(maxsize=None)
def make_format(color: str, *, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


@lru_cache(maxsize=1)
def build_highlighter_assets():
    kw_fmt = make_format(Theme.syntax_keyword, bold=True)
    fn_fmt = make_format(Theme.syntax_function)
    string_fmt = make_format(Theme.syntax_string)
    number_fmt = make_format(Theme.syntax_number)
    comment_fmt = make_format(Theme.syntax_comment, italic=True)
    operator_fmt = make_format(Theme.syntax_operator)

    kw_pattern = r"\b(?:" + "|".join(TSQL_KEYWORDS) + r")\b"
    fn_pattern = r"\b(?:" + "|".join(TSQL_FUNCTIONS) + r")\b"

    rules = (
        (
            QRegularExpression(
                kw_pattern,
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            ),
            kw_fmt,
        ),
        (
            QRegularExpression(
                fn_pattern,
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            ),
            fn_fmt,
        ),
        (QRegularExpression(r"\b\d+(?:\.\d+)?\b"), number_fmt),
        (QRegularExpression(r"[=<>!+\-*/%]+"), operator_fmt),
    )
    line_comment_re = QRegularExpression(r"--[^\n]*")
    return rules, line_comment_re, string_fmt, comment_fmt
