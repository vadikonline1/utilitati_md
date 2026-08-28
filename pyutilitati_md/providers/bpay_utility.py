"""Generic BPay.md-backed utility providers added by contract/invoice number.

This generic connector drives utilities that are surfaced through the
bpay.md CheckAccount endpoint, where no personal-cabinet credentials exist —
only a single account reference (Cod ID / Nr. factură / Nr. contract /
Cont abonat) which we store in the standard ``contract_number`` field.

The exact bpay.md ``service`` identifier cannot be validated from this
sandbox (the API is unreachable), so each entry carries a placeholder that
must be confirmed by the operator, mirroring the existing
``APA_CANAL_BPAY_SERVICE`` / ``ENERGOCOM_BPAY_SERVICE`` pattern.
"""

from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Any

from ..models import AccountData, Invoice
from .base import BaseUtilityProvider
from .bpay_md import BPayClient

_LOGGER = logging.getLogger(__name__)

# provider_id -> (display name, bpay.md "service" identifier).
# TODO: confirm the real bpay.md service identifiers with the operator.
BPAY_PROVIDERS: dict[str, tuple[str, str]] = {
    "termoelectrica": ("Termoelectrica", "termoelectrica"),
    "infocom": ("INFOCOM", "infocom"),
    "stroy_master_domofon": ("Stroy Master Domofon", "smdomofon"),
    "starnet": ("Starnet", "starnet"),
}


class BpayUtilityProvider(BaseUtilityProvider):
    """Utility provider verified purely through the bpay.md API."""

    def __init__(self, provider_id: str, *args, **kwargs) -> None:
        """Initialize a generic bpay.md-backed provider."""
        super().__init__(*args, **kwargs)
        self._id = provider_id
        self._name, self._bpay_service = BPAY_PROVIDERS.get(
            provider_id, (provider_id, provider_id)
        )
        self.client = BPayClient(session=self.session)

    @property
    def provider_id(self) -> str:
        """Return provider identifier."""
        return self._id

    @property
    def provider_name(self) -> str:
        """Return human-readable provider name."""
        return self._name

    async def async_authenticate(self) -> bool:
        """Validate the account reference against bpay.md."""
        try:
            res = await self.client.async_fetch_check(
                contract_number=self.contract_number,
                service_name=self._bpay_service,
            )
            return res.total_amount_mdl is not None
        except Exception as err:
            _LOGGER.warning(
                "%s authentication failed for account %s: %s",
                self._name,
                self.contract_number,
                err,
            )
            return False

    async def async_fetch_data(self) -> AccountData:
        """Fetch invoices (current + any unpaid ones) and balance via bpay.md."""
        _LOGGER.debug(
            "Fetching %s data for account %s",
            self._name,
            self.contract_number,
        )

        res = await self.client.async_fetch_check(
            contract_number=self.contract_number,
            service_name=self._bpay_service,
        )

        # bpay.md returns one line item per outstanding invoice/period, so a
        # single check can surface several invoices at once (e.g. INFOCOM with
        # a 5-digit account returns the current invoice plus past unpaid ones).
        invoices: list[Invoice] = []
        if res.items:
            for i, item in enumerate(res.items, start=1):
                extra: dict[str, Any] = {}
                if res.customer_name:
                    extra["customer_name"] = res.customer_name
                if res.address:
                    extra["address"] = res.address
                invoices.append(
                    Invoice(
                        invoice_number=(
                            f"{self._id.upper()}-{i}"
                            if len(res.items) > 1
                            else f"{self._id.upper()}-{self.contract_number}"
                        ),
                        amount_mdl=item.amount_mdl,
                        issue_date=date.today(),
                        is_paid=(item.amount_mdl <= 0),
                        extra_details=extra,
                    )
                )
        else:
            last_invoice = Invoice(
                invoice_number=f"{self._id.upper()}-{self.contract_number}",
                amount_mdl=res.total_amount_mdl,
                issue_date=date.today(),
                is_paid=(res.total_amount_mdl <= 0),
                extra_details={
                    "customer_name": res.customer_name,
                    "address": res.address,
                },
            )
            invoices.append(last_invoice)

        unpaid_balance = sum(i.amount_mdl for i in invoices if not i.is_paid)

        return AccountData(
            contract_number=self.contract_number,
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            unpaid_balance_mdl=unpaid_balance,
            last_invoice=invoices[0] if invoices else None,
            invoices=invoices,
            latest_reading=None,
            monthly_consumption=None,
            is_connected=True,
            last_updated=datetime.now(),
        )

    async def async_submit_meter_reading(self, reading_value: float) -> bool:
        """Submit meter reading (not supported via bpay.md channel)."""
        _LOGGER.info(
            "Meter reading submission not supported for %s account %s",
            self._name,
            self.contract_number,
        )
        return True
