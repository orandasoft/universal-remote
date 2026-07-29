"""Japanese television tuner capability."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from ...command_names import find_configured_command, normalize_command_name
from ..base import CommandPresentation, ProfileCapability

CAPABILITY_JAPANESE_TUNER: Final = "japanese_tuner"


@dataclass(frozen=True, slots=True)
class TunerRule:
    """One selectable tuner and its ordered selector aliases."""

    tuner_id: str
    selector_candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TunerCapability(ProfileCapability):
    """Command-name rules for tuner selection and numeric routing."""

    tuners: tuple[TunerRule, ...]
    numbers: tuple[int, ...]
    update_after_sent_success: bool = True
    update_after_received_match: bool = True

    def validate(self) -> None:
        """Validate tuner declarations."""
        if not self.tuners:
            raise ValueError(f"Capability {self.capability_id} contains no tuners")

        tuner_ids = tuple(tuner.tuner_id for tuner in self.tuners)
        if len(tuner_ids) != len(set(tuner_ids)):
            raise ValueError(
                f"Capability {self.capability_id} contains duplicate tuner ids"
            )

        normalized_selectors: list[str] = []
        for tuner in self.tuners:
            if not tuner.tuner_id.strip() or not tuner.selector_candidates:
                raise ValueError(
                    f"Capability {self.capability_id} contains an invalid tuner"
                )

            for candidate in tuner.selector_candidates:
                normalized = normalize_command_name(candidate)
                if not normalized:
                    raise ValueError(
                        f"Capability {self.capability_id} contains "
                        "an invalid selector candidate"
                    )
                normalized_selectors.append(normalized)

        if len(normalized_selectors) != len(set(normalized_selectors)):
            raise ValueError(
                f"Capability {self.capability_id} contains "
                "duplicate selector candidates"
            )

        if not self.numbers:
            raise ValueError(
                f"Capability {self.capability_id} contains no keypad numbers"
            )

        if len(self.numbers) != len(set(self.numbers)):
            raise ValueError(
                f"Capability {self.capability_id} contains duplicate keypad numbers"
            )

        if any(type(number) is not int or number <= 0 for number in self.numbers):
            raise ValueError(
                f"Capability {self.capability_id} contains an invalid keypad number"
            )

    def available_tuners(
        self,
        commands: Mapping[str, Any],
    ) -> tuple[str, ...]:
        """Return tuners with a selector and tuner-specific keypad command."""
        return tuple(
            tuner.tuner_id
            for tuner in self.tuners
            if self.selector_command_name(tuner.tuner_id, commands) is not None
            and any(
                self.tuner_number_command_name(
                    tuner.tuner_id,
                    number,
                    commands,
                )
                is not None
                for number in self.numbers
            )
        )

    def selector_command_name(
        self,
        tuner_id: str,
        commands: Mapping[str, Any],
    ) -> str | None:
        """Return the configured selector command for one tuner."""
        tuner = self._tuner(tuner_id)
        if tuner is None:
            return None

        for candidate in tuner.selector_candidates:
            configured = find_configured_command(commands, candidate)
            if configured is not None:
                return configured[0]

        return None

    def tuner_number_command_name(
        self,
        tuner_id: str,
        number: int,
        commands: Mapping[str, Any],
    ) -> str | None:
        """Return one configured tuner-specific numeric command."""
        if self._tuner(tuner_id) is None or number not in self.numbers:
            return None

        configured = find_configured_command(
            commands,
            self._tuner_number_name(tuner_id, number),
        )
        return configured[0] if configured is not None else None

    def keypad_number(self, command_name: str) -> int | None:
        """Return the keypad number represented by a generic command."""
        normalized = normalize_command_name(command_name)

        return next(
            (number for number in self.numbers if normalized == f"NUM_{number}"),
            None,
        )

    def routed_keypad_command_name(
        self,
        selected_tuner: str | None,
        command_name: str,
        commands: Mapping[str, Any],
    ) -> str | None:
        """Return the selected tuner's configured numeric command."""
        if selected_tuner is None:
            return None

        number = self.keypad_number(command_name)
        if number is None:
            return None

        return self.tuner_number_command_name(
            selected_tuner,
            number,
            commands,
        )

    def implied_tuner(self, command_name: str) -> str | None:
        """Return the tuner implied by a selector or prefixed number."""
        normalized = normalize_command_name(command_name)

        for tuner in self.tuners:
            if any(
                normalize_command_name(candidate) == normalized
                for candidate in tuner.selector_candidates
            ):
                return tuner.tuner_id

            if any(
                normalized == self._tuner_number_name(tuner.tuner_id, number)
                for number in self.numbers
            ):
                return tuner.tuner_id

        return None

    def presentation(
        self,
        command_name: str,
    ) -> CommandPresentation | None:
        """Return tuner-specific presentation for one command."""
        normalized = normalize_command_name(command_name)

        for tuner in self.tuners:
            if any(
                normalize_command_name(candidate) == normalized
                for candidate in tuner.selector_candidates
            ):
                return CommandPresentation(
                    label=tuner.tuner_id,
                    icon="mdi:import",
                    category="input",
                )

            for number in self.numbers:
                if normalized == self._tuner_number_name(
                    tuner.tuner_id,
                    number,
                ):
                    return CommandPresentation(
                        label=f"{tuner.tuner_id} Number {number}",
                        category="numeric",
                    )

        return None

    def _tuner(self, tuner_id: str) -> TunerRule | None:
        """Return one declared tuner by stable ID."""
        return next(
            (tuner for tuner in self.tuners if tuner.tuner_id == tuner_id),
            None,
        )

    @staticmethod
    def _tuner_number_name(tuner_id: str, number: int) -> str:
        """Return the normalized tuner-specific command name."""
        return f"{normalize_command_name(tuner_id)}_NUM_{number}"


JAPANESE_TUNER_CAPABILITY = TunerCapability(
    capability_id=CAPABILITY_JAPANESE_TUNER,
    tuners=tuple(
        TunerRule(tuner_id, (tuner_id,))
        for tuner_id in ("DTV", "BS", "CS1", "CS2", "BS4K", "CS4K")
    ),
    numbers=tuple(range(1, 13)),
)
