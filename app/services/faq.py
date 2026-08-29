"""Database-backed FAQ items, editable by admins in all three languages.

Each FAQ item has a question + answer for ro/ru/en (the platform's supported
languages) and a sort_order for display ordering on the landing page.
"""

from __future__ import annotations

from typing import Any

from ..db import _conn

LANGS = ("ro", "ru", "en")


# Default Q&A seeded on first run (matches the original static FAQ).
DEFAULT_FAQ: list[dict[str, str]] = [
    {
        "question_ro": "Serviciul este gratuit?",
        "answer_ro": "Da, urmărirea facturilor și notificările sunt complet gratuite.",
        "question_ru": "Сервис бесплатный?",
        "answer_ru": "Да, отслеживание счетов и уведомления полностью бесплатны.",
        "question_en": "Is the service free?",
        "answer_en": "Yes, tracking your utility invoices and receiving notifications is completely free.",
    },
    {
        "question_ro": "Ce furnizori sunt suportați?",
        "answer_ro": "Premier Energy, Energocom, Termoelectrica, FEE Nord, Apă-Canal Chișinău, StarNet, INFOCOM, InfoSapr și Stroy Master Domofon.",
        "question_ru": "Какие поставщики поддерживаются?",
        "answer_ru": "Premier Energy, Energocom, Termoelectrica, FEE Nord, Apă-Canal Chișinău, StarNet, INFOCOM, InfoSapr и Stroy Master Domofon.",
        "question_en": "Which providers are supported?",
        "answer_en": "Premier Energy, Energocom, Termoelectrica, FEE Nord, Apă-Canal Chișinău, StarNet, INFOCOM, InfoSapr and Stroy Master Domofon.",
    },
    {
        "question_ro": "Cum conectez o utilitate?",
        "answer_ro": "Adaugă o locuință, apoi conectează utilitatea folosind numărul de contract sau contul personal.",
        "question_ru": "Как подключить услугу?",
        "answer_ru": "Добавьте жильё, затем подключите услугу по номеру договора или лицевого счёта.",
        "question_en": "How do I connect a utility?",
        "answer_en": "Add a home, then connect the utility using your contract or personal account number.",
    },
    {
        "question_ro": "Cât de des se verifică facturile?",
        "answer_ro": "În mod implicit facturile se verifică o dată pe zi; administratorul poate modifica intervalul.",
        "question_ru": "Как часто проверяются счета?",
        "answer_ru": "По умолчанию счета проверяются раз в день; администратор может изменить интервал.",
        "question_en": "How often are invoices checked?",
        "answer_en": "By default invoices are checked once a day; the administrator can change the interval.",
    },
    {
        "question_ro": "Cum voi fi anunțat de facturi noi?",
        "answer_ro": "Poți primi notificări prin email sau Telegram. Configurează-le în pagina Cont.",
        "question_ru": "Как я узнаю о новых счетах?",
        "answer_ru": "Вы можете получать уведомления по email или Telegram — настройте в разделе Аккаунт.",
        "question_en": "How will I be notified about new invoices?",
        "answer_en": "You can receive notifications by email or Telegram. Configure them in your Account page.",
    },
    {
        "question_ro": "Datele mele sunt în siguranță?",
        "answer_ro": "Da. Datele sensibile sunt criptate, parolele sunt hash-uite, iar accesul este protejat.",
        "question_ru": "Мои данные в безопасности?",
        "answer_ru": "Да. Чувствительные данные шифруются, пароли хешируются, доступ защищён.",
        "question_en": "Is my data safe?",
        "answer_en": "Yes. Sensitive data is encrypted, passwords are hashed, and access is protected.",
    },
    {
        "question_ro": "Pot gestiona mai multe locuințe?",
        "answer_ro": "Da, poți adăuga câte locuințe ai nevoie și conecta utilități separate la fiecare.",
        "question_ru": "Можно ли управлять несколькими объектами?",
        "answer_ru": "Да, вы можете добавить сколько угодно жилья и подключить к каждому свои услуги.",
        "question_en": "Can I manage more than one home?",
        "answer_en": "Yes, you can add as many homes as you need and connect separate utilities to each.",
    },
    {
        "question_ro": "Ce se întâmplă dacă uit parola?",
        "answer_ro": "Folosește linkul „Ai uitat parola?” de pe pagina de autentificare — îți trimitem un link de resetare pe email.",
        "question_ru": "Что если я забыл пароль?",
        "answer_ru": "Используйте ссылку «Забыли пароль?» на странице входа — мы пришлём ссылку для сброса.",
        "question_en": "What happens if I forget my password?",
        "answer_en": "Use the \"Forgot password\" link on the login page — we will send you a reset link by email.",
    },
    {
        "question_ro": "Aplicația îmi plătește facturile?",
        "answer_ro": "Nu. Urmărim și îți reamintim de facturi; plata se face direct către furnizor prin platforma lor (ex. oplata.md).",
        "question_ru": "Приложение оплачивает мои счета?",
        "answer_ru": "Нет. Мы отслеживаем и напоминаем о счетах; оплата производится напрямую поставщику через их платформу (например, oplata.md).",
        "question_en": "Does the app pay my bills for me?",
        "answer_en": "No. We track and remind you about invoices; payment is made directly to the provider through their platform (e.g. oplata.md).",
    },
    {
        "question_ro": "Cum îmi șterg contul sau datele?",
        "answer_ro": "Îți poți dezactiva contul chiar tu din pagina Cont. Contul și toate facturile sale se șterg definitiv automat după 30 de zile.",
        "question_ru": "Как удалить аккаунт или данные?",
        "answer_ru": "Вы можете самостоятельно деактивировать аккаунт на странице Аккаунт. Аккаунт и все его счета безвозвратно удаляются автоматически через 30 дней.",
        "question_en": "How do I delete my account or data?",
        "answer_en": "You can disable your account yourself from the Account page. The account and all its invoices are permanently deleted automatically after 30 days.",
    },
]


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def list_faq_items() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM faq_items ORDER BY sort_order, id"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def add_faq_item(data: dict[str, str]) -> int:
    with _conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM faq_items").fetchone()["c"]
        cur = conn.execute(
            """INSERT INTO faq_items
               (sort_order, question_ro, question_ru, question_en,
                answer_ro, answer_ru, answer_en)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                count,
                data.get("question_ro", ""), data.get("question_ru", ""),
                data.get("question_en", ""),
                data.get("answer_ro", ""), data.get("answer_ru", ""),
                data.get("answer_en", ""),
            ),
        )
        return cur.lastrowid


def update_faq_item(faq_id: int, data: dict[str, str]) -> None:
    with _conn() as conn:
        conn.execute(
            """UPDATE faq_items SET
               question_ro = ?, question_ru = ?, question_en = ?,
               answer_ro = ?, answer_ru = ?, answer_en = ?
               WHERE id = ?""",
            (
                data.get("question_ro", ""), data.get("question_ru", ""),
                data.get("question_en", ""),
                data.get("answer_ro", ""), data.get("answer_ru", ""),
                data.get("answer_en", ""), faq_id,
            ),
        )


def delete_faq_item(faq_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM faq_items WHERE id = ?", (faq_id,))


def seed_default_faq(conn=None) -> None:
    """Insert the default FAQ items if the table is empty (idempotent)."""
    if conn is None:
        with _conn() as conn:
            _seed(conn)
    else:
        _seed(conn)


def _seed(conn) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM faq_items").fetchone()["c"]
    if count > 0:
        return
    for i, item in enumerate(DEFAULT_FAQ):
        conn.execute(
            """INSERT INTO faq_items
               (sort_order, question_ro, question_ru, question_en,
                answer_ro, answer_ru, answer_en)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                i,
                item["question_ro"], item["question_ru"], item["question_en"],
                item["answer_ro"], item["answer_ru"], item["answer_en"],
            ),
        )
