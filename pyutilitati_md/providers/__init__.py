"""Provider factory registry for pyutilitati_md."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientSession

from .auto_salubritate import AutoSalubritateProvider
from .base import BaseUtilityProvider
from .infosapr import InfoSaprProvider
from .oplata_utility import OPLATA_PROVIDERS, OplataUtilityProvider

PROVIDER_CLASSES: dict[str, type[BaseUtilityProvider]] = {
    "infosapr": InfoSaprProvider,
    "auto_salubritate": AutoSalubritateProvider,
    # Generic oplata.md-backed providers (single account reference, no cabinet).
    "premier_energy": OplataUtilityProvider,
    "energocom": OplataUtilityProvider,
    "infocom": OplataUtilityProvider,
    "termoelectrica": OplataUtilityProvider,
    "apa_canal_chisinau": OplataUtilityProvider,
    "starnet": OplataUtilityProvider,
    "fee_nord": OplataUtilityProvider,
    "stroy_master_domofon": OplataUtilityProvider,
}


def get_provider_instance(
    provider_id: str,
    contract_number: str,
    place_of_consumption: str | None = None,
    username: str | None = None,
    password: str | None = None,
    session: ClientSession | None = None,
    extra_config: dict[str, Any] | None = None,
) -> BaseUtilityProvider:
    """Instantiate and return the appropriate provider connector."""
    provider_cls = PROVIDER_CLASSES.get(provider_id)
    if not provider_cls:
        raise ValueError(f"Unknown utility provider: {provider_id}")

    base_kwargs = dict(
        contract_number=contract_number,
        place_of_consumption=place_of_consumption,
        username=username,
        password=password,
        session=session,
        extra_config=extra_config,
    )

    if provider_id in OPLATA_PROVIDERS:
        return OplataUtilityProvider(provider_id, **base_kwargs)

    return provider_cls(**base_kwargs)
