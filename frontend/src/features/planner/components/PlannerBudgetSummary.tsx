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

const HANOI_TURTLE_TOWER_IMAGE = "/images/hanoi-turtle-tower.jpg";

const budgetIcons = {
  travelPlaces: <path d="M12 21s6-5.2 6-11a6 6 0 1 0-12 0c0 5.8 6 11 6 11Z M12 12.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />,
  food: <path d="M7 3v7M4.5 3v4.5a2.5 2.5 0 0 0 5 0V3M7 10v11M16 3v18M16 3c2 1.7 3 3.8 3 6v2h-3" />,
  accommodation: <path d="M3 20V5M3 15h18v5M7 15v-5h5a3 3 0 0 1 3 3v2M7 10h3" />,
  transportation: <path d="m5 16-1 3M19 16l1 3M5 16h14l-1.2-7H6.2L5 16ZM7 9l1-3h8l1 3M7 19h2M15 19h2" />,
} as const;
type BudgetIconKey = keyof typeof budgetIcons;

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
  const budgetItems = ([
    { key: "travelPlaces", label: "Địa điểm", value: budget.travelPlaces },
    { key: "food", label: "Ăn uống", value: budget.food },
    {
      key: "accommodation",
      label: plan.accommodation?.nights
        ? `Lưu trú · ${plan.accommodation.nights} đêm`
        : "Lưu trú",
      value: budget.accommodation,
    },
    { key: "transportation", label: "Di chuyển", value: budget.transportation },
  ] as Array<{ key: BudgetIconKey; label: string; value: number }>).map((item) => ({
    ...item,
    share: budget.perPersonTotal > 0 ? (item.value / budget.perPersonTotal) * 100 : 0,
  }));

  return (
    <section aria-label="Tóm tắt ngân sách chuyến đi" className="plannerBudgetCard">
      <div className="plannerBudgetHero">
        <div className="plannerBudgetArtwork">
          <img
            src={HANOI_TURTLE_TOWER_IMAGE}
            alt="Tháp Rùa bên Hồ Gươm, Hà Nội"
            className="plannerBudgetTowerPhoto"
            referrerPolicy="no-referrer"
          />
          <svg className="plannerBudgetTowerFallback" viewBox="0 0 260 280" aria-hidden="true">
            <defs>
              <linearGradient id="towerSky" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor="#dff3f1" />
                <stop offset="1" stopColor="#f8faf3" />
              </linearGradient>
              <linearGradient id="towerLake" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor="#a8dcd5" />
                <stop offset="1" stopColor="#e4f3ec" />
              </linearGradient>
            </defs>
            <rect width="260" height="280" fill="url(#towerSky)" />
            <circle cx="206" cy="48" r="24" fill="#fff5c7" opacity=".8" />
            <path d="M0 175c45-17 78-10 121 2 42 12 79 10 139-7v110H0Z" fill="url(#towerLake)" />
            <path d="M36 211c38-11 62-10 102 0 36 9 69 9 105-1" fill="none" stroke="#82c9c0" strokeWidth="3" opacity=".65" />
            <path d="M101 202h57l-7-89h-43Z" fill="#eee6c7" stroke="#897959" strokeWidth="2" />
            <path d="M94 113h71l-15-13h-41Z" fill="#6a7b68" stroke="#53624f" strokeWidth="2" />
            <path d="M111 96h38l-8-20h-22Z" fill="#e8dfbb" stroke="#897959" strokeWidth="2" />
            <path d="M118 76h24l-12-17Z" fill="#61735f" stroke="#53624f" strokeWidth="2" />
            <path d="M91 202h78" stroke="#6c846d" strokeWidth="7" strokeLinecap="round" />
            <path d="M112 128h13v19h-13ZM136 128h13v19h-13ZM112 157h13v19h-13ZM136 157h13v19h-13Z" fill="#66806c" />
            <path d="M66 221c10-14 21-17 34-18M174 204c13-2 25 3 35 16" fill="none" stroke="#63966f" strokeWidth="7" strokeLinecap="round" />
          </svg>
        </div>
        <div className="plannerBudgetHeroContent">
          <header>
            <div className="plannerBudgetHeading">
              <span className="plannerBudgetLocationIcon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 21s6-5.2 6-11a6 6 0 1 0-12 0c0 5.8 6 11 6 11Z M12 12.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" /></svg></span>
              <strong>{plan.destination}</strong>
              <span aria-hidden="true">·</span>
              <small>{plan.days.length} ngày</small>
            </div>
          </header>
          <div className="plannerBudgetTotalRow">
            <div className="plannerBudgetTotal">
              <span>Chi phí dự kiến <span className="plannerBudgetInfo" title="Tổng chi phí ước tính cho toàn bộ chuyến đi">i</span></span>
              <strong>{formatPlannerMoney(budget.perPersonTotal, budget.currency)}</strong>
            </div>
            <span className="plannerBudgetBasis">mỗi người</span>
          </div>
          <p className="plannerBudgetExplanation">Tổng chi phí ước tính cho toàn bộ chuyến đi</p>
          {userBudget == null ? null : (
            <p className={`plannerBudgetTarget ${budgetDifference != null && budgetDifference < 0 ? "is-over" : ""}`}>
              Ngân sách của bạn: <strong>{formatPlannerMoney(userBudget, budget.currency)}</strong>
              {budgetDifference == null ? null : ` · ${budgetDifference < 0 ? "Vượt" : "Còn lại"} ${formatPlannerMoney(Math.abs(budgetDifference), budget.currency)}`}
            </p>
          )}
        </div>
      </div>
      <details className="plannerBudgetDistribution">
        <summary className="plannerBudgetDistributionHeader">
          <strong>Phân bổ chi phí</strong>
          <span className="plannerBudgetDetailsDropdown">Xem chi tiết</span>
        </summary>
        <div className="plannerBudgetItems" aria-label="Chi phí theo hạng mục">
          {budgetItems.map((item) => (
            <div className={`plannerBudgetItem plannerBudgetItem--${item.key}`} key={item.key}>
              <div className="plannerBudgetItemHeading">
                <span className="plannerBudgetItemIcon" aria-hidden="true"><svg viewBox="0 0 24 24">{budgetIcons[item.key]}</svg></span>
                <span>{item.label}</span>
              </div>
              <strong>{formatPlannerMoney(item.value, budget.currency)}</strong>
              <div className="plannerBudgetMeter" aria-hidden="true"><span style={{ width: `${item.share}%` }} /></div>
              <small>{item.share.toFixed(1)}%</small>
            </div>
          ))}
        </div>
      </details>
      {visibleNotes.length ? (
        <p className="plannerBudgetNotes">{visibleNotes.join(" · ")}</p>
      ) : null}
    </section>
  );
}
