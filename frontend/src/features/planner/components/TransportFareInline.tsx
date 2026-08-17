import type { TransportOption } from "@/features/planner/api/plans";
import {
  estimateGreenSmHanoiFare,
  GREEN_SM_FARE_URL,
} from "@/features/planner/lib/green-sm-fare";
import { formatPlannerMoney } from "@/features/planner/lib/planner-budget";
import { isCarMode } from "@/features/planner/lib/transport-options";

export function TransportFareInline({ option }: { option: TransportOption }) {
  if (!isCarMode(option.mode)) {
    return null;
  }
  const fare =
    option.estimatedCostPerPerson ??
    estimateGreenSmHanoiFare(option.distanceMeters);

  return (
    <>
      <span aria-hidden="true" className="transportMetaSeparator">·</span>
      <span className="transportFareAmount">
        {formatPlannerMoney(
          fare,
          option.currency ?? "VND"
        )}
      </span>
      <a
        aria-label="Mở bảng giá GreenSM"
        className="transportFareLink"
        href={GREEN_SM_FARE_URL}
        onClick={(event) => event.stopPropagation()}
        rel="noreferrer"
        target="_blank"
        title="Bảng giá GreenSM"
      >
        GreenSM
      </a>
    </>
  );
}
