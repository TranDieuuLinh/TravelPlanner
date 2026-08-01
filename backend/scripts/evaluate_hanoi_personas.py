from __future__ import annotations

import argparse
import json

import httpx


API_URL = "http://localhost:8000/api/plans/main/from-context"

PERSONAS = {
    "traditional_food_and_coffee": {
        "days": 1,
        "travelStyle": "local",
        "pace": "balanced",
        "interests": [
            "traditional Hanoi food",
            "local cuisine",
            "egg coffee",
        ],
    },
    "history_and_heritage": {
        "days": 1,
        "travelStyle": "cultural",
        "pace": "balanced",
        "interests": [
            "Hanoi history",
            "cultural heritage",
            "historic architecture",
        ],
    },
    "old_quarter_visit_with_meals": {
        "days": 1,
        "travelStyle": "cultural",
        "pace": "balanced",
        "interests": [
            "explore Hanoi Old Quarter",
            "temples monuments and historic architecture",
            "food",
        ],
    },
    "relaxed_local_hanoi": {
        "days": 2,
        "travelStyle": "local",
        "pace": "relaxed",
        "interests": [
            "local Hanoi culture",
            "traditional food",
            "coffee",
            "lakeside relaxation",
        ],
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--persona",
        action="append",
        choices=sorted(PERSONAS),
        help="Run only the selected persona; may be repeated.",
    )
    args = parser.parse_args()
    selected_personas = (
        {key: PERSONAS[key] for key in args.persona}
        if args.persona
        else PERSONAS
    )
    summaries: dict[str, dict] = {}
    with httpx.Client(timeout=600.0) as client:
        for label, persona in selected_personas.items():
            response = client.post(
                API_URL,
                json={
                    "intent": {
                        "destination": "Hà Nội",
                        "travelStyle": persona["travelStyle"],
                        "pace": persona["pace"],
                        "interests": persona["interests"],
                    },
                    "tripSpec": {"days": persona["days"]},
                    "regionKey": "vn,ha-noi",
                    "selectedPlaces": [],
                    "userStatus": {},
                },
            )
            if response.is_error:
                summaries[label] = {
                    "statusCode": response.status_code,
                    "error": response.text,
                }
                print(json.dumps({label: summaries[label]}, ensure_ascii=False, indent=2))
                continue
            plan = response.json()
            summaries[label] = {
                "title": plan.get("macroPlan", {}).get("title"),
                "warnings": plan.get("warnings", []),
                "checkStatus": plan.get("checkReport", {}).get("status"),
                "days": [
                    {
                        "day": day.get("day"),
                        "theme": day.get("theme"),
                        "items": [
                            {
                                "name": item.get("name"),
                                "placeId": item.get("placeId"),
                                "placeType": item.get("placeType"),
                                "role": item.get("role"),
                                "timeWindow": item.get("timeWindow"),
                                "source": item.get("source"),
                                "regionKey": item.get("regionKey"),
                            }
                            for item in day.get("items", [])
                        ],
                    }
                    for day in plan.get("days", [])
                ],
            }
            print(json.dumps({label: summaries[label]}, ensure_ascii=False, indent=2))
    print("\n=== ALL PERSONAS ===")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
