import type { TravelPlan } from "@/features/planner/api/plans";
import {
  formatPlannerMoney,
  plannerBudgetBreakdown,
} from "@/features/planner/lib/planner-budget";

type PlannerBudgetSummaryProps = {
  budgetTarget?: number | null;
  notes?: string[];
  plan: TravelPlan;
};

export function PlannerBudgetSummary({
  budgetTarget,
  notes = [],
  plan,
}: PlannerBudgetSummaryProps) {
  const budget = plannerBudgetBreakdown(plan);
  const userBudget =
    budgetTarget ??
    (plan.budget?.source === "explicit"
      ? plan.budget.amountPerPerson
      : null);
  const budgetDifference =
    userBudget == null ? null : userBudget - budget.perPersonTotal;
  const visibleNotes = notes.map((note) => note.trim()).filter(Boolean);
  const budgetGroups = [
    {
      key: "perPerson",
      label: "Tổng / người",
      total: budget.perPersonTotal,
      items: [
        { key: "travelPlaces", label: "Địa điểm", value: budget.travelPlaces },
        { key: "food", label: "Ăn uống", value: budget.food },
      ],
    },
    {
      key: "group",
      label: "Tổng nhóm",
      total: budget.groupTotal,
      items: [
        {
          key: "accommodation",
          label: plan.accommodation?.nights
            ? `Khách sạn · ${plan.accommodation.nights} đêm`
            : "Khách sạn",
          value: budget.accommodation,
        },
        { key: "transportation", label: "Di chuyển", value: budget.transportation },
      ],
    },
  ] as const;

  return (
    <section
      aria-label="Tóm tắt ngân sách chuyến đi"
      className="plannerBudgetCard"
    >
      <header>
        <div className="plannerBudgetHeading">
          <strong>{plan.destination}</strong>
          <span aria-hidden="true">·</span>
          <small>{plan.days.length} ngày</small>
        </div>
        <div className="plannerBudgetTarget">
          <span>Ngân sách</span>
          <strong>
            {userBudget == null
              ? "Chưa đặt"
              : formatPlannerMoney(userBudget, budget.currency)}
          </strong>
          {budgetDifference == null ? null : (
            <small className={budgetDifference < 0 ? "is-over" : "is-within"}>
              {budgetDifference < 0 ? "Vượt" : "Còn lại"}{" "}
              {formatPlannerMoney(Math.abs(budgetDifference), budget.currency)}
            </small>
          )}
        </div>
      </header>
      <div className="plannerBudgetComparison">
        {budgetGroups.map((group) => (
          <div className={`plannerBudgetGroup plannerBudgetGroup--${group.key}`} key={group.key}>
            <div className="plannerBudgetTotal">
              <span>{group.label}</span>
              <strong>{formatPlannerMoney(group.total, budget.currency)}</strong>
            </div>
            <div className="plannerBudgetGroupDetails">
              {group.items.map((item) => (
                <div
                  className={`plannerBudgetItem plannerBudgetItem--${item.key}`}
                  key={item.key}
                >
                  <span>{item.label}</span>
                  <strong>{formatPlannerMoney(item.value, budget.currency)}</strong>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="plannerBudgetNotes">
        <span>Lưu ý</span>
        <p>
          {visibleNotes.length ? visibleNotes.join(" · ") : "Chưa có lưu ý"}
        </p>
      </div>
    </section>
  );
}
