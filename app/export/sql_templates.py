"""Built-in SQL templates for common export jobs."""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent


@dataclass(frozen=True, slots=True)
class ExportSqlTemplate:
    key: str
    label: str
    sql: str


def _normalize_sql(value: str) -> str:
    return dedent(value).strip()


_PAYROLL_DIRECTORY_SQL = _normalize_sql(
    """
    SELECT DISTINCT
        s.ID_Persons AS employee_id,
        short_name.short_fio AS [\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a]
    FROM dbo.Staffs s
    JOIN dbo.Persons p
        ON p.ID = s.ID_Persons
    CROSS APPLY (
        SELECT LTRIM(RTRIM(
            CONCAT(
                NULLIF(LTRIM(RTRIM(p.Surname)), N''),
                CASE
                    WHEN NULLIF(LTRIM(RTRIM(p.Name)), N'') IS NULL THEN N''
                    ELSE N' ' + LEFT(LTRIM(RTRIM(p.Name)), 1) + N'.'
                END,
                CASE
                    WHEN NULLIF(LTRIM(RTRIM(p.Patronymic)), N'') IS NULL THEN N''
                    ELSE LEFT(LTRIM(RTRIM(p.Patronymic)), 1) + N'.'
                END
            )
        )) AS short_fio
    ) short_name
    WHERE short_name.short_fio <> N''
    ORDER BY [\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a];
    """
)


def _payroll_accruals_sql(rate_type: int) -> str:
    return _normalize_sql(
        f"""
        DECLARE @MonthStart date = DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1);
        DECLARE @NextMonthStart date = DATEADD(MONTH, 1, @MonthStart);
        DECLARE @RateType int = {rate_type};

        WITH payroll_source AS (
            SELECT
                srr.ID_Staffs AS employee_id,
                DATEFROMPARTS(YEAR(srr.DateTimeAdded), MONTH(srr.DateTimeAdded), 1) AS month_start,
                CAST(COALESCE(srr.[Sum], 0) AS decimal(18, 2)) AS amount,
                short_name.short_fio AS ident_short_name
            FROM dbo.SalaryRevenueRates srr
            JOIN dbo.Staffs s
                ON s.ID_Persons = srr.ID_Staffs
            JOIN dbo.Persons p
                ON p.ID = s.ID_Persons
            CROSS APPLY (
                SELECT LTRIM(RTRIM(
                    CONCAT(
                        NULLIF(LTRIM(RTRIM(p.Surname)), N''),
                        CASE
                            WHEN NULLIF(LTRIM(RTRIM(p.Name)), N'') IS NULL THEN N''
                            ELSE N' ' + LEFT(LTRIM(RTRIM(p.Name)), 1) + N'.'
                        END,
                        CASE
                            WHEN NULLIF(LTRIM(RTRIM(p.Patronymic)), N'') IS NULL THEN N''
                            ELSE LEFT(LTRIM(RTRIM(p.Patronymic)), 1) + N'.'
                        END
                    )
                )) AS short_fio
            ) short_name
            WHERE srr.ID_Staffs IS NOT NULL
              AND srr.DateTimeAdded >= @MonthStart
              AND srr.DateTimeAdded < @NextMonthStart
              AND srr.RateType = @RateType
              AND COALESCE(srr.[Sum], 0) <> 0
              AND short_name.short_fio <> N''
        )
        SELECT
            RIGHT('0' + CAST(MONTH(month_start) AS varchar(2)), 2) + N'.' + CAST(YEAR(month_start) AS nvarchar(4)) AS [\u041c\u0435\u0441\u044f\u0446],
            ident_short_name AS [\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a IDENT],
            ident_short_name AS [\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a],
            CAST(SUM(amount) AS decimal(18, 2)) AS [\u041d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u043e],
            N'IDENT' AS [\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a],
            CAST(N'' AS nvarchar(200)) AS [\u041a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0439]
        FROM payroll_source
        GROUP BY employee_id, ident_short_name, month_start
        ORDER BY [\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a IDENT];
        """
    )


_TEMPLATES: tuple[ExportSqlTemplate, ...] = (
    ExportSqlTemplate(
        key="payroll_directory",
        label="\u0421\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u0438\u043a \u0441\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a\u043e\u0432",
        sql=_PAYROLL_DIRECTORY_SQL,
    ),
    ExportSqlTemplate(
        key="payroll_accruals_rate_1",
        label="\u041d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u044f IDENT (\u0442\u0438\u043f \u0441\u0442\u0430\u0432\u043a\u0438 1)",
        sql=_payroll_accruals_sql(1),
    ),
    ExportSqlTemplate(
        key="payroll_accruals_rate_2",
        label="\u041d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u044f IDENT (\u0442\u0438\u043f \u0441\u0442\u0430\u0432\u043a\u0438 2)",
        sql=_payroll_accruals_sql(2),
    ),
)

_TEMPLATE_BY_KEY = {template.key: template for template in _TEMPLATES}


def export_job_sql_templates() -> tuple[ExportSqlTemplate, ...]:
    return _TEMPLATES


def get_export_job_sql_template(key: str) -> ExportSqlTemplate:
    try:
        return _TEMPLATE_BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"Unknown SQL template: {key}") from exc


__all__ = [
    "ExportSqlTemplate",
    "export_job_sql_templates",
    "get_export_job_sql_template",
]
