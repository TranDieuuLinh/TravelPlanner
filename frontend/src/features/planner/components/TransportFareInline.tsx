import type { TransportOption } from "@/features/planner/api/plans";
import {
  GREEN_SM_FARE_URL,
  resolveTransportGroupFare,
} from "@/features/planner/lib/green-sm-fare";
import { formatPlannerMoney } from "@/features/planner/lib/planner-budget";
import { isCarMode } from "@/features/planner/lib/transport-options";

export function TransportFareInline({
  option,
  travelerCount,
}: {
  option: TransportOption;
  travelerCount: number;
}) {
  if (!isCarMode(option.mode)) {
    return null;
  }
  const fare = resolveTransportGroupFare(
    option.distanceMeters,
    option.estimatedCostPerPerson,
    travelerCount,
  );

  return (
    <>
      <span aria-hidden="true" className="transportMetaSeparator">·</span>
      <span className="transportFareAmount">
        {formatPlannerMoney(
          fare,
          option.currency ?? "VND"
        )}
      </span>
      <small className="transportFareBasis">tổng nhóm</small>
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
