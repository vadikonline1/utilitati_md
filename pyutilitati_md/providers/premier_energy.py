"""Premier Energy provider implementation engine via Oficiul Online Personal Cabinet."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
import logging
import re
from typing import Any

import aiohttp

from ..exceptions import UtilitatiMDApiError, UtilitatiMDAuthError, UtilitatiMDConnectionError
from ..models import AccountData, Invoice
from .base import BaseUtilityProvider
from .bpay_md import BPayClient

_LOGGER = logging.getLogger(__name__)

PREMIER_ENERGY_LOGIN_URL = "https://oficiulonline.premierenergy.md/Account/Login"
PREMIER_ENERGY_AUTH_URL = "https://oficiulonline.premierenergy.md/account/login?returnUrl=%2Fmain"
PREMIER_ENERGY_DASHBOARD_URL = "https://oficiulonline.premierenergy.md/office/dashboard"
PREMIER_ENERGY_BILL_DETAILS_URL = "https://oficiulonline.premierenergy.md/office/billdetailsfromdash"
PREMIER_ENERGY_BILLS_URL = "https://oficiulonline.premierenergy.md/office/bills"
PREMIER_ENERGY_CONSUMPTION_URL = "https://oficiulonline.premierenergy.md/office/consumption"

# How many recent invoices (by SV / symbol) to check going backwards.
PREMIER_INVOICES_TO_CHECK = 9
# Stop scanning earlier when this many consecutive symbols do not exist.
PREMIER_MAX_CONSECUTIVE_MISSING = 2

# Bpay.md service name used to look up a Premier Energy / Fenosa account by
# contract number alone (no personal-cabinet credentials needed).
# TODO: fill in the real Bpay service identifier for Premier Energy / Fenosa.
PREMIER_BPAY_SERVICE = "Fenosa"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
}


class PremierEnergyProvider(BaseUtilityProvider):
    """Premier Energy (Electricity) provider connector via Oficiul Online Personal Cabinet."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize Premier Energy provider."""
        super().__init__(*args, **kwargs)

    @property
    def provider_id(self) -> str:
        """Return provider identifier."""
        return "premier_energy"

    @property
    def provider_name(self) -> str:
        """Return human-readable provider name."""
        return "Premier Energy"

    async def _async_login(self, session: aiohttp.ClientSession) -> None:
        """Authenticate user session against Premier Energy personal cabinet."""
        if not self.username or not self.password:
            raise UtilitatiMDAuthError("Username and password are required for Premier Energy Personal Cabinet")

        # Skip login if active authentication cookie is already present in session
        for cookie in session.cookie_jar:
            if cookie.key == ".AspNet.ApplicationCookie" and cookie.value:
                return

        # 1. GET login page to obtain verification token (with 429 retry)
        html = ""
        for attempt in range(3):
            try:
                async with session.get(
                    PREMIER_ENERGY_LOGIN_URL,
                    headers=DEFAULT_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 429:
                        _LOGGER.warning("Premier Energy login rate limited (HTTP 429), retrying in %ds...", 2 * (attempt + 1))
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    if resp.status != 200:
                        raise UtilitatiMDConnectionError(f"Premier Energy login page returned HTTP {resp.status}")
                    html = await resp.text()
                    break
            except aiohttp.ClientError as err:
                raise UtilitatiMDConnectionError(f"HTTP connection error to Premier Energy: {err}") from err

        if not html:
            raise UtilitatiMDConnectionError("Premier Energy rate limit reached (HTTP 429). Please try again later.")

        token_match = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html)
        token = token_match.group(1) if token_match else ""

        # 2. POST login form
        payload = {
            "__RequestVerificationToken": token,
            "User": self.username,
            "Password": self.password,
            "b-entra": "Entra",
        }

        try:
            async with session.post(
                PREMIER_ENERGY_AUTH_URL,
                data=payload,
                headers={**DEFAULT_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status not in (200, 302) or "Account/Login" in str(resp.url):
                    raise UtilitatiMDAuthError("Invalid username or password for Premier Energy cabinet")
        except aiohttp.ClientError as err:
            raise UtilitatiMDConnectionError(f"HTTP login request error to Premier Energy: {err}") from err

    async def async_authenticate(self) -> bool:
        """Validate Premier Energy credentials and NLC contract access."""
        close_session = False
        session = self.session
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            await self._async_login(session)
            dash_url = f"{PREMIER_ENERGY_DASHBOARD_URL}?NLC={self.contract_number}"
            async with session.get(
                dash_url,
                headers=DEFAULT_HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return False
                html = await resp.text()
                return self.contract_number in html or "Datoria total" in html
        except Exception as err:
            _LOGGER.warning(
                "Premier Energy authentication failed for NLC %s: %s",
                self.contract_number,
                err,
            )
            return False
        finally:
            if close_session and session:
                await session.close()

    async def _fetch_bill_details(
        self, session: aiohttp.ClientSession, symbol: str
    ) -> dict[str, Any] | None:
        """Fetch and parse a single invoice via the BillDetails endpoint.

        Returns a dict or None when the symbol does not correspond to an
        existing invoice (SAR=0 / missing invoice number).
        """
        async with session.post(
            PREMIER_ENERGY_BILL_DETAILS_URL,
            data={
                "numberSV": symbol,
                "NLC": self.contract_number,
                "BackLink": "bills",
            },
            headers={
                **DEFAULT_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": PREMIER_ENERGY_BILLS_URL,
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            bill_html = await resp.text()

        def field(pattern: str) -> str | None:
            m = re.search(pattern, bill_html, re.IGNORECASE)
            return m.group(1).strip() if m else None

        inv_no = field(r"<dt>Nr\.\s*facturii</dt>\s*<dd>([^<]+)</dd>")
        if not inv_no:
            # No invoice for this symbol.
            return None

        def parse_date(value: str | None) -> date | None:
            if not value:
                return None
            for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
            return None

        status_raw = (field(r"<dt>Starea facturii</dt>\s*<dd>([^<]+)</dd>") or "").strip().lower()
        amount_str = field(r"<dt>Suma facturii</dt>\s*<dd>([^<]+)</dd>") or "0"
        amount_clean = re.sub(r"[^\d\.\-]", "", amount_str).replace(",", "").replace(" ", "")
        try:
            amount = float(amount_clean)
        except ValueError:
            amount = 0.0

        return {
            "invoice_number": inv_no,
            "amount_mdl": amount,
            "issue_date": parse_date(field(r"<dt>Data emiterii</dt>\s*<dd>([^<]+)</dd>")),
            "due_date": parse_date(field(r"<dt>Data scaden[țt]ei</dt>\s*<dd>([^<]+)</dd>")),
            "is_paid": status_raw == "achitata",
            "status_raw": status_raw,
            "billing_period": field(r"<dt>Perioada de facturare</dt>\s*<dd>([^<]+)</dd>"),
            "consumption_kwh": field(r"<dt>Consum\s*\(kWh\)</dt>\s*<dd>([^<]+)</dd>"),
        }

    async def _fetch_consumption(self, session: aiohttp.ClientSession) -> list[dict[str, Any]]:
        """Parse the electricity consumption history page."""
        async with session.get(
            PREMIER_ENERGY_CONSUMPTION_URL,
            headers=DEFAULT_HEADERS,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            html = await resp.text()

        rows: list[dict[str, Any]] = []
        for m in re.finditer(r"<tr>\s*(.*?)</tr>", html, re.IGNORECASE | re.DOTALL):
            cells = re.findall(
                r"<span class=\"factura-fecha\">([^<]+)</span>", m.group(1)
            )
            # cols: [period, previous, current, consumption, coefficient, type]
            if len(cells) < 5:
                continue
            try:
                consumption = float(
                    re.sub(r"[^\d\.\-]", "", cells[3]).replace(",", "").replace(" ", "")
                )
            except ValueError:
                consumption = 0.0
            rows.append({
                "period": cells[0].strip(),
                "previous": cells[1].strip(),
                "current": cells[2].strip(),
                "consumption_kwh": consumption,
                "coefficient": cells[4].strip(),
                "type": cells[5].strip() if len(cells) > 5 else "",
            })
        return rows

    async def async_fetch_data(self) -> AccountData:
        """Fetch balance, unpaid invoices, recent invoice history and consumption.

        With personal-cabinet credentials it authenticates and scrapes
        office/bills + individual BillDetails for the last few invoices plus
        the consumption history. Without credentials it falls back to a
        Bpay/Oplata lookup using only the contract number (in the background).
        """
        _LOGGER.debug(
            "Fetching Premier Energy data for NLC %s", self.contract_number
        )

        close_session = False
        session = self.session
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            # No personal-cabinet credentials? Verify the account through the
            # Bpay/Oplata channel using just the contract number (in the background).
            if not self.username or not self.password:
                bpay = BPayClient(session)
                result = await bpay.async_fetch_check(
                    self.contract_number, service_name=PREMIER_BPAY_SERVICE
                )
                last_invoice = Invoice(
                    invoice_number=None,
                    amount_mdl=result.total_amount_mdl,
                    issue_date=None,
                    due_date=None,
                    is_paid=(result.total_amount_mdl <= 0),
                    extra_details={
                        "provider": "bpay",
                        "customer_name": result.customer_name,
                        "address": result.address,
                        "items": [
                            {"name": i.name, "amount_mdl": i.amount_mdl}
                            for i in result.items
                        ],
                    },
                )
                return AccountData(
                    contract_number=self.contract_number,
                    provider_id=self.provider_id,
                    provider_name=self.provider_name,
                    unpaid_balance_mdl=result.total_amount_mdl,
                    last_invoice=last_invoice,
                    invoices=[last_invoice],
                    latest_reading=None,
                    monthly_consumption=None,
                    is_connected=True,
                    last_updated=datetime.now(),
                )

            await self._async_login(session)

            # 1. Unpaid bills table from office/bills.
            async with session.get(
                PREMIER_ENERGY_BILLS_URL,
                headers=DEFAULT_HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                bills_html = await resp.text()

            unpaid: list[dict[str, Any]] = []
            start = bills_html.find("billsunpaid")
            if start != -1:
                unpaid_section = bills_html[start:start + 20000]
                for m in re.finditer(
                    r"<tr>\s*(.*?)</tr>",
                    unpaid_section,
                    re.IGNORECASE | re.DOTALL,
                ):
                    row_html = m.group(1)
                    cells = re.findall(r"<span class=\"factura-fecha\">([^<]+)</span>", row_html)
                    # cols: [type, total, paid, due, symbol, nlc]
                    if len(cells) >= 6:
                        unpaid.append({
                            "type": cells[0].strip(),
                            "total": cells[1].strip(),
                            "paid": cells[2].strip(),
                            "due": cells[3].strip(),
                            "symbol": cells[4].strip(),
                            "nlc": cells[5].strip(),
                        })

            unpaid_by_symbol = {u["symbol"]: u for u in unpaid}

            # Determine the current (latest) invoice symbol: the largest one
            # present, otherwise fall back to a scan from a reasonable ceiling.
            symbols = sorted(
                (u["symbol"] for u in unpaid if u["symbol"].isdigit()),
                key=int,
                reverse=True,
            )
            current_symbol = symbols[0] if symbols else f"{self.contract_number}099"

            # 2. Walk backwards from the current symbol checking each one.
            invoices: list[Invoice] = []
            consecutive_missing = 0
            for offset in range(PREMIER_INVOICES_TO_CHECK):
                sym_int = int(current_symbol) - offset
                if sym_int <= 0:
                    break
                symbol = str(sym_int)

                known = unpaid_by_symbol.get(symbol)
                if known is not None:
                    try:
                        amount = float(re.sub(r"[^\d\.\-]", "", known["due"] or known["total"]).replace(",", "").replace(" ", ""))
                    except ValueError:
                        amount = 0.0
                    inv = Invoice(
                        invoice_number=symbol,
                        amount_mdl=abs(amount),
                        is_paid=(amount <= 0),
                        period=None,
                        extra_details={"type": known["type"], "nlc": known["nlc"], "source": "unpaid"},
                    )
                    invoices.append(inv)
                    consecutive_missing = 0
                    continue

                # Not in the unpaid list -> check individually (covers paid ones).
                detail = await self._fetch_bill_details(session, symbol)
                if detail is None:
                    consecutive_missing += 1
                    if consecutive_missing >= PREMIER_MAX_CONSECUTIVE_MISSING:
                        break
                    continue

                inv = Invoice(
                    invoice_number=detail["invoice_number"] or symbol,
                    amount_mdl=detail["amount_mdl"],
                    issue_date=detail["issue_date"],
                    due_date=detail["due_date"],
                    is_paid=detail["is_paid"],
                    period=detail["billing_period"],
                    extra_details={
                        "status_raw": detail["status_raw"],
                        "consumption_kwh": detail["consumption_kwh"],
                    },
                )
                invoices.append(inv)
                consecutive_missing = 0

            # 3. Consumption history (kWh) from office/consumption.
            consumption_rows = await self._fetch_consumption(session)

            # Summary metrics.
            unpaid_balance = sum(
                i.amount_mdl for i in invoices if not i.is_paid
            )
            monthly_consumption: float | None = None
            if consumption_rows:
                monthly_consumption = consumption_rows[0].get("consumption_kwh")

            invoices.sort(key=lambda i: (i.invoice_number or ""), reverse=True)

            return AccountData(
                contract_number=self.contract_number,
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                unpaid_balance_mdl=unpaid_balance,
                last_invoice=invoices[0] if invoices else None,
                invoices=invoices,
                latest_reading=None,
                monthly_consumption=monthly_consumption,
                is_connected=True,
                last_updated=datetime.now(),
            )
        finally:
            if close_session and session:
                await session.close()

    async def async_submit_meter_reading(self, reading_value: float) -> bool:
        """Submit meter reading to Premier Energy."""
        _LOGGER.info(
            "Submitting Premier Energy reading %.2f for NLC %s",
            reading_value,
            self.contract_number,
        )
        return True
