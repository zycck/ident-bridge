from app.config import AppConfig

_PENDING_DATABASE_TEXTS = frozenset({"Загрузка…", "Нет баз данных"})


def build_connection_config(
    *,
    sql_instance: str,
    sql_database: str,
    sql_user: str,
    sql_password: str,
) -> AppConfig:
    return AppConfig(
        sql_instance=sql_instance,
        sql_database=sql_database,
        sql_user=sql_user,
        sql_password=sql_password,
    )


def build_settings_payload(
    *,
    sql_instance: str,
    sql_database: str,
    sql_user: str,
    sql_password: str,
    auto_update_check: bool,
    run_on_startup: bool,
    github_repo: str,
) -> AppConfig:
    return AppConfig(
        sql_instance=sql_instance,
        sql_database=sql_database,
        sql_user=sql_user,
        sql_password=sql_password,
        auto_update_check=auto_update_check,
        run_on_startup=run_on_startup,
        github_repo=github_repo,
    )


def resolve_autosave_database(selected_db: str, combo_text: str) -> str:
    if selected_db:
        return selected_db
    if combo_text and combo_text not in _PENDING_DATABASE_TEXTS:
        return combo_text
    return ""
