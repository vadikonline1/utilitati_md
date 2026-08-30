"""Database-backed content pages, editable by admins from /admin?tab=pages.

Each page has a unique slug (used in the URL) and title/content for ro/ru/en.
Content is stored as HTML so admins can include headings, lists, tables and
links. Built-in pages (privacy, contact, about) are seeded on first run and can
be edited but not deleted; their content may use placeholders that are filled
at render time from the company / SEO settings:

    {company_name} {company_email} {company_address} {site} {contact} {privacy}
"""

from __future__ import annotations

import re
from typing import Any

from ..db import _conn

LANGS = ("ro", "ru", "en")

PLACEHOLDERS = "{company_name} {company_email} {company_address} {site} {contact} {privacy}"


def slugify(text: str) -> str:
    """Turn free text into a URL-safe slug (lowercase, dashes)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower().strip())
    return slug.strip("-") or "page"


def list_pages() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pages ORDER BY is_builtin DESC, slug"
        ).fetchall()
    return [dict(r) for r in rows]


def get_page(slug: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM pages WHERE slug = ?", (slug,)
        ).fetchone()
    return dict(row) if row else None


def get_page_by_id(page_id: int) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM pages WHERE id = ?", (page_id,)
        ).fetchone()
    return dict(row) if row else None


def page_exists(slug: str) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT id FROM pages WHERE slug = ?", (slug,)).fetchone()
    return row is not None


def add_page(data: dict[str, str]) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO pages
               (slug, title_ro, title_ru, title_en,
                content_ro, content_ru, content_en,
                meta_title, meta_description, is_builtin)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                data["slug"],
                data.get("title_ro", ""), data.get("title_ru", ""),
                data.get("title_en", ""),
                data.get("content_ro", ""), data.get("content_ru", ""),
                data.get("content_en", ""),
                data.get("meta_title", ""), data.get("meta_description", ""),
            ),
        )
        return cur.lastrowid


def update_page(page_id: int, data: dict[str, str]) -> None:
    with _conn() as conn:
        conn.execute(
            """UPDATE pages SET
               slug = ?, title_ro = ?, title_ru = ?, title_en = ?,
               content_ro = ?, content_ru = ?, content_en = ?,
               meta_title = ?, meta_description = ?,
               updated_at = datetime('now')
               WHERE id = ?""",
            (
                data["slug"],
                data.get("title_ro", ""), data.get("title_ru", ""),
                data.get("title_en", ""),
                data.get("content_ro", ""), data.get("content_ru", ""),
                data.get("content_en", ""),
                data.get("meta_title", ""), data.get("meta_description", ""),
                page_id,
            ),
        )


def delete_page(page_id: int) -> None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT is_builtin FROM pages WHERE id = ?", (page_id,)
        ).fetchone()
        if row and not row["is_builtin"]:
            conn.execute("DELETE FROM pages WHERE id = ?", (page_id,))


def render_content(content: str, tokens: dict[str, str]) -> str:
    """Replace {placeholder} tokens in page content with live values."""
    out = content or ""
    for key, value in tokens.items():
        out = out.replace("{" + key + "}", value or "")
    return out


# --------------------------------------------------------------------------- #
# Built-in pages seeded on first run (editable, but not deletable).
# Tokens like {company_name} / {company_email} are filled from /admin settings.
# --------------------------------------------------------------------------- #
DEFAULT_PAGES: list[dict[str, str]] = [
    {
        "slug": "privacy",
        "is_builtin": "1",
        "title_ro": "Politica de confidențialitate și GDPR",
        "title_ru": "Политика конфиденциальности и GDPR",
        "title_en": "Privacy policy & GDPR",
        "content_ro": """
<h2>1. Cine suntem</h2>
<p>UTILITĂȚI.MD este o platformă digitală destinată gestionării centralizate a
facturilor și informațiilor despre utilitățile utilizatorilor din Republica
Moldova. Platforma te ajută să urmărești și să organizezi facturile pentru
electricitate, gaze, apă, internet și alte servicii, totul dintr-un singur cont.</p>
<ul>
  <li><b>Operatorul platformei:</b> {company_name}</li>
  <li><b>Email oficial / cereri GDPR:</b> {company_email}</li>
  <li><b>Adresă juridică:</b> {company_address}</li>
  <li><b>Site:</b> {site}</li>
</ul>
<p>În sensul Regulamentului (UE) 2016/679 („GDPR”) și al Legii nr. 133/2011 privind
protecția datelor cu caracter personal (Republica Moldova), operatorul de date este
entitatea care administrează platforma și care decide în ce scop și prin ce mijloace
sunt prelucrate datele tale.</p>

<h2>2. Ce oferă concret platforma</h2>
<p>Serviciile UTILITĂȚI.MD:</p>
<ul>
  <li><b>Centralizarea utilităților</b> — adaugi toate utilitățile într-un singur cont;</li>
  <li><b>Gestionarea facturilor</b> — păstrezi evidența facturilor și a perioadelor de plată;</li>
  <li><b>Monitorizarea sumelor</b> — vezi ce facturi sunt emise și care rămân neachitate;</li>
  <li><b>Notificări automate</b> — primești o notificare când apare o factură nouă sau ai facturi neachitate;</li>
  <li><b>Istoricul facturilor</b> — poți verifica facturile anterioare;</li>
  <li><b>Gestionarea mai multor locuințe</b> — apartament, casă, chirie, părinți etc.;</li>
  <li><b>Mai multe tipuri de utilități</b> — electricitate, gaze, apă, internet și alte servicii compatibile;</li>
  <li><b>Un singur cont</b> — nu mai urmărești separat fiecare furnizor.</li>
</ul>

<h2>3. Ce NU este UTILITĂȚI.MD</h2>
<p>Pentru claritate, platforma:</p>
<ul>
  <li>nu este furnizor de energie electrică, gaze sau apă;</li>
  <li>nu emite facturile furnizorilor și nu modifică tarifele acestora;</li>
  <li>nu înlocuiește conturile oficiale ale furnizorilor;</li>
  <li>nu este o autoritate publică;</li>
  <li>nu achită facturile în numele tău — plata se face de către tine, direct către furnizor, prin platforma oficială a acestuia (de exemplu oplata.md).</li>
</ul>

<h2>4. Ce date colectăm</h2>
<p>Colectăm și prelucrăm doar datele necesare pentru funcționarea serviciului
(temei juridic: executarea contractului de utilizare, interes legitim sau,
acolo unde este cazul, consimțământul tău):</p>
<ul>
  <li><b>Date de cont:</b> nume, prenume, adresă de email și nume de utilizator; parolele nu se stochează în clar — se păstrează doar sub formă de hash criptografic;</li>
  <li><b>Informații despre locuințe:</b> denumire, adresă și, opțional, etaj sau zonă;</li>
  <li><b>Date de conectare la utilități:</b> furnizori, numere de contract sau cont personal; opțional, acreditările portalului furnizorului — stocate <b>criptate</b> și folosite exclusiv pentru citirea facturilor; le poți elimina oricând;</li>
  <li><b>Date despre facturi:</b> număr, sumă, perioadă, termen de plată, status de plată;</li>
  <li><b>Preferințe de notificare:</b> adrese de email suplimentare și ID-uri Telegram — stocate criptat;</li>
  <li><b>Date tehnice:</b> adresa IP, date de utilizare și identificatorii browserului, folosite exclusiv pentru securitate, funcționare și diagnosticare.</li>
</ul>

<h2>5. Securitatea datelor</h2>
<p>Luăm măsuri tehnice și organizatorice adecvate pentru protejarea datelor tale:</p>
<ul>
  <li><b>În tranzit:</b> toate conexiunile către platformă au loc prin HTTPS (transport criptat);</li>
  <li><b>La stocare:</b> parolele de utilizator sunt păstrate sub formă de hash (PBKDF2-HMAC); acreditările portalurilor furnizorilor, adresele suplimentare de notificare și ID-urile Telegram sunt criptate (cifru AES) cu o cheie ce nu se află în baza de date;</li>
  <li><b>Acces:</b> administratorii tehnici nu pot vizualiza conținutul decriptat al datelor tale; accesul la datele de gestionare este protejat prin autentificare.</li>
</ul>
<p>În cazul unui incident de securitate care ar putea afecta datele personale, vom
anunța utilizatorii afectați conform obligațiilor legale aplicabile.</p>

<h2>6. Date pe care NU le solicităm</h2>
<p>Platforma nu solicită și nu stochează date care nu sunt necesare funcționării
serviciului. Nu colectăm:</p>
<ul>
  <li>numere de card bancar, CVV sau alte date bancare;</li>
  <li>autentificări la platforme care nu au legătură cu utilitățile conectate;</li>
  <li>istoricul de navigare, locația GPS ori datele de contact din agenda ta.</li>
</ul>

<h2>7. Cine are acces la facturile mele?</h2>
<p>Facturile și datele asociate contului tău sunt accesibile doar contului tău și
sunt procesate automat de sistem exclusiv pentru funcționarea serviciului:
sincronizarea, calculul soldurilor și notificările. Personalul care administrează
tehnic serviciul nu are acces la conținutul decriptat al datelor; celelalte
persoane nu le pot vizualiza în niciun mod. Nu vindem și nu partajăm datele tale
cu terți pentru scopuri comerciale sau de publicitate.</p>

<h2>8. Cât timp păstrăm datele (retenție)</h2>
<table class="retention">
  <thead><tr><th>Tip de date</th><th>Perioada de păstrare</th></tr></thead>
  <tbody>
    <tr><td>Cont utilizator activ</td><td>Pe durata de existență a contului</td></tr>
    <tr><td>Facturi</td><td>Maximum 24 de luni, apoi ștergere automată</td></tr>
    <tr><td>Cont neconfirmat (emailul nu a fost validat)</td><td>Ștergere automată după un interval scurt</td></tr>
    <tr><td>Cont dezactivat de utilizator</td><td>Ștergere definitivă după 30 de zile</td></tr>
    <tr><td>Cont inactiv (fără autentificare)</td><td>Ștergere după 12 luni, precedată de emailuri de avertisment</td></tr>
  </tbody>
</table>
<p>„Ștergere definitivă” înseamnă că datele, inclusiv facturile și preferințele,
nu mai pot fi accesate sau recuperate prin mijloace normale.</p>

<h2>9. Cookie-uri și tehnologii similare</h2>
<p>Platforma folosește doar cookie-uri strict necesare funcționării:</p>
<ul>
  <li><b>cookie de sesiune/autentificare</b> — te ține autentificat în cont;</li>
  <li><b>cookie de limbă</b> — reține limba aleasă;</li>
  <li><b>stocare locală (localStorage)</b> — tema clară/întunecată și confirmarea bannerului de cookie-uri.</li>
</ul>
<p>Nu folosim cookie-uri de publicitate, de analiză sau de urmărire ale terților.
Pentru bannerul de cookie-uri și mai multe detalii, vezi secțiunea <a href="{privacy}">Confidențialitate</a>.
Poți oricând șterge cookie-urile și datele locale din setările browserului tău.</p>

<h2>10. Furnizori terți care ne ajută să operăm serviciul</h2>
<p>Pentru funcționarea platformei putem utiliza furnizori specializați, cărora le
oferim exclusiv datele necesare scopului respectiv:</p>
<ul>
  <li><b>găzduire / hosting</b> — pentru rularea serviciului și stocarea bazei de date;</li>
  <li><b>serviciu de email (SMTP)</b> — pentru trimiterea notificărilor și emailurilor oficiale;</li>
  <li><b>Telegram</b> — pentru notificările trimise prin bot atunci când alegi această opțiune.</li>
</ul>
<p>Datele sunt prelucrate de terți doar în măsura necesară prestării serviciului
și în conformitate cu acorduri adecvate de protecție a datelor.</p>

<h2>11. Drepturile tale</h2>
<p>Ai dreptul, în condițiile legislației aplicabile, să:</p>
<ul>
  <li>soliciți <b>accesul</b> la datele tale personale;</li>
  <li>soliciți <b>rectificarea</b> datelor incorecte;</li>
  <li>soliciți <b>ștergerea</b> datelor;</li>
  <li>soliciți <b>exportul datelor</b> (portabilitate);</li>
  <li>soliciți <b>restricționarea</b> prelucrării;</li>
  <li>te <b>opui</b> anumitor forme de prelucrare;</li>
  <li><b>retragi consimțământul</b> atunci când prelucrarea se bazează pe consimțământ (de exemplu, notificările — din pagina Profil);</li>
  <li>depui o <b>plângere</b> la Centrul Național pentru Protecția Datelor cu Caracter Personal (Republica Moldova) sau la autoritatea competentă din țara ta.</li>
</ul>
<p><b>Cum faci asta?</b> Folosește <a href="{contact}">pagina de contact</a> și
alege subiectul <b>„GDPR — Solicitare date”</b>, ori scrie-ne la {company_email}
cu același subiect. Răspundem de regulă în maximum 30 de zile.</p>

<h2>12. Temeiuri juridice</h2>
<p>Prelucrăm datele personale pe următoarele temeiuri: executarea contractului
de utilizare a serviciului (crearea contului, conectarea utilităților, generarea
notificărilor), consimțământul tău (notificările, acolo unde e cazul), interesul
legitim (securitate, prevenirea abuzului, menținerea evidențelor tehnice) și
obligațiile legale care ne incumbă. Simpla utilizare a platformei nu reprezintă
un consimțământ automat pentru toate prelucrările: notificările sunt opționale
și le poți configura în cont.</p>

<h2>13. Modificări ale politicii</h2>
<p>Este posibil să actualizăm această politică. Versiunea curentă este publicată
pe această pagină, iar modificările importante sunt aduse la cunoștința ta prin
platformă (email sau notificare).</p>

<h2>14. Contact</h2>
<p>Pentru orice întrebare privind datele sau această politică, folosește
<a href="{contact}">pagina de contact</a> sau scrie-ne la {company_email}.</p>
""",
        "content_ru": """
<h2>1. Кто мы</h2>
<p>UTILITĂȚI.MD — это цифровая платформа для централизованного управления
счетами и информацией о коммунальных услугах пользователей из Республики
Молдова. Платформа помогает отслеживать и организовывать счета за
электричество, газ, воду, интернет и другие услуги — всё в одном аккаунте.</p>
<ul>
  <li><b>Оператор платформы:</b> {company_name}</li>
  <li><b>Официальная почта / GDPR-запросы:</b> {company_email}</li>
  <li><b>Юридический адрес:</b> {company_address}</li>
  <li><b>Сайт:</b> {site}</li>
</ul>
<p>В соответствии с Регламентом (ЕС) 2016/679 („GDPR”) и Законом № 133/2011 о
защите персональных данных (Республика Молдова), оператором данных является
организация, которая управляет платформой и определяет цели и способы
обработки ваших данных.</p>

<h2>2. Что конкретно предлагает платформа</h2>
<ul>
  <li><b>Централизация услуг</b> — все коммунальные услуги в одном аккаунте;</li>
  <li><b>Управление счетами</b> — учёт счетов и периодов оплаты;</li>
  <li><b>Контроль сумм</b> — видно, какие счета выставлены и какие не оплачены;</li>
  <li><b>Автоматические уведомления</b> — при появлении нового счёта или наличии неоплаченных счетов;</li>
  <li><b>История счетов</b> — можно проверить предыдущие счета;</li>
  <li><b>Несколько объектов недвижимости</b> — квартира, дом, аренда, родители и т.д.;</li>
  <li><b>Разные виды услуг</b> — электричество, газ, вода, интернет и другие;</li>
  <li><b>Один аккаунт</b> — не нужно следить за каждым поставщиком отдельно.</li>
</ul>

<h2>3. Чем НЕ является UTILITĂȚI.MD</h2>
<ul>
  <li>не является поставщиком электроэнергии, газа или воды;</li>
  <li>не выставляет счета поставщиков и не меняет их тарифы;</li>
  <li>не заменяет официальные кабинеты поставщиков;</li>
  <li>не является государственным органом;</li>
  <li>не оплачивает счета от вашего имени — оплата производится вами напрямую поставщику через его официальную платформу (например, oplata.md).</li>
</ul>

<h2>4. Какие данные мы собираем</h2>
<ul>
  <li><b>Данные аккаунта:</b> имя, фамилия, email и логин; пароли не хранятся в открытом виде — только в виде криптографического хеша;</li>
  <li><b>Информация о недвижимости:</b> название, адрес и, опционально, этаж/зона;</li>
  <li><b>Данные подключения услуг:</b> поставщики, номера договоров или лицевых счетов; при желании — учётные данные портала поставщика, хранящиеся <b>в зашифрованном виде</b> для чтения счетов; их можно удалить в любой момент;</li>
  <li><b>Данные о счетах:</b> номер, сумма, период, срок оплаты, статус оплаты;</li>
  <li><b>Настройки уведомлений:</b> дополнительные email-адреса и Telegram ID — в зашифрованном виде;</li>
  <li><b>Технические данные:</b> IP-адрес, данные использования и идентификаторы браузера — только для безопасности, работы и диагностики.</li>
</ul>

<h2>5. Безопасность данных</h2>
<ul>
  <li><b>При передаче:</b> все соединения выполняются по HTTPS (шифрованный транспорт);</li>
  <li><b>При хранении:</b> пароли пользователей хранятся в виде хеша (PBKDF2-HMAC); учётные данные порталов поставщиков, дополнительные email и Telegram ID зашифрованы (AES) ключом, который не находится в базе данных;</li>
  <li><b>Доступ:</b> технические администраторы не могут просматривать расшифрованные данные; доступ к управлению защищён аутентификацией.</li>
</ul>
<p>В случае инцидента, который может затронуть персональные данные, мы уведомим
пострадавших пользователей в соответствии с применимыми требованиями.</p>

<h2>6. Какие данные мы НЕ запрашиваем</h2>
<ul>
  <li>номера банковских карт, CVV или другие банковские данные;</li>
  <li>логины к платформам, не связанным с подключёнными услугами;</li>
  <li>историю браузера, GPS-координаты или контакты из вашей адресной книги.</li>
</ul>

<h2>7. Кто имеет доступ к моим счетам?</h2>
<p>Счета и связанные данные доступны только вашему аккаунту и обрабатываются
системой автоматически исключительно для работы сервиса. Технический персонал
не имеет доступа к расшифрованным данным; посторонние лица не могут их
просматривать никаким образом. Мы не продаём и не передаём ваши данные третьим
лицам в коммерческих или рекламных целях.</p>

<h2>8. Хранение данных (ретенция)</h2>
<table class="retention">
  <thead><tr><th>Тип данных</th><th>Срок хранения</th></tr></thead>
  <tbody>
    <tr><td>Активный аккаунт пользователя</td><td>В течение всего срока существования аккаунта</td></tr>
    <tr><td>Счета</td><td>Максимум 24 месяца, затем автоматическое удаление</td></tr>
    <tr><td>Неподтверждённый аккаунт</td><td>Автоматическое удаление через короткий срок</td></tr>
    <tr><td>Деактивированный пользователем аккаунт</td><td>Безвозвратное удаление через 30 дней</td></tr>
    <tr><td>Неактивный аккаунт</td><td>Удаление через 12 месяцев после предупредительных писем</td></tr>
  </tbody>
</table>
<p>„Безвозвратное удаление” означает, что данные, включая счета и настройки,
больше не могут быть получены обычными способами.</p>

<h2>9. Cookie-файлы и аналогичные технологии</h2>
<ul>
  <li><b>сессионный cookie</b> — удерживает вас в аккаунте;</li>
  <li><b>cookie языка</b> — запоминает выбранный язык;</li>
  <li><b>localStorage</b> — тема (светлая/тёмная) и подтверждение баннера cookie.</li>
</ul>
<p>Мы не используем рекламные, аналитические или отслеживающие cookie третьих
сторон. Вы можете в любой момент удалить cookie и локальные данные в настройках
браузера.</p>

<h2>10. Сторонние поставщики, помогающие нам работать</h2>
<ul>
  <li><b>хостинг</b> — размещение сервиса и базы данных;</li>
  <li><b>почтовая служба (SMTP)</b> — отправка уведомлений и официальных писем;</li>
  <li><b>Telegram</b> — уведомления через бота (если вы выбрали этот способ).</li>
</ul>
<p>Третьи лица обрабатывают данные только в объёме, необходимом для
предоставления услуги, и в соответствии с надлежащими соглашениями о защите
данных.</p>

<h2>11. Ваши права</h2>
<ul>
  <li><b>доступ</b> к своим данным;</li>
  <li><b>исправление</b> неверных данных;</li>
  <li><b>удаление</b> данных;</li>
  <li><b>экспорт данных</b> (переносимость);</li>
  <li><b>ограничение</b> обработки;</li>
  <li><b>возражение</b> против отдельных видов обработки;</li>
  <li><b>отзыв согласия</b> (например, на уведомления — на странице Профиль);</li>
  <li><b>жалоба</b> в Центр по защите персональных данных Республики Молдова или в компетентный орган вашей страны.</li>
</ul>
<p><b>Как это сделать?</b> Воспользуйтесь <a href="{contact}">страницей контактов</a>
и выберите тему <b>„GDPR — Запрос данных”</b>, либо напишите нам на {company_email}
с той же темой. Мы отвечаем, как правило, в течение 30 дней.</p>

<h2>12. Правовые основания</h2>
<p>Мы обрабатываем персональные данные на следующих основаниях: исполнение
договора использования сервиса (создание аккаунта, подключение услуг,
уведомления), ваше согласие (уведомления, где применимо), законный интерес
(безопасность, предотвращение злоупотреблений, ведение технических записей)
и возложенные на нас правовые обязанности. Простое использование платформы
не является автоматическим согласием на всю обработку: уведомления
необязательны и настраиваются в аккаунте.</p>

<h2>13. Изменения политики</h2>
<p>Мы можем обновлять эту политику. Актуальная версия публикуется на этой
странице; о важных изменениях мы сообщаем через платформу.</p>

<h2>14. Контакты</h2>
<p>По любым вопросам о данных используйте <a href="{contact}">страницу
контактов</a> или напишите нам на {company_email}.</p>
""",
        "content_en": """
<h2>1. Who we are</h2>
<p>UTILITĂȚI.MD is a digital platform for the centralised management of utility
invoices and information for users in the Republic of Moldova. The platform
helps you track and organise invoices for electricity, gas, water, internet and
other services — all from a single account.</p>
<ul>
  <li><b>Platform operator:</b> {company_name}</li>
  <li><b>Official email / GDPR requests:</b> {company_email}</li>
  <li><b>Registered address:</b> {company_address}</li>
  <li><b>Website:</b> {site}</li>
</ul>
<p>Under Regulation (EU) 2016/679 („GDPR") and Law No. 133/2011 on personal data
protection (Republic of Moldova), the data controller is the entity that runs the
platform and decides the purposes and means of processing your personal data.</p>

<h2>2. What the platform actually does</h2>
<ul>
  <li><b>Centralise utilities</b> — add all your utilities to one account;</li>
  <li><b>Manage invoices</b> — keep track of invoices and billing periods;</li>
  <li><b>Monitor amounts</b> — see issued invoices and which remain unpaid;</li>
  <li><b>Automatic notifications</b> — get notified when a new invoice appears or invoices stay unpaid;</li>
  <li><b>Invoice history</b> — review previous invoices;</li>
  <li><b>Multiple homes</b> — apartment, house, rental, parents, etc.;</li>
  <li><b>Multiple utility types</b> — electricity, gas, water, internet and more;</li>
  <li><b>One account</b> — no need to follow each provider separately.</li>
</ul>

<h2>3. What UTILITĂȚI.MD is NOT</h2>
<ul>
  <li>not an electricity, gas or water provider;</li>
  <li>does not issue provider invoices or change their tariffs;</li>
  <li>does not replace the providers' official accounts;</li>
  <li>is not a public authority;</li>
  <li>does not pay invoices on your behalf — you pay the provider directly through its official platform (e.g. oplata.md).</li>
</ul>

<h2>4. What data we collect</h2>
<ul>
  <li><b>Account data:</b> first name, last name, email and username; passwords are never stored in clear text — only as cryptographic hashes;</li>
  <li><b>Home information:</b> name, address and, optionally, floor or area;</li>
  <li><b>Utility connection data:</b> providers, contract or personal account numbers; optionally, provider-portal credentials — stored <b>encrypted</b> and used only to read invoices; you can remove them at any time;</li>
  <li><b>Invoice data:</b> number, amount, period, due date, payment status;</li>
  <li><b>Notification preferences:</b> additional email addresses and Telegram IDs — stored encrypted;</li>
  <li><b>Technical data:</b> IP address, usage data and browser identifiers — used only for security, operation and diagnostics.</li>
</ul>

<h2>5. Data security</h2>
<ul>
  <li><b>In transit:</b> all connections to the platform use HTTPS (encrypted transport);</li>
  <li><b>At rest:</b> user passwords are stored as hashes (PBKDF2-HMAC); provider-portal credentials, additional notification emails and Telegram IDs are encrypted (AES cipher) with a key that is not stored in the database;</li>
  <li><b>Access:</b> technical administrators cannot view your decrypted data; management access is protected by authentication.</li>
</ul>
<p>If a security incident could affect personal data, we will notify the affected
users as required by applicable law.</p>

<h2>6. Data we do NOT collect</h2>
<ul>
  <li>bank card numbers, CVV or other banking data;</li>
  <li>logins to platforms unrelated to the connected utilities;</li>
  <li>browsing history, GPS location or your address-book contacts.</li>
</ul>

<h2>7. Who can see my invoices?</h2>
<p>Your invoices and related data are accessible only to your account and are
processed automatically by the system purely to run the service. Technical staff
do not have access to your decrypted data, and no third parties can view it. We
do not sell or share your data for commercial or advertising purposes.</p>

<h2>8. Data retention</h2>
<table class="retention">
  <thead><tr><th>Data type</th><th>Retention period</th></tr></thead>
  <tbody>
    <tr><td>Active user account</td><td>For as long as the account exists</td></tr>
    <tr><td>Invoices</td><td>Maximum 24 months, then automatic deletion</td></tr>
    <tr><td>Unconfirmed account (email not verified)</td><td>Automatic deletion after a short period</td></tr>
    <tr><td>Account deactivated by the user</td><td>Permanent deletion after 30 days</td></tr>
    <tr><td>Inactive account (no login)</td><td>Deletion after 12 months, preceded by warning emails</td></tr>
  </tbody>
</table>
<p>„Permanent deletion" means the data, including invoices and preferences, can no
longer be accessed or recovered through normal means.</p>

<h2>9. Cookies and similar technologies</h2>
<ul>
  <li><b>session cookie</b> — keeps you signed in;</li>
  <li><b>language cookie</b> — remembers your chosen language;</li>
  <li><b>localStorage</b> — light/dark theme and the cookie-banner acknowledgement.</li>
</ul>
<p>We do not use advertising, analytics or third-party tracking cookies. You can
delete cookies and local data at any time in your browser settings. For the
cookie banner and more details see <a href="{privacy}">Privacy</a>.</p>

<h2>10. Third-party providers that help us operate</h2>
<ul>
  <li><b>hosting</b> — running the service and storing the database;</li>
  <li><b>email service (SMTP)</b> — sending notifications and official messages;</li>
  <li><b>Telegram</b> — notifications via the bot when you choose this option.</li>
</ul>
<p>Third parties process data only to the extent necessary to provide the service
and under appropriate data-protection agreements.</p>

<h2>11. Your rights</h2>
<ul>
  <li>request <b>access</b> to your personal data;</li>
  <li>request <b>rectification</b> of incorrect data;</li>
  <li>request <b>deletion</b> of your data;</li>
  <li>request an <b>export</b> of your data (portability);</li>
  <li>request <b>restriction</b> of processing;</li>
  <li><b>object</b> to certain types of processing;</li>
  <li><b>withdraw consent</b> where processing is based on consent (e.g. notifications — from the Profile page);</li>
  <li>file a <b>complaint</b> with the National Centre for Personal Data Protection of the Republic of Moldova or the competent authority in your country.</li>
</ul>
<p><b>How to do it?</b> Use the <a href="{contact}">contact page</a> and choose the
subject <b>"GDPR — Data request"</b>, or write to {company_email} with the same
subject. We answer, as a rule, within 30 days.</p>

<h2>12. Legal bases</h2>
<p>We process personal data on the following grounds: performance of the service
contract (account creation, connecting utilities, notifications), your consent
(notifications, where applicable), legitimate interest (security, abuse
prevention, technical record-keeping) and legal obligations. Simply using the
platform is not automatic consent to all processing: notifications are optional
and configured in your account.</p>

<h2>13. Changes to this policy</h2>
<p>We may update this policy. The current version is always published on this
page; important changes are communicated through the platform.</p>

<h2>14. Contact</h2>
<p>For any question about your data or this policy, use the
<a href="{contact}">contact page</a> or write to {company_email}.</p>
""",
    },
    {
        "slug": "contact",
        "is_builtin": "1",
        "title_ro": "Contact",
        "title_ru": "Контакты",
        "title_en": "Contact",
        "content_ro": """
<p>Suntem bucuroși să te ajutăm. Scrie-ne pentru orice întrebare despre
platformă, utilități sau datele tale. Pentru cereri privind protecția datelor,
alege subiectul <b>„GDPR — Solicitare date”</b> în formularul de mai jos sau
scrie-ne la {company_email}.</p>
<p>Folosește formularul de mai jos și îți vom răspunde cât mai curând posibil.</p>
""",
        "content_ru": """
<p>Мы будем рады помочь. Напишите нам по любому вопросу о платформе, услугах
или ваших данных. Для запросов о защите данных выберите тему
<b>„GDPR — Запрос данных”</b> в форме ниже или напишите нам на {company_email}.</p>
<p>Воспользуйтесь формой ниже — мы ответим как можно скорее.</p>
""",
        "content_en": """
<p>We are happy to help. Write to us with any question about the platform, your
utilities or your data. For data-protection requests, choose the subject
<b>"GDPR — Data request"</b> in the form below or write to {company_email}.</p>
<p>Please use the form below and we will reply as soon as possible.</p>
""",
    },
    {
        "slug": "about",
        "is_builtin": "1",
        "title_ro": "Despre noi",
        "title_ru": "О нас",
        "title_en": "About us",
        "content_ro": """
<h2>Asistentul tău pentru facturile casei</h2>
<p>Nu mai urmări facturile în cinci locuri diferite. UTILITĂȚI.MD îți adună
utilitățile într-un singur loc și te ajută să nu uiți de plăți. Electricitate.
Gaz. Apă. Internet. Și alte servicii recurente. Un singur cont, o singură
evidență, notificări la timp.</p>

<h2>Cum funcționează</h2>
<ol>
  <li><b>Creezi contul</b> — în câteva minute, gratuit.</li>
  <li><b>Adaugi utilitățile</b> — electricitate, gaz, apă, internet sau alte servicii compatibile, folosind numărul de contract sau contul personal (de exemplu prin platforma de plată a furnizorului).</li>
  <li><b>Sistemul organizează informația</b> — facturile și datele introduse sunt centralizate într-un singur loc.</li>
  <li><b>Primești notificări</b> — pe email sau Telegram, când apare o factură nouă sau ai facturi neachitate.</li>
  <li><b>Ai istoricul la îndemână</b> — verifici ce ai primit și ce rămâne de achitat, direct către furnizor.</li>
</ol>

<h2>Ce oferim</h2>
<ul>
  <li><b>Toate utilitățile într-un singur loc</b> — fără să cauți prin emailuri, SMS-uri și hârtii.</li>
  <li><b>Notificări la timp</b> — știi când trebuie să verifici sau să achiți o factură.</li>
  <li><b>Istoricul facturilor</b> — evidență clară a facturilor primite.</li>
  <li><b>Mai multe locuințe</b> — gestionezi separat utilitățile pentru apartament, casă, chirie sau părinți.</li>
  <li><b>Date protejate</b> — datele tale sunt stocate într-un mod securizat: parole hash-uite, iar datele sensibile criptate.</li>
  <li><b>Creat pentru Moldova</b> — platformă orientată spre modul în care utilizatorii din Republica Moldova își gestionează utilitățile.</li>
</ul>

<h2>Ce NU facem</h2>
<p>Nu suntem furnizor de energie sau gaze, nu emitem facturi, nu modificăm tarife
și nu plătim facturile în locul tău. Suntem un instrument de organizare și
monitorizare a obligațiilor pentru utilități.</p>

<h2>Întrebări?</h2>
<p>Vezi <a href="/">întrebările frecvente</a> sau scrie-ne prin
<a href="/contact">pagina de contact</a>.</p>
""",
        "content_ru": """
<h2>Ваш помощник по домашним счетам</h2>
<p>Не следите за счетами в пяти разных местах. UTILITĂȚI.MD собирает ваши
коммунальные услуги в одном месте и помогает не забыть об оплате. Электричество.
Газ. Вода. Интернет. И другие регулярные услуги. Один аккаунт, один учёт,
своевременные уведомления.</p>

<h2>Как это работает</h2>
<ol>
  <li><b>Создаёте аккаунт</b> — за несколько минут, бесплатно.</li>
  <li><b>Добавляете услуги</b> — электричество, газ, воду, интернет и другие, используя номер договора или лицевой счёт (например, через платёжную платформу поставщика).</li>
  <li><b>Система организует информацию</b> — счета и данные собраны в одном месте.</li>
  <li><b>Получаете уведомления</b> — по email или Telegram, когда появляется новый счёт или есть неоплаченные счета.</li>
  <li><b>История всегда под рукой</b> — видно, что было получено и что осталось оплатить поставщику.</li>
</ol>

<h2>Что мы предлагаем</h2>
<ul>
  <li><b>Все услуги в одном месте</b> — без поиска по email, SMS и бумагам.</li>
  <li><b>Своевременные уведомления</b> — вы знаете, когда проверить или оплатить счёт.</li>
  <li><b>История счетов</b> — чёткий учёт полученных счетов.</li>
  <li><b>Несколько объектов</b> — отдельное управление квартирой, домом, арендой или родителями.</li>
  <li><b>Защита данных</b> — пароли хешируются, чувствительные данные шифруются.</li>
  <li><b>Создано для Молдовы</b> — платформа учитывает, как пользователи в Молдове управляют коммунальными услугами.</li>
</ul>

<h2>Чем мы НЕ занимаемся</h2>
<p>Мы не поставщик энергии или газа, не выставляем счета, не меняем тарифы и не
оплачиваем счета за вас. Мы — инструмент для организации и мониторинга
коммунальных обязательств.</p>

<h2>Вопросы?</h2>
<p>Смотрите <a href="/">часто задаваемые вопросы</a> или свяжитесь с нами через
<a href="/contact">страницу контактов</a>.</p>
""",
        "content_en": """
<h2>Your assistant for household bills</h2>
<p>Stop chasing invoices across five different places. UTILITĂȚI.MD brings your
utilities together in one place and helps you never miss a payment. Electricity.
Gas. Water. Internet. And other recurring services. One account, one record,
timely notifications.</p>

<h2>How it works</h2>
<ol>
  <li><b>Create your account</b> — in a few minutes, free of charge.</li>
  <li><b>Add your utilities</b> — electricity, gas, water, internet and other compatible services, using your contract or personal account number (e.g. through the provider's payment platform).</li>
  <li><b>The system organises the information</b> — invoices and data are centralised in one place.</li>
  <li><b>Receive notifications</b> — by email or Telegram when a new invoice appears or invoices stay unpaid.</li>
  <li><b>History at hand</b> — check what you received and what remains to be paid directly to the provider.</li>
</ol>

<h2>What we offer</h2>
<ul>
  <li><b>All utilities in one place</b> — no digging through emails, SMS and papers.</li>
  <li><b>Timely notifications</b> — you know when to check or pay an invoice.</li>
  <li><b>Invoice history</b> — a clear record of received invoices.</li>
  <li><b>Multiple homes</b> — manage utilities separately for your apartment, house, rental or parents.</li>
  <li><b>Protected data</b> — passwords are hashed and sensitive data is encrypted.</li>
  <li><b>Made for Moldova</b> — a platform tuned to how users in the Republic of Moldova manage their utilities.</li>
</ul>

<h2>What we do NOT do</h2>
<p>We are not an energy or gas provider, we do not issue invoices, we do not
change tariffs and we do not pay invoices on your behalf. We are a tool for
organising and monitoring your utility obligations.</p>

<h2>Questions?</h2>
<p>See the <a href="/">frequently asked questions</a> or write to us via the
<a href="/contact">contact page</a>.</p>
""",
    },
]


# Bumped whenever the built-in page content above changes. On startup, if the
# stored version is older, the built-in pages are refreshed from DEFAULT_PAGES
# (custom pages and later admin edits are kept until the next bump).
SEED_VERSION = "3"


def seed_default_pages(conn=None) -> None:
    """Insert the built-in pages if the table is empty, else sync content when
    the seed version has changed (idempotent)."""
    if conn is None:
        with _conn() as conn:
            _seed(conn)
    else:
        _seed(conn)


def _seed(conn) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM pages").fetchone()["c"]
    if count == 0:
        for page in DEFAULT_PAGES:
            conn.execute(
                """INSERT INTO pages
                   (slug, title_ro, title_ru, title_en,
                    content_ro, content_ru, content_en, is_builtin)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    page["slug"],
                    page["title_ro"], page["title_ru"], page["title_en"],
                    page["content_ro"], page["content_ru"], page["content_en"],
                    int(page.get("is_builtin", "0") or "0"),
                ),
            )
    else:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'pages_seed_version'"
        ).fetchone()
        try:
            version = int(row["value"] if row else "0")
        except (TypeError, ValueError):
            version = 0
        if version < int(SEED_VERSION):
            for page in DEFAULT_PAGES:
                conn.execute(
                    """UPDATE pages SET
                       title_ro = ?, title_ru = ?, title_en = ?,
                       content_ro = ?, content_ru = ?, content_en = ?,
                       meta_title = ?, meta_description = ?,
                       is_builtin = 1, updated_at = datetime('now')
                       WHERE slug = ?""",
                    (
                        page["title_ro"], page["title_ru"], page["title_en"],
                        page["content_ro"], page["content_ru"], page["content_en"],
                        page.get("meta_title", ""), page.get("meta_description", ""),
                        page["slug"],
                    ),
                )
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('pages_seed_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SEED_VERSION,),
    )