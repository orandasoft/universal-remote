"""Protocol-neutral infrared command models."""

from dataclasses import dataclass


type CommandMatchKey = tuple[str, int, int, int | None]


@dataclass(frozen=True, slots=True)
class DecodedInfraredCommand:
    """Protocol-aware decoded infrared command used for matching."""

    protocol: str
    address: int
    primary: int
    secondary: int | None = None

    @property
    def match_key(self) -> CommandMatchKey:
        """Return a stable protocol-aware command matching key."""
        return (self.protocol, self.address, self.primary, self.secondary)
