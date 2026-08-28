"""Provider factory registry for pyutilitati_md."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientSession

from .apa_canal_chisinau import ApaCanalChisinauProvider
from .auto_salubritate import AutoSalubritateProvider
from .base import BaseUtilityProvider
from .bpay_utility import BPAY_PROVIDERS, BpayUtilityProvider
from .energocom import EnergocomProvider
from .fee_nord import FeeNordProvider
from .infosapr import InfoSaprProvider
from .premier_energy import PremierEnergyProvider
from .starnet import StarnetProvider

PROVIDER_CLASSES: dict[str, type[BaseUtilityProvider]] = {
    "premier_energy": PremierEnergyProvider,
    "infosapr": InfoSaprProvider,
    "energocom": EnergocomProvider,
    "starnet": StarnetProvider,
    "fee_nord": FeeNordProvider,
    "apa_canal_chisinau": ApaCanalChisinauProvider,
    "auto_salubritate": AutoSalubritateProvider,
    # Generic bpay.md-backed providers (single account reference, no cabinet).
    "termoelectrica": BpayUtilityProvider,
    "infocom": BpayUtilityProvider,
    "stroy_master_domofon": BpayUtilityProvider,
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

    if provider_id in BPAY_PROVIDERS:
        return BpayUtilityProvider(provider_id, **base_kwargs)

    return provider_cls(**base_kwargs)
