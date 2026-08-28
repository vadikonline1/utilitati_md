"""Generic oplata.md-backed utility providers added by account reference.

This generic connector drives utilities that are surfaced through the
oplata.md ``/payment/check`` endpoint, where no personal-cabinet credentials
exist — only a single account/factură/contract reference which we store in the
standard ``contract_number`` field.

Each provider's oplata.md ``service_id`` is a plain constant in code (see
``OPLATA_SERVICE_IDS``), mirroring the dedicated ``FEE_NORD_SERVICE_ID`` /
``INFOSAPR_SERVICE_ID`` connectors. No runtime/environment configuration is
required: the request is built from the operator-set service id and the
account reference the user enters in the app.
"""

from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Any

from ..models import AccountData, Invoice
from .base import BaseUtilityProvider
from .oplata_md import OplataMDClient

_LOGGER = logging.getLogger(__name__)

# oplata.md "service_id" per provider. Set the correct value for each provider
# you deploy; this connector needs no environment configuration beyond that.
OPLATA_SERVICE_IDS: dict[str, int] = {
    "premier_energy": 0,
    "energocom": 0,
    "infocom": 0,
    "termoelectrica": 0,
    "apa_canal_chisinau": 0,
    "starnet": 0,
    "fee_nord": 0,
    "stroy_master_domofon": 0,
}

# Display names (kept in sync with the web UI provider meta).
OPLATA_NAMES: dict[str, str] = {
    "premier_energy": "Premier Energy",
    "energocom": "Energocom",
    "infocom": "INFOCOM",
    "termoelectrica": "Termoelectrica",
    "apa_canal_chisinau": "Apă-Canal Chișinău",
    "starnet": "StarNet",
    "fee_nord": "FEE Nord",
    "stroy_master_domofon": "Stroy Master Domofon",
}

# oplata.md "Pasul 1" account field label per provider.
OPLATA_ACCOUNT_NAMES: dict[str, str] = {
    "premier_energy": "Cod NLC",
    "energocom": "Contul personal",
    "infocom": "Numărul contului",
    "termoelectrica": "Numărul contului",
    "apa_canal_chisinau": "Numărul contului",
    "starnet": "Codul personal",
    "fee_nord": "Numărul contractului",
    "stroy_master_domofon": "Cont Abonat",
}

# Providers that accept the generic single-account oplata flow.
OPLATA_PROVIDERS: frozenset[str] = frozenset(OPLATA_SERVICE_IDS)


class OplataUtilityProvider(BaseUtilityProvider):
    """Utility provider verified purely through the oplata.md API."""

    def __init__(self, provider_id: str, *args, **kwargs) -> None:
        """Initialize a generic oplata.md-backed provider."""
        super().__init__(*args, **kwargs)
        self._id = provider_id
        self._name = OPLATA_NAMES.get(provider_id, provider_id)
        self._account_name = OPLATA_ACCOUNT_NAMES.get(provider_id, "Cont personal")
        self._service_id = OPLATA_SERVICE_IDS.get(provider_id, 0)
        self.client = OplataMDClient(session=self.session)

    @property
    def provider_id(self) -> str:
        """Return provider identifier."""
        return self._id

    @property
    def provider_name(self) -> str:
        """Return human-readable provider name."""
        return self._name

    async def async_authenticate(self) -> bool:
        """Validate the account reference against oplata.md."""
        try:
            res = await self.client.async_fetch_check(
                contract_number=self.contract_number,
                service_id=self._service_id,
                account_key="account",
                account_name=self._account_name,
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
        """Fetch invoices (current + any unpaid ones) and balance via oplata.md."""
        _LOGGER.debug(
            "Fetching %s data for account %s (service_id=%s)",
            self._name,
            self.contract_number,
            self._service_id,
        )

        res = await self.client.async_fetch_check(
            contract_number=self.contract_number,
            service_id=self._service_id,
            account_key="account",
            account_name=self._account_name,
        )

        # oplata.md returns one line item per outstanding invoice/period, so a
        # single check can surface several invoices at once.
        invoices: list[Invoice] = []
        if res.items:
            for i, item in enumerate(res.items, start=1):
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
                        extra_details={"destination": item.name},
                    )
                )
        else:
            invoices.append(
                Invoice(
                    invoice_number=f"{self._id.upper()}-{self.contract_number}",
                    amount_mdl=res.total_amount_mdl,
                    issue_date=date.today(),
                    is_paid=(res.total_amount_mdl <= 0),
                )
            )

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
        """Submit meter reading (not supported via oplata.md channel)."""
        _LOGGER.info(
            "Meter reading submission not supported for %s account %s",
            self._name,
            self.contract_number,
        )
        return True
