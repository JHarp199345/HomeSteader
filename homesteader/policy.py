"""Provider trust policy.

The core remains offline. This policy records which external provider identities
the user permits a future adapter or manual handoff to use; it does not add any
network capability or grant database access.
"""

from dataclasses import dataclass
from enum import StrEnum


class ProviderKind(StrEnum):
    LOCAL = "local"
    EXTERNAL = "external"


class DisclosureDenied(PermissionError):
    """Raised when a processing request would disclose local records externally."""


@dataclass(frozen=True)
class ProcessingPolicy:
    configured_external_providers: frozenset[str] = frozenset()

    def authorize(self, provider: ProviderKind, purpose: str, provider_id: str | None = None) -> None:
        if provider is ProviderKind.LOCAL:
            return
        if not provider_id or provider_id not in self.configured_external_providers:
            raise DisclosureDenied(
                f"External processing for '{purpose}' is not approved for provider '{provider_id}'."
            )
        # Authorization only. The prototype has no network implementation.
