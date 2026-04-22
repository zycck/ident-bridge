"""Tests for built-in SQL templates used by export jobs."""

from app.export.sql_templates import (
    export_job_sql_templates,
    get_export_job_sql_template,
)


def test_export_job_sql_templates_expose_expected_keys_and_labels() -> None:
    templates = export_job_sql_templates()

    assert [template.key for template in templates] == [
        "payroll_directory",
        "payroll_accruals_rate_1",
        "payroll_accruals_rate_2",
    ]
    assert [template.label for template in templates] == [
        "\u0421\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u0438\u043a \u0441\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a\u043e\u0432",
        "\u041d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u044f IDENT (\u0442\u0438\u043f \u0441\u0442\u0430\u0432\u043a\u0438 1)",
        "\u041d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u044f IDENT (\u0442\u0438\u043f \u0441\u0442\u0430\u0432\u043a\u0438 2)",
    ]


def test_payroll_directory_template_uses_short_fio_and_unique_employee_id() -> None:
    template = get_export_job_sql_template("payroll_directory")

    assert "employee_id" in template.sql
    assert "LEFT(LTRIM(RTRIM(p.Name)), 1)" in template.sql
    assert "LEFT(LTRIM(RTRIM(p.Patronymic)), 1)" in template.sql
    assert "DISTINCT" in template.sql
    assert "[\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a]" in template.sql


def test_payroll_accrual_template_uses_current_month_and_google_sheet_columns() -> None:
    template = get_export_job_sql_template("payroll_accruals_rate_1")

    assert (
        "DECLARE @MonthStart date = DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1);"
        in template.sql
    )
    assert "DECLARE @NextMonthStart date = DATEADD(MONTH, 1, @MonthStart);" in template.sql
    assert "AND srr.RateType = @RateType" in template.sql
    assert "[\u041c\u0435\u0441\u044f\u0446]" in template.sql
    assert "[\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a IDENT]" in template.sql
    assert "[\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a]" in template.sql
    assert "[\u041d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u043e]" in template.sql
    assert "[\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a]" in template.sql
    assert "[\u041a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0439]" in template.sql


def test_rate_specific_templates_differ_only_by_rate_type_default() -> None:
    rate_1 = get_export_job_sql_template("payroll_accruals_rate_1")
    rate_2 = get_export_job_sql_template("payroll_accruals_rate_2")

    assert "DECLARE @RateType int = 1;" in rate_1.sql
    assert "DECLARE @RateType int = 2;" in rate_2.sql
