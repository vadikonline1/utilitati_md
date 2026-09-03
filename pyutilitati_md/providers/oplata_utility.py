"""Generic oplata.md-backed utility providers added by account reference.

This generic connector drives utilities that are surfaced through the
oplata.md ``/payment/check`` endpoint, where no personal-cabinet credentials
exist — only a single account/factură/contract reference which we store in the
standard ``contract_number`` field.

Each provider's oplata.md ``service_id`` is a plain constant in code (see
``OPLATA_SERVICE_IDS``). Set the correct oplata.md service id for each provider
you deploy directly here — no environment configuration is required. The request
is built from that service id plus the account reference the user enters in the
app.
"""

from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Any

from ..models import AccountData, Invoice
from .base import BaseUtilityProvider
from .oplata_md import OplataMDClient

_LOGGER = logging.getLogger(__name__)

# oplata.md "service_id" per provider. This is the numeric "Id" oplata.md uses to
# route the /payment/check request to the right provider. Values were confirmed
# against the live oplata.md service pages in August 2026.
OPLATA_SERVICE_IDS: dict[str, int] = {
    "premier_energy": 604,
    "energocom": 1333,
    "infocom": 0,
    "termoelectrica": 815,
    "apa_canal_chisinau": 605,
    "starnet": 300,
    "fee_nord": 1184,
    "stroy_master_domofon": 816,
    "cet_nord": 611,
    "paza_a_mai": 1312,
    "probon": 1343,
    "eco_mereni": 1077,
    "antar_salubrizare": 1189,
    "anintercom": 1191,
    "sagaidac_service": 1253,
    "vipinterfon": 1330,
    "econdominiu": 760,
    "salubeco": 1202,
    "legion_security_group": 1295,
    "invoicer": 904,
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
    "cet_nord": "CET Nord",
    "paza_a_mai": "Paza a MAI",
    "probon": "Probon",
    "eco_mereni": "Eco-Mereni",
    "antar_salubrizare": "ANTAR SALUBRIZARE",
    "anintercom": "Anintercom",
    "sagaidac_service": "Sagaidac Service",
    "vipinterfon": "VIP Interfon",
    "econdominiu": "E-Condominiu",
    "salubeco": "SALUBECO",
    "legion_security_group": "LEGION SECURITY GROUP",
    "invoicer": "Invoicer",
}

# oplata.md "Pasul 1" account field name submitted in the request (Items[0].Name)
# per provider. This must match the field name oplata.md shows for the provider.
OPLATA_ACCOUNT_NAMES: dict[str, str] = {
    "premier_energy": "Codul NLC",
    "energocom": "Cont personal ",
    "infocom": "Numărul contului",
    "termoelectrica": "Cod ID",
    "apa_canal_chisinau": "Numărul facturii",
    "starnet": "Personal ID",
    "fee_nord": "Numărul contractului",
    "stroy_master_domofon": "Cont Abonat",
    "cet_nord": "Numărul facturii",
    "paza_a_mai": "Factura",
    "probon": "ID Client",
    "eco_mereni": "Cod LUC",
    "antar_salubrizare": "Numarul contractului",
    "anintercom": "Numar contract",
    "sagaidac_service": "Numarul contractului",
    "vipinterfon": "Numar contract",
    "econdominiu": "Cod Consumator",
    "salubeco": "Numarul contractului",
    "legion_security_group": "Personal ID",
    "invoicer": " ID platitor",
}

# Providers that verify the account by name + surname. The account's `full_name`
# is sent as a second oplata.md field (Items[1]) when connecting/checking.
OPLATA_FULLNAME_REQUIRED: frozenset[str] = frozenset(
    {"stroy_master_domofon", "vipinterfon", "legion_security_group"}
)

# Label used for the name+surname field on oplata.md (Items[1].Name), and whether
# the field is oplata.md's "special1" type (personal-passport style entry).
OPLATA_FULLNAME_LABELS: dict[str, str] = {
    "stroy_master_domofon": "Nume, Prenume",
    "vipinterfon": "Nume, Prenume",
    "legion_security_group": "Nume, Prenume",
}
OPLATA_FULLNAME_SPECIAL: frozenset[str] = frozenset(
    {"legion_security_group", "stroy_master_domofon"}
)

# Providers that accept the generic single-account oplata flow.
OPLATA_PROVIDERS: frozenset[str] = frozenset(OPLATA_NAMES)


class OplataUtilityProvider(BaseUtilityProvider):
    """Utility provider verified purely through the oplata.md API."""

    def __init__(self, provider_id: str, *args, **kwargs) -> None:
        """Initialize a generic oplata.md-backed provider."""
        super().__init__(*args, **kwargs)
        self._id = provider_id
        self._name = OPLATA_NAMES.get(provider_id, provider_id)
        self._account_name = OPLATA_ACCOUNT_NAMES.get(provider_id, "Cont personal")
        self._service_id = OPLATA_SERVICE_IDS.get(provider_id, 0)
        self._needs_fullname = provider_id in OPLATA_FULLNAME_REQUIRED
        self.client = OplataMDClient(session=self.session)

    @property
    def provider_id(self) -> str:
        """Return provider identifier."""
        return self._id

    @property
    def provider_name(self) -> str:
        """Return human-readable provider name."""
        return self._name

    def _extra_fields(self) -> list[dict[str, Any]]:
        """Build the oplata.md second field for name+surname providers."""
        if not self._needs_fullname:
            return []
        full_name = (self.full_name or "").strip()
        if not full_name:
            return []
        label = OPLATA_FULLNAME_LABELS.get(self._id, "Nume, Prenume")
        return [
            {
                "key": "special1" if self._id in OPLATA_FULLNAME_SPECIAL else "fullname",
                "name": label,
                "value": full_name,
                "special": self._id in OPLATA_FULLNAME_SPECIAL,
            }
        ]

    async def async_authenticate(self) -> bool:
        """Validate the account reference against oplata.md."""
        try:
            res = await self.client.async_fetch_check(
                contract_number=self.contract_number,
                service_id=self._service_id,
                account_key="account",
                account_name=self._account_name,
                extra_items=self._extra_fields(),
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
            extra_items=self._extra_fields(),
        )

        # oplata.md returns one line item per billing/service element. Some
        # providers (e.g. Premier Energy) surface several distinct unpaid
        # invoices at once (each with its own positive amount), while others
        # (e.g. Termoelectrica) return a per-service breakdown of a single
        # invoice. Only split into separate invoices when every item carries a
        # real, billed amount; otherwise collapse them into one invoice whose
        # items become the service breakdown.
        invoices: list[Invoice] = []
        if res.items and all(i.amount_mdl > 0 for i in res.items):
            for i, item in enumerate(res.items, start=1):
                invoices.append(
                    Invoice(
                        invoice_number=f"{self._id.upper()}-{i}",
                        amount_mdl=item.amount_mdl,
                        issue_date=date.today(),
                        is_paid=False,
                        external_invoice_id=item.name or None,
                        extra_details={"destination": item.name},
                    )
                )
        elif res.items:
            invoices.append(
                Invoice(
                    invoice_number=f"{self._id.upper()}-{self.contract_number}",
                    amount_mdl=res.total_amount_mdl,
                    issue_date=date.today(),
                    is_paid=(res.total_amount_mdl <= 0),
                    extra_details={item.name: item.amount_mdl for item in res.items},
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
