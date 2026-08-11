from dataclasses import dataclass


@dataclass(frozen=True)
class PlaceSearchPolicy:
    named_acceptance_score: float = 0.82
    named_minimum_margin: float = 0.08
    ambiguity_name_score: float = 0.86
    requirement_acceptance_score: float = 0.68

    def __post_init__(self) -> None:
        for field_name, value in vars(self).items():
            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be between zero and one")

