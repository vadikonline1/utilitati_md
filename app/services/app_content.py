"""Server-driven app content for the mobile client.

Every user-facing string in the mobile app (labels, titles, empty states,
button texts, notification badge styles, the "new invoice" notification text)
is resolved from here. Admins edit the per-language values in the web
``/admin`` "Aplicație" tab; overrides are stored as flat settings keys
``app_<screen>_<flatkey>_<lang>`` and layered on top of the built-in defaults.
The app fetches the fully resolved config from ``GET /api/content?lang=...``
so changing copy on the website never requires an app build.

Placeholders like ``{home}`` / ``{value}`` are filled by the consumer
(server notification builder or the mobile client).
"""

from __future__ import annotations

from copy import deepcopy

from .settings import SETTING_KEYS, get_setting, set_settings

APP_LANGS = ("ro", "ru", "en")
DEFAULT_LANG = "ro"
PREFIX = "app_"


# --------------------------------------------------------------------------- #
# Built-in defaults (source of truth). If a localized default is missing the
# RO value is used, then admin overrides are layered on top.
# --------------------------------------------------------------------------- #
DEFAULTS: dict[str, dict[str, dict]] = {
    "ro": {
        "common": {
            "loading": "Se încarcă…",
            "cancel": "Anulează",
            "save": "Salvează",
            "delete": "Șterge",
            "edit": "Editează",
            "error_generic": "A apărut o eroare. Încearcă din nou.",
        },
        "dashboard": {
            "stat_unpaid_balance": "Sold total neachitat",
            "stat_open_invoices": "Facturi deschise",
            "stat_paid_invoices": "Facturi achitate",
            "stat_arrears": "Restanțe",
            "stat_homes": "Locuințe",
            "vezi": "vezi",
            "support": "Susține proiectul nostru",
            "empty": "Nu ai nicio locuință încă.",
            "fab_home": "Locuință",
            "fab_utility": "Utilitate",
            "error_load": "Nu s-au putut încărca datele.",
        },
        "homes": {
            "accounts_chip": "{count} conturi",
            "unpaid_chip": "{count} neplătite",
            "empty": "Nu ai nicio locuință încă.",
            "fab_home": "Locuință",
            "fab_utility": "Utilitate",
            "error_load": "Nu s-au putut încărca locuințele.",
        },
        "invoices": {
            "group_others": "Altele",
            "default_title": "Factură",
            "period": "Perioada {value}",
            "due": "Scadență {value}",
            "paid": "Plătită",
            "unpaid": "Neplătită",
            "empty": "Nicio factură disponibilă.",
            "error_load": "Nu s-au putut încărca facturile.",
            "delete_title": "Șterge factura",
            "delete_confirm": "Sigur vrei să ștergi această factură?",
            "error_save": "Operațiunea a eșuat.",
            "error_delete": "Ștergerea a eșuat.",
        },
        "notifications": {
            "title": "Notificări",
            "read_all": "Marchează toate ca citite",
            "empty": "Nicio notificare încă.",
            "default_title": "Notificare",
            "error_load": "Nu s-au putut încărca notificările.",
            "badge": {
                "invoice": {"label": "Factură", "color": "#16a34a"},
                "unpaid": {"label": "Neachitat", "color": "#f59e0b"},
                "admin": {"label": "Administrație", "color": "#dc2626"},
                "general": {"label": "General", "color": "#0d9488"},
                "other": {"label": "Altele", "color": "#0d9488"},
            },
            # "New invoice found" notification (bell + push), filled server-side.
            "new_invoice_title": "Factură nouă 🔔",
            "new_invoice_intro": "S-a găsit factură nouă:",
            "new_invoice_line": "• {home} · {utility} — {amount} MDL",
            "new_invoice_more": "+{count} facturi în plus",
            "new_invoice_total": "Total: {total} MDL",
        },
        "home_detail": {
            "contract": "Contract: {value}",
            "floor": "Etaj {value}",
            "status_active": "Activ",
            "status_disabled": "Dezactivat",
            "empty": "Niciun cont de utilități adăugat.",
            "error_load": "Nu s-au putut încărca datele.",
        },
        "account_detail": {
            "contract": "Contract: {value}",
            "location": "Loc: {value}",
            "refresh": "Actualizează facturi",
            "edit": "Editează",
            "invoices_title": "Facturi",
            "status_paid": "Plătită",
            "status_unpaid": "Neplătită",
            "status_unknown": "Necunoscută",
            "empty": "Nicio factură. Apasă „Actualizează facturi”.",
            "connect_error_title": "Nu s-a putut conecta",
            "connect_error_body": "Conectare eșuată la furnizor.",
            "refresh_done": "Facturile au fost actualizate. Sold neplătit: {unpaid} MDL.",
            "error_load": "Nu s-au putut încărca datele contului.",
            "error_save": "Actualizarea a eșuat.",
        },
        "home_form": {
            "title_new": "Locuință nouă",
            "title_edit": "Editează locuința",
            "label_name": "Nume *",
            "placeholder_name": "ex. Apartament 12",
            "label_address": "Adresă",
            "label_floor": "Etaj",
            "label_sector": "Sector",
            "warn_required_name": "Numele este obligatoriu.",
            "error_load": "Locuința nu a putut fi încărcată.",
            "error_save": "Salvarea a eșuat.",
        },
        "account_form": {
            "title_new": "Utilitate nouă",
            "title_edit": "Editează contul",
            "section_home": "Locuință *",
            "section_provider": "Furnizor *",
            "picker_provider": "Selectează furnizorul",
            "provider_label": "{icon} {name}",
            "provider_readonly": "Furnizorul nu poate fi schimbat după creare.",
            "label_contract": "Număr contract / identificator *",
            "empty_homes": "Nu ai nicio locuință. Creează întâi o locuință.",
            "warn_provider": "Selectează un furnizor.",
            "warn_contract": "Completează numărul de contract / identificatorul.",
            "warn_home": "Selectează locuința.",
            "modal_title": "Furnizor",
            "error_load": "Datele de formular nu au putut fi încărcate.",
            "error_save": "Salvarea a eșuat.",
        },
        "profile": {
            "name_label": "Nume, Prenume",
            "save_name": "Salvează numele",
            "name_saved": "Numele a fost salvat.",
            "settings": "Setări",
            "change_password": "Schimbă parola",
            "password_changed": "Parola a fost schimbată.",
            "language": "Limba platformei",
            "language_title": "Limba",
            "notifications": "Notificări",
            "notif_on": "Activat — primești notificări pentru facturi noi",
            "notif_off": "Dezactivat — fără notificări push",
            "notif_activated": "Ai activat notificările. Notificarea de test a fost trimisă.",
            "password_title": "Schimbă parola",
            "password_current": "Parola curentă",
            "password_new": "Parola nouă (min 6 caractere)",
            "password_confirm": "Confirmă parola",
            "password_warn_complete": "Completează parola curentă și cea nouă.",
            "password_warn_length": "Parola nouă trebuie să aibă minim 6 caractere.",
            "password_warn_mismatch": "Parolele nu coincid.",
            "deactivate": "Dezactivarea contului",
            "deactivate_title": "Dezactivare cont",
            "deactivate_confirm": "Sigur vrei să dezactivezi contul? Vei fi deconectat.",
            "deactivate_btn": "Dezactivează",
            "logout_btn": "Deconectează-te",
            "section_channel": "Canal de actualizare",
            "beta_desc": "Build din ramura deploy — actualizare directă, detectată după SHA-ul noului build",
            "version": "Versiune instalată: v{value}",
            "check_updates": "Verifică actualizări",
            "section_account": "Cont",
            "logout": "Deconectare",
            "up_to_date": "La zi",
            "update_manual_open": "Nu am putut descărca/instala APK-ul. Deschide fișierul apk-ului din GitHub release.",
        },
    },
    "ru": {
        "common": {
            "loading": "Загрузка…",
            "cancel": "Отмена",
            "save": "Сохранить",
            "delete": "Удалить",
            "edit": "Изменить",
            "error_generic": "Произошла ошибка. Попробуйте ещё раз.",
        },
        "dashboard": {
            "stat_unpaid_balance": "Неоплаченный остаток",
            "stat_open_invoices": "Открытые счета",
            "stat_paid_invoices": "Оплаченные счета",
            "stat_arrears": "Задолженность",
            "stat_homes": "Квартиры",
            "vezi": "смотреть",
            "support": "Поддержите наш проект",
            "empty": "У вас пока нет ни одной квартиры.",
            "fab_home": "Квартира",
            "fab_utility": "Коммунальная услуга",
            "error_load": "Не удалось загрузить данные.",
        },
        "homes": {
            "accounts_chip": "{count} счетов",
            "unpaid_chip": "{count} неоплачено",
            "empty": "У вас пока нет ни одной квартиры.",
            "fab_home": "Квартира",
            "fab_utility": "Коммунальная услуга",
            "error_load": "Не удалось загрузить квартиры.",
        },
        "invoices": {
            "group_others": "Прочие",
            "default_title": "Счёт",
            "period": "Период: {value}",
            "due": "Срок оплаты: {value}",
            "paid": "Оплачено",
            "unpaid": "Не оплачено",
            "empty": "Счетов пока нет.",
            "error_load": "Не удалось загрузить счета.",
            "delete_title": "Удалить счёт",
            "delete_confirm": "Вы уверены, что хотите удалить этот счёт?",
            "error_save": "Операция не удалась.",
            "error_delete": "Удаление не удалось.",
        },
        "notifications": {
            "title": "Уведомления",
            "read_all": "Отметить все как прочитанные",
            "empty": "Пока нет уведомлений.",
            "default_title": "Уведомление",
            "error_load": "Не удалось загрузить уведомления.",
            "badge": {
                "invoice": {"label": "Счёт", "color": "#16a34a"},
                "unpaid": {"label": "Не оплачено", "color": "#f59e0b"},
                "admin": {"label": "Администрация", "color": "#dc2626"},
                "general": {"label": "Общее", "color": "#0d9488"},
                "other": {"label": "Прочее", "color": "#0d9488"},
            },
            "new_invoice_title": "Новый счёт 🔔",
            "new_invoice_intro": "Обнаружен новый счёт:",
            "new_invoice_line": "• {home} · {utility} — {amount} MDL",
            "new_invoice_more": "+{count} счетов ещё",
            "new_invoice_total": "Итого: {total} MDL",
        },
        "home_detail": {
            "contract": "Договор: {value}",
            "floor": "Этаж {value}",
            "status_active": "Активен",
            "status_disabled": "Отключён",
            "empty": "Счёт коммунальных услуг не добавлен.",
            "error_load": "Не удалось загрузить данные.",
        },
        "account_detail": {
            "contract": "Договор: {value}",
            "location": "Место: {value}",
            "refresh": "Обновить счета",
            "edit": "Изменить",
            "invoices_title": "Счета",
            "status_paid": "Оплачено",
            "status_unpaid": "Не оплачено",
            "status_unknown": "Неизвестно",
            "empty": "Нет счетов. Нажмите «Обновить счета».",
            "connect_error_title": "Не удалось подключиться",
            "connect_error_body": "Не удалось подключиться к поставщику.",
            "refresh_done": "Счета обновлены. Неоплаченный остаток: {unpaid} MDL.",
            "error_load": "Не удалось загрузить данные счёта.",
            "error_save": "Обновление не удалось.",
        },
        "home_form": {
            "title_new": "Новая квартира",
            "title_edit": "Изменить квартиру",
            "label_name": "Название *",
            "placeholder_name": "напр. Квартира 12",
            "label_address": "Адрес",
            "label_floor": "Этаж",
            "label_sector": "Район",
            "warn_required_name": "Название обязательно.",
            "error_load": "Не удалось загрузить квартиру.",
            "error_save": "Не удалось сохранить.",
        },
        "account_form": {
            "title_new": "Новая коммунальная услуга",
            "title_edit": "Изменить счёт",
            "section_home": "Квартира *",
            "section_provider": "Поставщик *",
            "picker_provider": "Выберите поставщика",
            "provider_label": "{icon} {name}",
            "provider_readonly": "Поставщика нельзя изменить после создания.",
            "label_contract": "№ договора / идентификатор *",
            "empty_homes": "Нет ни одной квартиры. Сначала создайте квартиру.",
            "warn_provider": "Выберите поставщика.",
            "warn_contract": "Укажите № договора / идентификатор.",
            "warn_home": "Выберите квартиру.",
            "modal_title": "Поставщик",
            "error_load": "Не удалось загрузить данные формы.",
            "error_save": "Не удалось сохранить.",
        },
        "profile": {
            "name_label": "Имя, Фамилия",
            "save_name": "Сохранить имя",
            "name_saved": "Имя сохранено.",
            "settings": "Настройки",
            "change_password": "Сменить пароль",
            "password_changed": "Пароль изменён.",
            "language": "Язык платформы",
            "language_title": "Язык",
            "notifications": "Уведомления",
            "notif_on": "Включено — вы получаете уведомления о новых счетах",
            "notif_off": "Выключено — без push-уведомлений",
            "notif_activated": "Уведомления включены. Тестовое уведомление отправлено.",
            "password_title": "Сменить пароль",
            "password_current": "Текущий пароль",
            "password_new": "Новый пароль (мин. 6 символов)",
            "password_confirm": "Подтвердите пароль",
            "password_warn_complete": "Заполните текущий и новый пароль.",
            "password_warn_length": "Новый пароль должен быть не короче 6 символов.",
            "password_warn_mismatch": "Пароли не совпадают.",
            "deactivate": "Деактивация аккаунта",
            "deactivate_title": "Деактивация аккаунта",
            "deactivate_confirm": "Вы уверены, что хотите деактивировать аккаунт? Вы будете отключены.",
            "deactivate_btn": "Деактивировать",
            "logout_btn": "Выйти",
            "section_channel": "Канал обновлений",
            "beta_desc": "Сборка из ветки deploy — прямое обновление по SHA новой сборки",
            "version": "Установленная версия: v{value}",
            "check_updates": "Проверить обновления",
            "section_account": "Аккаунт",
            "logout": "Выйти",
            "up_to_date": "Актуально",
            "update_manual_open": "Не удалось скачать/установить APK. Откройте apk-файл из GitHub release.",
        },
    },
    "en": {
        "common": {
            "loading": "Loading…",
            "cancel": "Cancel",
            "save": "Save",
            "delete": "Delete",
            "edit": "Edit",
            "error_generic": "Something went wrong. Try again.",
        },
        "dashboard": {
            "stat_unpaid_balance": "Total unpaid",
            "stat_open_invoices": "Open bills",
            "stat_paid_invoices": "Paid bills",
            "stat_arrears": "Arrears",
            "stat_homes": "Homes",
            "vezi": "view",
            "support": "Support our project",
            "empty": "No homes yet.",
            "fab_home": "Home",
            "fab_utility": "Utility",
            "error_load": "Could not load data.",
        },
        "homes": {
            "accounts_chip": "{count} utilities",
            "unpaid_chip": "{count} unpaid",
            "empty": "No homes yet.",
            "fab_home": "Home",
            "fab_utility": "Utility",
            "error_load": "Could not load homes.",
        },
        "invoices": {
            "group_others": "Others",
            "default_title": "Invoice",
            "period": "Period {value}",
            "due": "Due {value}",
            "paid": "Paid",
            "unpaid": "Unpaid",
            "empty": "No invoices available.",
            "error_load": "Could not load invoices.",
            "delete_title": "Delete invoice",
            "delete_confirm": "Are you sure you want to delete this invoice?",
            "error_save": "Operation failed.",
            "error_delete": "Delete failed.",
        },
        "notifications": {
            "title": "Notifications",
            "read_all": "Mark all as read",
            "empty": "No notifications yet.",
            "default_title": "Notification",
            "error_load": "Could not load notifications.",
            "badge": {
                "invoice": {"label": "Invoice", "color": "#16a34a"},
                "unpaid": {"label": "Unpaid", "color": "#f59e0b"},
                "admin": {"label": "Admin", "color": "#dc2626"},
                "general": {"label": "General", "color": "#0d9488"},
                "other": {"label": "Other", "color": "#0d9488"},
            },
            "new_invoice_title": "New invoice 🔔",
            "new_invoice_intro": "A new invoice was found:",
            "new_invoice_line": "• {home} · {utility} — {amount} MDL",
            "new_invoice_more": "+{count} more invoices",
            "new_invoice_total": "Total: {total} MDL",
        },
        "home_detail": {
            "contract": "Contract: {value}",
            "floor": "Floor {value}",
            "status_active": "Active",
            "status_disabled": "Disabled",
            "empty": "No utility account added.",
            "error_load": "Could not load data.",
        },
        "account_detail": {
            "contract": "Contract: {value}",
            "location": "Location: {value}",
            "refresh": "Refresh invoices",
            "edit": "Edit",
            "invoices_title": "Invoices",
            "status_paid": "Paid",
            "status_unpaid": "Unpaid",
            "status_unknown": "Unknown",
            "empty": "No invoices. Tap “Refresh invoices”.",
            "connect_error_title": "Could not connect",
            "connect_error_body": "Connection to provider failed.",
            "refresh_done": "Invoices updated. Unpaid balance: {unpaid} MDL.",
            "error_load": "Could not load account data.",
            "error_save": "Update failed.",
        },
        "home_form": {
            "title_new": "New home",
            "title_edit": "Edit home",
            "label_name": "Name *",
            "placeholder_name": "e.g. Apartment 12",
            "label_address": "Address",
            "label_floor": "Floor",
            "label_sector": "Sector",
            "warn_required_name": "Name is required.",
            "error_load": "Could not load the home.",
            "error_save": "Save failed.",
        },
        "account_form": {
            "title_new": "New utility",
            "title_edit": "Edit account",
            "section_home": "Home *",
            "section_provider": "Provider *",
            "picker_provider": "Select provider",
            "provider_label": "{icon} {name}",
            "provider_readonly": "Provider cannot be changed after creation.",
            "label_contract": "Contract number / identifier *",
            "empty_homes": "No homes yet. Create a home first.",
            "warn_provider": "Select a provider.",
            "warn_contract": "Fill in the contract number / identifier.",
            "warn_home": "Select a home.",
            "modal_title": "Provider",
            "error_load": "Could not load form data.",
            "error_save": "Save failed.",
        },
        "profile": {
            "name_label": "First, Last name",
            "save_name": "Save name",
            "name_saved": "Name saved.",
            "settings": "Settings",
            "change_password": "Change password",
            "password_changed": "Password changed.",
            "language": "Platform language",
            "language_title": "Language",
            "notifications": "Notifications",
            "notif_on": "On — you get notified about new invoices",
            "notif_off": "Off — no push notifications",
            "notif_activated": "Notifications enabled. Test notification sent.",
            "password_title": "Change password",
            "password_current": "Current password",
            "password_new": "New password (min 6 chars)",
            "password_confirm": "Confirm password",
            "password_warn_complete": "Fill in the current and new password.",
            "password_warn_length": "New password must be at least 6 characters.",
            "password_warn_mismatch": "Passwords do not match.",
            "deactivate": "Deactivate account",
            "deactivate_title": "Deactivate account",
            "deactivate_confirm": "Are you sure you want to deactivate your account? You will be logged out.",
            "deactivate_btn": "Deactivate",
            "logout_btn": "Log out",
            "section_channel": "Update channel",
            "beta_desc": "Build from the deploy branch — direct update, detected by the new build SHA",
            "version": "Installed version: v{value}",
            "check_updates": "Check updates",
            "section_account": "Account",
            "logout": "Log out",
            "up_to_date": "Up to date",
            "update_manual_open": "Could not download/install the APK. Open the apk file from the GitHub release.",
        },
    },
}


# --------------------------------------------------------------------------- #
# Admin editor schema: which fields exist per screen (path, control, label).
# "Path" is the same dotted key used at runtime; it doubles as the settings
# suffix with dots replaced by underscores.
# --------------------------------------------------------------------------- #
SCREENS = (
    "dashboard",
    "homes",
    "invoices",
    "notifications",
    "home_detail",
    "account_detail",
    "home_form",
    "account_form",
    "profile",
)

SCREEN_META = {
    "dashboard": {
        "title": "Dashboard · afișări",
        "hint": "Statisticile principale și lista locuințelor de pe prima pagină.",
    },
    "homes": {"title": "Locuințe", "hint": "Lista locuințelor (ecran Locuințe)."},
    "invoices": {"title": "Facturi", "hint": "Lista facturilor (ecran Facturi)."},
    "notifications": {
        "title": "Notificări",
        "hint": "Ecranul clopotel + textul notificării „factură nouă” (clopot/push).",
    },
    "home_detail": {"title": "Locuință · detaliu", "hint": "Detalii locuință și conturi."},
    "account_detail": {"title": "Cont · detaliu", "hint": "Detalii cont + facturi."},
    "home_form": {"title": "Formular locuință", "hint": "Formular creare/editare locuință."},
    "account_form": {"title": "Formular cont", "hint": "Formular creare/editare cont utilitate."},
    "profile": {"title": "Profil", "hint": "Ecranul Profil / setări."},
}

# (_SCREENS that are not editable in admin "Aplicație" but still resolved for
#  the app — the "common" strings are always RO/install defaults.)
_COMMON_FIELDS = (
    ("loading", "text", "Se încarcă…"),
    ("cancel", "text", "Anulează"),
    ("save", "text", "Salvează"),
    ("delete", "text", "Șterge"),
    ("edit", "text", "Editează"),
    ("error_generic", "text", "Eroare generică"),
)

FIELDS: dict[str, list[tuple[str, str, str]]] = {
    "dashboard": [
        ("stat_unpaid_balance", "text", "Sold total neachitat"),
        ("stat_open_invoices", "text", "Facturi deschise"),
        ("stat_paid_invoices", "text", "Facturi achitate"),
        ("stat_arrears", "text", "Restanțe"),
        ("stat_homes", "text", "Locuințe"),
        ("vezi", "text", "„vezi”"),
        ("support", "text", "Buton susținere"),
        ("empty", "text", "Text gol (fără locuințe)"),
        ("fab_home", "text", "Meniu FAB: Locuință"),
        ("fab_utility", "text", "Meniu FAB: Utilitate"),
        ("error_load", "text", "Eroare la încărcare"),
    ],
    "homes": [
        ("accounts_chip", "text", "Chip conturi ({count})"),
        ("unpaid_chip", "text", "Chip neplătite ({count})"),
        ("empty", "text", "Text gol"),
        ("fab_home", "text", "Meniu FAB: Locuință"),
        ("fab_utility", "text", "Meniu FAB: Utilitate"),
        ("error_load", "text", "Eroare la încărcare"),
    ],
    "invoices": [
        ("group_others", "text", "Segment „Altele”"),
        ("default_title", "text", "Titlu implicit factură"),
        ("period", "text", "Perioada ({value})"),
        ("due", "text", "Scadență ({value})"),
        ("paid", "text", "Status plătită"),
        ("unpaid", "text", "Status neplătită"),
        ("empty", "text", "Text gol"),
        ("error_load", "text", "Eroare la încărcare"),
        ("delete_title", "text", "Titlu dialog ștergere"),
        ("delete_confirm", "text", "Confirmare ștergere"),
        ("error_save", "text", "Eroare operațiune"),
        ("error_delete", "text", "Eroare ștergere"),
    ],
    "notifications": [
        ("title", "text", "Titlu pagină"),
        ("read_all", "text", "Marchează toate citite"),
        ("empty", "text", "Text gol"),
        ("default_title", "text", "Titlu implicit notificare"),
        ("error_load", "text", "Eroare la încărcare"),
        ("badge.invoice.label", "text", "Tip „Factură” — etichetă"),
        ("badge.invoice.color", "color", "Tip „Factură” — culoare"),
        ("badge.unpaid.label", "text", "Tip „Neachitat” — etichetă"),
        ("badge.unpaid.color", "color", "Tip „Neachitat” — culoare"),
        ("badge.admin.label", "text", "Tip „Administrație” — etichetă"),
        ("badge.admin.color", "color", "Tip „Administrație” — culoare"),
        ("badge.general.label", "text", "Tip „General” — etichetă"),
        ("badge.general.color", "color", "Tip „General” — culoare"),
        ("badge.other.label", "text", "Tip „Altele” — etichetă"),
        ("badge.other.color", "color", "Tip „Altele” — culoare"),
        ("new_invoice_title", "text", "Clopot/push: titlu factură nouă"),
        ("new_invoice_intro", "text", "Clopot/push: text intro"),
        ("new_invoice_line", "text", "Clopot/push: linie ({home},{utility},{amount})"),
        ("new_invoice_more", "text", "Clopot/push: la mai multe facturi ({count})"),
        ("new_invoice_total", "text", "Clopot/push: total ({total})"),
    ],
    "home_detail": [
        ("contract", "text", "Contract ({value})"),
        ("floor", "text", "Etaj ({value})"),
        ("status_active", "text", "Status activ"),
        ("status_disabled", "text", "Status dezactivat"),
        ("empty", "text", "Text gol"),
        ("error_load", "text", "Eroare la încărcare"),
    ],
    "account_detail": [
        ("contract", "text", "Contract ({value})"),
        ("location", "text", "Loc ({value})"),
        ("refresh", "text", "Buton actualizare"),
        ("edit", "text", "Buton editare"),
        ("invoices_title", "text", "Titlu listă facturi"),
        ("status_paid", "text", "Status plătită"),
        ("status_unpaid", "text", "Status neplătită"),
        ("status_unknown", "text", "Status necunoscută"),
        ("empty", "text", "Text gol"),
        ("connect_error_title", "text", "Eroare conectare — titlu"),
        ("connect_error_body", "text", "Eroare conectare — conținut"),
        ("refresh_done", "text", "După actualizare ({unpaid})"),
        ("error_load", "text", "Eroare la încărcare"),
        ("error_save", "text", "Eroare actualizare"),
    ],
    "home_form": [
        ("title_new", "text", "Titlu creare"),
        ("title_edit", "text", "Titlu editare"),
        ("label_name", "text", "Etichetă Nume"),
        ("placeholder_name", "text", "Placeholder nume"),
        ("label_address", "text", "Etichetă Adresă"),
        ("label_floor", "text", "Etichetă Etaj"),
        ("label_sector", "text", "Etichetă Sector"),
        ("warn_required_name", "text", "Avertisment nume obligatoriu"),
        ("error_load", "text", "Eroare la încărcare"),
        ("error_save", "text", "Eroare salvare"),
    ],
    "account_form": [
        ("title_new", "text", "Titlu creare"),
        ("title_edit", "text", "Titlu editare"),
        ("section_home", "text", "Secțiune Locuință"),
        ("section_provider", "text", "Secțiune Furnizor"),
        ("picker_provider", "text", "Placeholder furnizor"),
        ("provider_label", "text", "Format furnizor ({icon},{name})"),
        ("provider_readonly", "text", "Notă furnizor fix"),
        ("label_contract", "text", "Etichetă contract"),
        ("empty_homes", "text", "Fără locuințe"),
        ("warn_provider", "text", "Avertisment furnizor"),
        ("warn_contract", "text", "Avertisment contract"),
        ("warn_home", "text", "Avertisment locuință"),
        ("modal_title", "text", "Titlu modal furnizor"),
        ("error_load", "text", "Eroare la încărcare"),
        ("error_save", "text", "Eroare salvare"),
    ],
    "profile": [
        ("name_label", "text", "Etichetă nume"),
        ("save_name", "text", "Buton salvare nume"),
        ("name_saved", "text", "Nume salvat"),
        ("settings", "text", "Secțiune Setări"),
        ("change_password", "text", "Schimbă parola"),
        ("password_changed", "text", "Parolă schimbată"),
        ("language", "text", "Limba platformei"),
        ("language_title", "text", "Titlu alegere limbă"),
        ("notifications", "text", "Notificări"),
        ("notif_on", "text", "Stare activată"),
        ("notif_off", "text", "Stare dezactivată"),
        ("notif_activated", "text", "Notificări activate"),
        ("password_title", "text", "Titlu modal parolă"),
        ("password_current", "text", "Placeholder parola curentă"),
        ("password_new", "text", "Placeholder parola nouă"),
        ("password_confirm", "text", "Placeholder confirmare"),
        ("password_warn_complete", "text", "Avertisment completare"),
        ("password_warn_length", "text", "Avertisment lungime"),
        ("password_warn_mismatch", "text", "Avertisment necoincidență"),
        ("deactivate", "text", "Dezactivare cont"),
        ("deactivate_title", "text", "Titlu dialog dezactivare"),
        ("deactivate_confirm", "text", "Confirmare dezactivare"),
        ("deactivate_btn", "text", "Buton dezactivare"),
        ("logout_btn", "text", "Buton deconectare"),
        ("section_channel", "text", "Secțiune canal"),
        ("beta_desc", "text", "Descriere canal Beta"),
        ("version", "text", "Versiune ({value})"),
        ("check_updates", "text", "Verifică actualizări"),
        ("section_account", "text", "Secțiune Cont"),
        ("logout", "text", "Deconectare"),
        ("up_to_date", "text", "La zi"),
        ("update_manual_open", "text", "Eroare deschidere APK"),
    ],
}


def _setting_suffix(path: str, lang: str) -> str:
    return f"{path.replace('.', '_')}_{lang}"


def _setting_key(screen: str, path: str, lang: str) -> str:
    return f"{PREFIX}{screen}_{_setting_suffix(path, lang)}"


def register_setting_keys() -> None:
    for screen, fields in FIELDS.items():
        for path, _control, _label in fields:
            for lang in APP_LANGS:
                SETTING_KEYS.add(_setting_key(screen, path, lang))


register_setting_keys()


def _set_nested(obj: dict, path: str, value: str) -> None:
    parts = path.split(".")
    cursor = obj
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = value


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def resolve_screen(screen: str, lang: str) -> dict:
    """Resolve one screen for a language: localized default + admin overrides."""
    base = deepcopy(DEFAULTS[DEFAULT_LANG].get(screen, {}))
    localized = DEFAULTS.get(lang, {}).get(screen, {})
    out = _deep_merge(base, localized)
    for path, _control, _label in FIELDS.get(screen, []):
        stored = get_setting(_setting_key(screen, path, lang), "").strip()
        if stored:
            _set_nested(out, path, stored)
    return out


def resolve_content(lang: str = DEFAULT_LANG) -> dict:
    """Full config for the app: { 'lang': <resolved>, 'screens': {screen: {...}} }."""
    if lang not in APP_LANGS:
        lang = DEFAULT_LANG
    screens = {n: resolve_screen(n, lang) for n in SCREENS}
    screens["common"] = deepcopy(DEFAULTS[DEFAULT_LANG]["common"])
    localized_common = DEFAULTS.get(lang, {}).get("common", {})
    if localized_common:
        screens["common"] = _deep_merge(screens["common"], localized_common)
    return {"lang": lang, "screens": screens}


def _default_at(lang: str, screen: str, path: str) -> str:
    cursor = DEFAULTS.get(lang, {}).get(screen, {})
    for part in path.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return ""
        cursor = cursor[part]
    return str(cursor or "")


# --------------------------------------------------------------------------- #
# Admin editor data
# --------------------------------------------------------------------------- #
def admin_editor() -> list[dict]:
    """[{screen, title, hint, fields:[{path, control, label, values:{lang}}]}]."""
    result = []
    for screen in SCREENS:
        fields = []
        for path, control, label in FIELDS[screen]:
            values = {}
            for lang in APP_LANGS:
                default = _default_at(DEFAULT_LANG, screen, path)
                localized = _default_at(lang, screen, path)
                values[lang] = get_setting(_setting_key(screen, path, lang), "") \
                    or localized or default
            fields.append({"path": path, "control": control, "label": label, "values": values})
        result.append({"screen": screen, **SCREEN_META[screen], "fields": fields})
    return result


def save_screen(screen: str, form_values: dict[str, str]) -> int:
    """Persist submitted app_<screen>_* fields (empty = reset to default).

    ``form_values`` maps the settings key -> submitted value.
    Returns how many keys were written.
    """
    prefix = f"{PREFIX}{screen}_"
    values = {}
    for raw_key, raw_value in form_values.items():
        key = raw_key.strip()
        if not key.startswith(prefix):
            continue
        values[key] = str(raw_value).strip()
    set_settings(values)
    return len(values)


def reset_screen(screen: str) -> int:
    """Remove admin overrides for a screen so built-in defaults are used again."""
    prefix = f"{PREFIX}{screen}_"
    values = {}
    for path, _control, _label in FIELDS.get(screen, []):
        for lang in APP_LANGS:
            values[_setting_key(screen, path, lang)] = ""
    set_settings(values)
    return len(values)


def localized_string(screen: str, path: str, lang: str) -> str:
    """Runtime helper (server side) for a single content string, e.g. the
    'new invoice' notification text. Falls back to RO default."""
    resolved = resolve_screen(screen, lang)
    parts = path.split(".")
    cursor = resolved
    for part in parts:
        if not isinstance(cursor, dict) or part not in cursor:
            fallback = DEFAULTS[DEFAULT_LANG].get(screen, {})
            for p in parts:
                if not isinstance(fallback, dict) or p not in fallback:
                    return ""
                fallback = fallback[p]
            return str(fallback or "")
        cursor = cursor[part]
    return str(cursor or "")