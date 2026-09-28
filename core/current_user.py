def get_current_user_id() -> int:
    """Функция-singleton: создатель во всех методах этой лабораторной.

    Идентификатор задан константой. При первом вызове он сохраняется
    на самой функции и дальше возвращается тот же самый.
    """
    if getattr(get_current_user_id, "_user_id", None) is None:
        get_current_user_id._user_id = 1
    return get_current_user_id._user_id
