"""RunPay payment portal provider for Moldova utility accounts.

RunPay (my.runpay.com) exposes a multi-step HTML billing form per operator
(service) at ``/operator?id=<operator_id>``. Verifying an account and reading
its outstanding balance requires:

  1. GET the operator page to obtain the hidden ``cur`` (request id) and the
     account input field.
  2. Fill in the account reference.
  3. Submit the form. The page runs reCAPTCHA v3 (``grecaptcha.execute``) and
     then POSTs ``/operator/index`` with ``id``, ``cur``, the token and the
     account. The response is the "step 2" payment page that carries the
     outstanding amount(s).

reCAPTCHA v3 cannot be satisfied by a plain HTTP client (it needs to run the
site JS and passes a human-scored token), so this provider drives a real
Chromium via Playwright in a worker thread.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date, datetime
from typing import Any

from ..exceptions import UtilitatiMDAuthError, UtilitatiMDConnectionError
from ..models import AccountData, Invoice
from .base import BaseUtilityProvider

_LOGGER = logging.getLogger(__name__)

RUNPAY_OPERATOR_URL = "https://my.runpay.com/operator"
RUNPAY_INDEX_URL = "https://my.runpay.com/operator/index"

# operator_id per provider (from the project instructions).
RUNPAY_OPERATOR_IDS: dict[str, int] = {
    "energocom": 2725,
    "termoelectrica": 1285,
    "premier_energy": 1923,
    "starnet": 871,
    "fee_nord": 1865,
    "infosapr": 1133,
    "stroy_master_domofon": 1115,
    "apa_canal_chisinau": 2727,
    "infocom": 1404,
}

# Edg / Chrome user-agent used to reduce bot detection heuristics.
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
)

ACCOUNT_NOT_FOUND_MARKERS = re.compile(
    r"nu a trecut|nu\s+a\s+trecut|incorect|не найд|не найдено|не существует|"
    r"nepravil|некорректн|găsit|неверн",
    re.IGNORECASE,
)

STEP_TITLES = ("Datele destinatarului", "Tipul achitarii", "Achitare servicii",
               "Transfer efectuat")


class RunPayProvider(BaseUtilityProvider):
    """RunPay-backed provider connector (single account reference, no cabinet)."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize runpay provider."""
        super().__init__(*args, **kwargs)
        self._operator_id = RUNPAY_OPERATOR_IDS.get(self.provider_id)
        self._session_cookie = (
            (self.extra_config or {}).get("session_cookie")
            or os.environ.get("RUNPAY_SESSION_COOKIE")
            or ""
        )

    @property
    def provider_id(self) -> str:
        """Return the runpay-backed provider identifier (overridden by subclass)."""
        return "runpay"

    @property
    def provider_name(self) -> str:
        """Return human-readable provider name."""
        return "RunPay"

    _EXPECTED_PROVIDERS = frozenset(RUNPAY_OPERATOR_IDS)

    async def async_authenticate(self) -> bool:
        """Validate that the account exists on the runpay operator."""
        try:
            amount = await self._fetch_amount_threaded()
            return amount is not None
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.warning("runpay authenticate failed for %s: %s", self.contract_number, err)
            return False

    async def async_fetch_data(self) -> AccountData:
        """Fetch the outstanding balance via the runpay operator flow."""
        _LOGGER.debug("Fetching runpay data for contract %s (op=%s)",
                      self.contract_number, self._operator_id)
        amount = await self._fetch_amount_threaded()
        unpaid = round(amount, 2) if amount and amount > 0 else 0.0
        invoice = Invoice(
            invoice_number=f"RP-{self.contract_number}",
            amount_mdl=round(unpaid, 2),
            issue_date=date.today(),
            due_date=None,
            period=None,
            is_paid=unpaid <= 0,
            extra_details={"source": "runpay"},
        )
        return AccountData(
            contract_number=self.contract_number,
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            unpaid_balance_mdl=round(unpaid, 2),
            last_invoice=invoice,
            latest_reading=None,
            monthly_consumption=None,
            is_connected=True,
            last_updated=datetime.now(),
        )

    async def async_submit_meter_reading(self, reading_value: float) -> bool:
        """RunPay has no meter reading submission."""
        return True

    # ------------------------------------------------------------------ #
    # Playwright worker
    # ------------------------------------------------------------------ #
    async def _fetch_amount_threaded(self) -> float:
        return await asyncio.to_thread(self._fetch_amount_sync)

    def _fetch_amount_sync(self) -> float:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as err:  # pragma: no cover
            raise UtilitatiMDConnectionError(
                "Playwright/Chromium not installed for the runpay provider"
            ) from err

        if self._operator_id is None:
            raise UtilitatiMDConnectionError(
                f"Unknown runpay operator for provider '{self.provider_id}'"
            )

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Exception as err:  # pragma: no cover
                raise UtilitatiMDConnectionError(
                    f"Could not launch Chromium for runpay: {err}"
                ) from err
            try:
                ctx = browser.new_context(
                    user_agent=DEFAULT_UA,
                    viewport={"width": 1280, "height": 900},
                )
                if self._session_cookie:
                    for part in self._session_cookie.split(";"):
                        part = part.strip()
                        if not part or "=" not in part:
                            continue
                        key, _, value = part.partition("=")
                        ctx.add_cookies([{
                            "name": key.strip(),
                            "value": value.strip(),
                            "domain": ".my.runpay.com",
                            "path": "/",
                        }])
                page = ctx.new_page()

                resp = page.goto(
                    f"{RUNPAY_OPERATOR_URL}?id={self._operator_id}",
                    wait_until="networkidle",
                    timeout=30000,
                )
                if resp is None or resp.status != 200:
                    raise UtilitatiMDConnectionError(
                        f"runpay operator page returned HTTP "
                        f"{resp.status if resp else 'no response'}"
                    )
                page.wait_for_timeout(2000)

                field_name = self._account_field_name(page)
                page.fill(f"input[name={field_name}]", self.contract_number)
                page.wait_for_timeout(800)
                page.click("button:has-text('CONTINUARE')")

                # Wait for the /operator/index POST to complete.
                try:
                    page.wait_for_url("**/operator/index**", timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(2500)
                step_html = page.content()
            finally:
                browser.close()

        return self._parse_step_html(step_html)

    @staticmethod
    def _account_field_name(page: Any) -> str:
        """Return the account text-input name on the runpay operator page."""
        names = page.eval_on_selector_all(
            "input[type=text]",
            "els => els.map(e => e.name)",
        )
        for n in names:
            if n:
                return n
        return "Account"

    # ------------------------------------------------------------------ #
    # Parser
    # ------------------------------------------------------------------ #
    @staticmethod
    def _has_step(html: str) -> bool:
        """Return True if the response looks like a runpay step (payment) page."""
        return any(t in html for t in STEP_TITLES)

    def _parse_step_html(self, html: str) -> float:
        if not self._has_step(html):
            if ACCOUNT_NOT_FOUND_MARKERS.search(html) or "Înapoi" in html:
                raise UtilitatiMDAuthError(
                    f"Account or contract '{self.contract_number}' not found"
                )
            raise UtilitatiMDConnectionError(
                "runpay returned an unparseable response (unknown step)"
            )

        # 1. A visible (non-hidden) Summa text input carries the exact amount
        # the user must pay (e.g. StarNet pre-fills it with the balance).
        m = re.search(
            r'<input[^>]*id="Summa"[^>]*type="text"[^>]*value="([^"]*)"', html
        )
        if m:
            val = self._parse_number(m.group(1))
            if val is not None and val > 0:
                return val

        # 2. Sum the selectable service balances (Termoelectrica-style):
        #    <li class="button ..." a="X.XX"> ... </li>
        items = re.findall(r'<li[^>]*\sa="([0-9][0-9\.,]*)"', html)
        if items:
            return sum(
                v for v in (self._parse_number(i) for i in items) if v is not None
            )

        # 3. "Suma spre achitare" display span (pay_amount) and other amounts.
        for span_id in ("pay_amount", "amount"):
            m = re.search(
                rf'id="{span_id}"[^>]*>\s*([0-9][0-9\.,\s]*)\s*<', html
            )
            if m:
                val = self._parse_number(m.group(1))
                if val is not None:
                    return val

        # 4. "Suma spre achitare" following number in bare text.
        m = re.search(r"Suma[^<]{0,20}achitare[^<]{0,40}?([0-9][0-9\.,\s]*)", html)
        if m:
            val = self._parse_number(m.group(1))
            if val is not None:
                return val

        raise UtilitatiMDConnectionError(
            f"runpay returned a step page but no amount could be parsed "
            f"for account '{self.contract_number}'"
        )

    @staticmethod
    def _parse_number(text: str) -> float | None:
        if not text:
            return None
        s = text.strip().replace("\u00a0", "").replace(" ", "")
        if not s:
            return None
        s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
