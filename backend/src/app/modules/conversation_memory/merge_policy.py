"""Merge policy and conflict resolution logic for Conversation Memory facts."""

from typing import Sequence

from app.modules.conversation_memory.contract import (
    MemoryFact,
    WorkingMemoryState,
)


class MergePolicyEvaluator:
    """Evaluates and filters extracted memory facts according to conversation memory policy rules."""

    def evaluate_facts(
        self,
        current_memory: WorkingMemoryState,
        extracted_facts: Sequence[MemoryFact],
    ) -> list[MemoryFact]:
        valid_facts: list[MemoryFact] = []
        existing_facts = current_memory.active_facts or current_memory.confirmed_facts

        for new_fact in extracted_facts:
            existing_active = [
                f for f in existing_facts
                if f.key == new_fact.key and f.status == "active"
            ]
            existing_confirmed = [
                f for f in existing_active
                if f.confirmed_by_user
            ]

            # Rule 1: Explicit user confirmation has highest priority
            if new_fact.confirmed_by_user:
                # An explicit user change wins over a previous confirmed value;
                # confidence must never make the system ignore a direct choice.
                valid_facts.append(new_fact)
                continue

            # Rule 2: Unconfirmed facts cannot overwrite user-confirmed facts
            if existing_confirmed:
                continue

            # Rule 3: Unconfirmed vs unconfirmed confidence comparison
            if existing_active:
                if new_fact.provenance.confidence < existing_active[0].provenance.confidence:
                    continue

            valid_facts.append(new_fact)

        return valid_facts

    def merge_facts_into_memory_state(
        self,
        current_memory: WorkingMemoryState,
        new_facts: Sequence[MemoryFact],
    ) -> WorkingMemoryState:
        """Apply extracted facts to update WorkingMemoryState fields while preserving history."""
        updated_dict = current_memory.model_dump(mode="python", by_alias=True)

        mentioned_places = list(current_memory.mentioned_places)
        selected_places = list(current_memory.selected_places)

        all_facts = list(current_memory.active_facts) if current_memory.active_facts else list(current_memory.confirmed_facts)

        for fact in new_facts:
            # Update projection fields
            if fact.key == "destination" and fact.status == "active":
                updated_dict["destination"] = str(fact.value)
            elif fact.key == "duration" and fact.status == "active":
                updated_dict["durationDays"] = int(fact.value)
            elif fact.key == "travelers" and fact.status == "active":
                updated_dict["travelers"] = int(fact.value)
            elif fact.key == "budget_tier" and fact.status == "active":
                updated_dict["budget"] = {"tier": str(fact.value)}
            elif fact.key == "place_candidate" and fact.status == "active":
                place_str = str(fact.value)
                if place_str not in mentioned_places:
                    mentioned_places.append(place_str)
                if fact.confirmed_by_user and place_str not in selected_places:
                    selected_places.append(place_str)

            # Preserve history & supersede old active facts:
            # Scalar facts supersede all previous active facts with same key.
            # place_candidate facts ONLY supersede previous active facts with matching normalized_value.
            for i, old_fact in enumerate(all_facts):
                if old_fact.key == fact.key and old_fact.status == "active":
                    if fact.key == "place_candidate":
                        if old_fact.computed_normalized_value == fact.computed_normalized_value:
                            all_facts[i] = old_fact.model_copy(update={"status": "superseded"})
                    else:
                        all_facts[i] = old_fact.model_copy(update={"status": "superseded"})

            all_facts.append(fact)

        active_facts = [f for f in all_facts if f.status == "active"]
        confirmed_facts = [f for f in active_facts if f.confirmed_by_user]

        updated_dict["mentionedPlaces"] = mentioned_places
        updated_dict["selectedPlaces"] = selected_places
        updated_dict["activeFacts"] = active_facts
        updated_dict["confirmedFacts"] = confirmed_facts

        return WorkingMemoryState.model_validate(updated_dict)
