"use client";

import { useMemo, useState, type CSSProperties, type FormEvent } from "react";

type GroupPlanningPanelProps = {
  chatId: string | null;
  currentUserName?: string | null;
  destination: string;
};

type GroupTool = "where" | "when" | "spending";
type GroupMember = { id: string; name: string; location: string };
type GroupExpense = { id: string; title: string; amount: number; paidBy: string };

const DAYS = ["T6, 14/8", "T7, 15/8", "CN, 16/8", "T2, 17/8"];
const TIMES = ["09:00", "12:00", "15:00", "18:00", "20:00"];

function initials(name: string) {
  return name
    .trim()
    .split(/\s+/)
    .slice(-2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function money(value: number) {
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(value);
}

function ShareIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="18" cy="5" r="2.5" />
      <circle cx="6" cy="12" r="2.5" />
      <circle cx="18" cy="19" r="2.5" />
      <path d="m8.2 10.8 7.6-4.5M8.2 13.2l7.6 4.5" />
    </svg>
  );
}

export function GroupPlanningPanel({
  chatId,
  currentUserName,
  destination,
}: GroupPlanningPanelProps) {
  const ownerName = currentUserName?.trim() || "Bạn";
  const [activeTool, setActiveTool] = useState<GroupTool>("where");
  const [members, setMembers] = useState<GroupMember[]>([
    { id: "owner", name: ownerName, location: "" },
    { id: "mai", name: "Mai", location: "" },
    { id: "nam", name: "Nam", location: "" },
  ]);
  const [newMember, setNewMember] = useState("");
  const [shareState, setShareState] = useState<"idle" | "copied" | "failed">("idle");
  const [meetingPointVisible, setMeetingPointVisible] = useState(false);
  const [selectedAvailabilityMember, setSelectedAvailabilityMember] = useState("owner");
  const [availability, setAvailability] = useState<Record<string, string[]>>({
    owner: ["0-2", "0-3", "1-2", "1-3", "2-1", "2-2"],
    mai: ["0-3", "0-4", "1-2", "1-3", "2-2", "2-3"],
    nam: ["0-1", "0-2", "0-3", "1-3", "2-2", "2-3"],
  });
  const [expenses, setExpenses] = useState<GroupExpense[]>([
    { id: "hotel", title: "Khách sạn", amount: 2400000, paidBy: "owner" },
    { id: "taxi", title: "Taxi sân bay", amount: 360000, paidBy: "mai" },
  ]);
  const [expenseTitle, setExpenseTitle] = useState("");
  const [expenseAmount, setExpenseAmount] = useState("");
  const [expensePayer, setExpensePayer] = useState("owner");

  const filledLocations = members.filter((member) => member.location.trim());
  const availabilityScores = useMemo(() => {
    const scores: Record<string, number> = {};
    for (let day = 0; day < DAYS.length; day += 1) {
      for (let time = 0; time < TIMES.length; time += 1) {
        const key = `${day}-${time}`;
        scores[key] = members.reduce(
          (score, member) => score + (availability[member.id]?.includes(key) ? 1 : 0),
          0
        );
      }
    }
    return scores;
  }, [availability, members]);
  const bestAvailability = Math.max(0, ...Object.values(availabilityScores));
  const totalExpenses = expenses.reduce((sum, expense) => sum + expense.amount, 0);
  const sharePerPerson = members.length ? totalExpenses / members.length : 0;

  async function copyInviteLink() {
    const url = new URL(window.location.href);
    if (chatId) url.searchParams.set("chatId", chatId);
    url.searchParams.set("group", "join");
    try {
      await navigator.clipboard.writeText(url.toString());
      setShareState("copied");
    } catch {
      setShareState("failed");
    }
  }

  function addMember(event: FormEvent) {
    event.preventDefault();
    const name = newMember.trim();
    if (!name) return;
    const id = `member-${Date.now()}`;
    setMembers((current) => [...current, { id, name, location: "" }]);
    setAvailability((current) => ({ ...current, [id]: [] }));
    setNewMember("");
  }

  function toggleAvailability(key: string) {
    setAvailability((current) => {
      const selected = current[selectedAvailabilityMember] ?? [];
      return {
        ...current,
        [selectedAvailabilityMember]: selected.includes(key)
          ? selected.filter((item) => item !== key)
          : [...selected, key],
      };
    });
  }

  function addExpense(event: FormEvent) {
    event.preventDefault();
    const amount = Number(expenseAmount.replace(/[^0-9]/g, ""));
    if (!expenseTitle.trim() || !Number.isFinite(amount) || amount <= 0) return;
    setExpenses((current) => [
      ...current,
      { id: `expense-${Date.now()}`, title: expenseTitle.trim(), amount, paidBy: expensePayer },
    ]);
    setExpenseTitle("");
    setExpenseAmount("");
  }

  return (
    <section aria-labelledby="group-planning-title" className="groupPlanningPanel">
      <header className="groupPlanningHeader">
        <div>
          <span className="groupPreviewBadge">Bản xem trước · lưu trên thiết bị này</span>
          <h2 id="group-planning-title">Cùng nhau lên kế hoạch {destination}</h2>
          <p>Mời bạn bè, chốt điểm gặp, giờ rảnh và chia chi phí trong một chỗ.</p>
        </div>
        <button className="groupShareButton" onClick={() => void copyInviteLink()} type="button">
          <ShareIcon />
          {shareState === "copied" ? "Đã sao chép link" : shareState === "failed" ? "Không sao chép được" : "Chia sẻ"}
        </button>
      </header>

      <div className="groupMemberStrip">
        <div className="groupMemberAvatars" aria-label={`${members.length} thành viên`}>
          {members.slice(0, 5).map((member) => (
            <span key={member.id} title={member.name}>{initials(member.name)}</span>
          ))}
        </div>
        <div><strong>{members.length} người đang lên kế hoạch</strong><small>Ai có link đều có thể mở bản xem trước này.</small></div>
        <form onSubmit={addMember}>
          <input aria-label="Tên thành viên mới" onChange={(event) => setNewMember(event.target.value)} placeholder="Thêm tên bạn bè" value={newMember} />
          <button type="submit">Thêm</button>
        </form>
      </div>

      <nav aria-label="Công cụ nhóm" className="groupToolTabs">
        <button className={activeTool === "where" ? "active" : ""} onClick={() => setActiveTool("where")} type="button"><span>⌖</span><strong>Gặp ở đâu?</strong><small>Tìm điểm ở giữa</small></button>
        <button className={activeTool === "when" ? "active" : ""} onClick={() => setActiveTool("when")} type="button"><span>◷</span><strong>Gặp khi nào?</strong><small>So lịch rảnh</small></button>
        <button className={activeTool === "spending" ? "active" : ""} onClick={() => setActiveTool("spending")} type="button"><span>₫</span><strong>Chi tiêu nhóm</strong><small>Chia tiền công bằng</small></button>
      </nav>

      {activeTool === "where" ? (
        <div className="groupWhereLayout">
          <div className="groupToolCard">
            <header><span>01</span><div><h3>Mọi người xuất phát từ đâu?</h3><p>Nhập khu vực hoặc địa chỉ gần đúng của từng người.</p></div></header>
            <div className="groupLocationList">
              {members.map((member) => (
                <label key={member.id}>
                  <span>{initials(member.name)}</span>
                  <div><strong>{member.name}</strong><input onChange={(event) => {
                    const location = event.target.value;
                    setMembers((current) => current.map((item) => item.id === member.id ? { ...item, location } : item));
                    setMeetingPointVisible(false);
                  }} placeholder="Nhập vị trí" value={member.location} /></div>
                </label>
              ))}
            </div>
            <button className="groupPrimaryAction" disabled={filledLocations.length < 2} onClick={() => setMeetingPointVisible(true)} type="button">Tìm điểm gặp ở giữa</button>
          </div>
          <div className={meetingPointVisible ? "groupMeetingMap has-result" : "groupMeetingMap"}>
            <div className="groupMapRoad roadOne" /><div className="groupMapRoad roadTwo" />
            {filledLocations.slice(0, 4).map((member, index) => <span className={`groupMapPin pin-${index + 1}`} key={member.id}>{initials(member.name)}</span>)}
            {meetingPointVisible ? <div className="groupMeetingPoint"><span>★</span><strong>Điểm gặp gợi ý</strong><small>Khu vực trung tâm giữa {filledLocations.length} vị trí</small></div> : <div className="groupMapEmpty"><span>⌖</span><strong>Bản đồ điểm gặp</strong><small>Thêm ít nhất 2 vị trí để xem điểm ở giữa.</small></div>}
            <span className="groupMapDisclaimer">Bản đồ minh hoạ</span>
          </div>
        </div>
      ) : null}

      {activeTool === "when" ? (
        <div className="groupToolCard groupWhenCard">
          <header><span>02</span><div><h3>Chọn tất cả lúc bạn rảnh</h3><p>Ô càng đậm nghĩa là càng nhiều người cùng rảnh — giống When2meet.</p></div></header>
          <div className="availabilityMembers">
            {members.map((member) => <button className={selectedAvailabilityMember === member.id ? "active" : ""} key={member.id} onClick={() => setSelectedAvailabilityMember(member.id)} type="button"><span>{initials(member.name)}</span>{member.name}</button>)}
          </div>
          <div className="availabilityScroll">
            <div className="availabilityGrid" style={{ "--group-count": members.length } as CSSProperties}>
              <span />{DAYS.map((day) => <strong key={day}>{day}</strong>)}
              {TIMES.map((time, timeIndex) => [
                <small key={`${time}-label`}>{time}</small>,
                ...DAYS.map((day, dayIndex) => {
                  const key = `${dayIndex}-${timeIndex}`;
                  const score = availabilityScores[key] ?? 0;
                  const selected = availability[selectedAvailabilityMember]?.includes(key);
                  return <button aria-label={`${day}, ${time}: ${score}/${members.length} người rảnh`} className={`${selected ? "selected" : ""} ${score === bestAvailability && score > 1 ? "best" : ""}`} key={key} onClick={() => toggleAvailability(key)} style={{ "--availability": score } as CSSProperties} type="button"><span>{score || ""}</span></button>;
                }),
              ])}
            </div>
          </div>
          <p className="availabilityHint"><span /> Khung đậm nhất hiện có <strong>{bestAvailability}/{members.length} người</strong> cùng rảnh.</p>
        </div>
      ) : null}

      {activeTool === "spending" ? (
        <div className="groupSpendingLayout">
          <div className="groupToolCard">
            <header><span>03</span><div><h3>Thêm khoản chi chung</h3><p>Tạm tính chia đều cho tất cả thành viên.</p></div></header>
            <form className="groupExpenseForm" onSubmit={addExpense}>
              <label><span>Nội dung</span><input onChange={(event) => setExpenseTitle(event.target.value)} placeholder="Ví dụ: Vé tàu" value={expenseTitle} /></label>
              <label><span>Số tiền</span><input inputMode="numeric" onChange={(event) => setExpenseAmount(event.target.value)} placeholder="500.000" value={expenseAmount} /></label>
              <label><span>Người trả</span><select onChange={(event) => setExpensePayer(event.target.value)} value={expensePayer}>{members.map((member) => <option key={member.id} value={member.id}>{member.name}</option>)}</select></label>
              <button className="groupPrimaryAction" type="submit">Thêm khoản chi</button>
            </form>
          </div>
          <div className="groupExpenseSummary">
            <header><div><span>Tổng chi nhóm</span><strong>{money(totalExpenses)}</strong></div><small>{money(sharePerPerson)} / người</small></header>
            <div className="groupExpenseList">
              {expenses.map((expense) => {
                const payer = members.find((member) => member.id === expense.paidBy)?.name ?? "Thành viên";
                return <article key={expense.id}><span>₫</span><div><strong>{expense.title}</strong><small>{payer} đã trả</small></div><b>{money(expense.amount)}</b><button aria-label={`Xóa ${expense.title}`} onClick={() => setExpenses((current) => current.filter((item) => item.id !== expense.id))} type="button">×</button></article>;
              })}
            </div>
            <p>Chỉ là phép tính nháp; chưa tạo giao dịch hoặc yêu cầu thanh toán thật.</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
