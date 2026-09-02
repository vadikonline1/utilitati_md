"""Oplata.md payment portal client engine for Moldova utility providers."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Any

import aiohttp

from ..exceptions import UtilitatiMDApiError, UtilitatiMDAuthError, UtilitatiMDConnectionError

_LOGGER = logging.getLogger(__name__)

OPLATA_MD_CHECK_URL = "https://oplata.md/payment/check"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ro;q=0.8,ru;q=0.7",
    "Content-Type": "application/x-www-form-urlencoded",
}


@dataclass
class OplataMDServiceItem:
    """Sub-service line item breakdown."""

    name: str
    amount_mdl: float
    service_code: str | None = None
    invoice_id: str | None = None


@dataclass
class OplataMDInvoiceResult:
    """Parsed result from oplata.md payment invoice request."""

    contract_number: str
    total_amount_mdl: float
    items: list[OplataMDServiceItem] = field(default_factory=list)
    raw_html: str = ""


class OplataMDClient:
    """Client for fetching utility invoice details from oplata.md."""

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        """Initialize oplata.md client."""
        self._session = session

    async def async_fetch_check(
        self,
        contract_number: str,
        service_id: int,
        account_key: str = "account",
        account_name: str = "Cont personal ",
        sub_srv: int = 0,
        extra_items: list[dict[str, Any] | None] | None = None,
    ) -> OplataMDInvoiceResult:
        """Fetch and parse invoice data from oplata.md /payment/check endpoint.

        ``extra_items`` optionally appends additional ``Items[N]`` fields (used
        when a provider verifies by name + surname, e.g. Stroy Master Domofon,
        VIP Interfon and LEGION SECURITY GROUP). Each entry may carry:
          * ``key``   – the oplata.md item key (e.g. "special1" or "fullname")
          * ``name``  – the displayed field label ("Nume, Prenume")
          * ``value`` – the submitted value
          * ``special`` – when True, also submit ``Items[N].Special=1``
        """
        payload = {
            "Id": str(service_id),
            "SubSrv": str(sub_srv),
            "Items[0].Key": account_key,
            "Items[0].Name": account_name,
            "Items[0].Value": contract_number,
        }
        for index, item in enumerate(extra_items or [], start=1):
            payload[f"Items[{index}].Key"] = str(item.get("key", "account"))
            payload[f"Items[{index}].Name"] = str(item.get("name", ""))
            payload[f"Items[{index}].Value"] = str(item.get("value", ""))
            if item.get("special"):
                payload[f"Items[{index}].Special"] = "1"
        return await self._post_and_parse(OPLATA_MD_CHECK_URL, payload, contract_number)

    async def _post_and_parse(
        self, url: str, payload: dict[str, str], contract_number: str
    ) -> OplataMDInvoiceResult:
        """Send HTTP POST payload to oplata.md and parse output."""
        close_session = False
        session = self._session
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.post(
                url,
                data=payload,
                headers=DEFAULT_HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status != 200:
                    raise UtilitatiMDConnectionError(
                        f"oplata.md returned HTTP status {response.status}"
                    )
                html_text = await response.text()
        except aiohttp.ClientError as err:
            raise UtilitatiMDConnectionError(f"HTTP connection error to oplata.md: {err}") from err
        finally:
            if close_session and session:
                await session.close()

        return self._parse_invoice_html(contract_number, html_text)

    def _parse_invoice_html(self, contract_number: str, html_text: str) -> OplataMDInvoiceResult:
        """Parse HTML output from oplata.md invoice page."""
        # 1. Extract total amount
        ppvalue_match = re.search(r'id="Amount"[^>]*ppvalue="(\d+)"', html_text)
        amount_match = re.search(r'id="Amount"[^>]*value="([\d\.]+)"', html_text)

        total_amount: float | None = None
        if ppvalue_match:
            try:
                total_amount = float(ppvalue_match.group(1)) / 100.0
            except ValueError:
                pass

        if total_amount is None and amount_match:
            try:
                total_amount = float(amount_match.group(1))
            except ValueError:
                pass

        # 1b. Fallback: providers like Premier Energy surface each outstanding
        # invoice as a radio button (Items[0].Value = "REF; SUMAMDL") instead of
        # a single id="Amount" total. Parse those into line items.
        if total_amount is None and re.search(
            r'name="Items\[0\]\.Value"[^>]*type="radio"', html_text
        ):
            items, total_amount = self._parse_radio_invoices(html_text)
            if total_amount is None:
                raise UtilitatiMDApiError(
                    f"Failed to parse invoice total amount for contract "
                    f"'{contract_number}'"
                )
            # TODO: better period/label extraction when available
            return OplataMDInvoiceResult(
                contract_number=contract_number,
                total_amount_mdl=total_amount,
                items=items,
                raw_html=html_text,
            )

        if total_amount is None:
            if 'id="Amount"' not in html_text:
                raise UtilitatiMDAuthError(
                    f"Account or invoice not found for contract '{contract_number}'"
                )
            raise UtilitatiMDApiError(
                f"Failed to parse invoice total amount for contract '{contract_number}'"
            )

        # 2. Extract sub-services (ServicePaymentList items)
        items: list[OplataMDServiceItem] = []

        # Find indexed blocks: ServicePaymentList[<idx>]
        indices = set(re.findall(r'name="ServicePaymentList\[(\d+)\]', html_text))
        sorted_indices = sorted(indices, key=int)

        for idx in sorted_indices:
            dest_match = re.search(
                rf'name="ServicePaymentList\[{idx}\]\.Destination"[^>]*value="([^"]+)"',
                html_text,
            )
            ppval_match = re.search(
                rf'name="ServicePaymentList\[{idx}\]\.AmountFactFloat"[^>]*ppvalue="(\d+)"',
                html_text,
            )
            val_match = re.search(
                rf'name="ServicePaymentList\[{idx}\]\.AmountFactFloat"[^>]*value="([\d\.]+)"',
                html_text,
            )

            dest_name = dest_match.group(1) if dest_match else f"Service #{idx}"
            item_amount = 0.0

            if ppval_match:
                try:
                    item_amount = float(ppval_match.group(1)) / 100.0
                except ValueError:
                    pass
            elif val_match:
                try:
                    item_amount = float(val_match.group(1))
                except ValueError:
                    pass

            items.append(OplataMDServiceItem(name=dest_name, amount_mdl=item_amount))

        return OplataMDInvoiceResult(
            contract_number=contract_number,
            total_amount_mdl=total_amount,
            items=items,
            raw_html=html_text,
        )

    def _parse_radio_invoices(
        self, html_text: str
    ) -> tuple[list[OplataMDServiceItem], float | None]:
        """Parse providers that return invoices as radio buttons.

        oplata.md renders each outstanding invoice as:
            <input id="Items_0__Value" name="Items[0].Value" type="radio"
                   value="REF" />REF; 123.45MDL <br />
        The visible label holds the reference followed by "; <amount>MDL".
        Returns (line_items, total) where total is the sum of all invoices.
        """
        items: list[OplataMDServiceItem] = []
        total = 0.0

        # Each radio block: value="REF" />LABEL <br>
        pattern = re.compile(
            r'name="Items\[0\]\.Value"[^>]*type="radio"[^>]*value="([^"]*)"'
            r'\s*/>\s*([^<\n]+?)\s*(?:<br|</)'
        )
        for match in pattern.finditer(html_text):
            value = match.group(1)
            label = match.group(2)
            amount = self._extract_amount_from_label(label)
            if amount is None:
                continue
            name = value if value else label.split(";")[0].strip()
            items.append(OplataMDServiceItem(name=name, amount_mdl=amount))
            total += amount

        if not items:
            return [], None
        return items, round(total, 2)

    @staticmethod
    def _extract_amount_from_label(label: str) -> float | None:
        """Pull the trailing '<number>MDL' (or a bare number) from a label."""
        match = re.search(r"([\d]+(?:[\.,]\d+)?)\s*MDL", label, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                return None
        # Fallback: a bare decimal token in the label.
        match = re.search(r"([\d]+\.\d{2})", label)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None
