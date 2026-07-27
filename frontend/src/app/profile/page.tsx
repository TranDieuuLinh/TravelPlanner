"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

type Role = "buyer" | "creator" | "admin";

const buyerTransactions = [
  ["ORD-DEMO-1042", "Đà Nẵng & Hội An", "149.000đ", "Đã cấp quyền", "24/07/2026"],
  ["ORD-DEMO-0988", "Ninh Bình cuối tuần", "99.000đ", "Hoàn tiền", "12/07/2026"],
  ["ORD-DEMO-0916", "48 giờ ăn Hải Phòng", "79.000đ", "Đã cấp quyền", "28/06/2026"]
];

const creatorTransactions = [
  ["SALE-DEMO-8831", "Đà Nẵng & Hội An", "+126.650đ", "Khả dụng", "26/07/2026"],
  ["SALE-DEMO-8824", "Đà Nẵng & Hội An", "+126.650đ", "Đang chờ", "25/07/2026"],
  ["RFND-DEMO-0211", "Food tour miền Trung", "-67.150đ", "Hoàn tiền", "23/07/2026"]
];

const systemTransactions = [
  ["PAY-DEMO-98122", "buyer_1042", "Thanh toán", "149.000đ", "Thành công"],
  ["RFND-DEMO-2138", "admin_01", "Hoàn tiền", "99.000đ", "Đã xử lý"],
  ["PAY-DEMO-98121", "buyer_0998", "Thanh toán", "189.000đ", "Thất bại"],
  ["PAY-DEMO-98120", "buyer_0872", "Thanh toán", "79.000đ", "Đang chờ"]
];

const traceLogs = [
  ["11:45:20", "req_demo_8fa2", "creator_203", "listing.publish", "listing_demo_42", "200"],
  ["11:42:18", "req_demo_8f9e", "buyer_1042", "checkout.create", "order_demo_1042", "201"],
  ["11:31:06", "req_demo_8f7c", "admin_01", "refund.approve", "refund_demo_2138", "200"],
  ["11:28:51", "req_demo_8f61", "anonymous", "plan.generate", "job_demo_701", "429"],
  ["11:22:43", "req_demo_8f40", "buyer_0998", "payment.webhook", "payment_demo_98121", "400"]
];

export default function ProfilePage() {
  return <Suspense fallback={<div className="routeLoading">Đang mở hồ sơ…</div>}><Profile /></Suspense>;
}

function Profile() {
  const params = useSearchParams();
  const requested = params.get("mode");
  const [role, setRole] = useState<Role>(requested === "creator" || requested === "admin" ? requested : "buyer");
  const [tab, setTab] = useState("Tổng quan");
  const [query, setQuery] = useState("");

  const tabs = role === "buyer"
    ? ["Tổng quan", "Chuyến đi", "Giao dịch"]
    : role === "creator"
      ? ["Tổng quan", "Listing", "Giao dịch"]
      : ["Tổng quan", "Trace log", "Giao dịch hệ thống", "Báo cáo"];

  const filteredLogs = useMemo(() => traceLogs.filter((row) => row.join(" ").toLowerCase().includes(query.toLowerCase())), [query]);

  function changeRole(next: Role) {
    setRole(next);
    setTab("Tổng quan");
  }

  return (
    <main className="profilePage pageWidth">
      <section className="roleBar">
        <div><strong>Chế độ xem</strong><span>Authentication, payment và audit backend chưa được triển khai — dữ liệu bên dưới là demo.</span></div>
        <div className="roleButtons">
          <button className={role === "buyer" ? "active" : ""} onClick={() => changeRole("buyer")} type="button">Traveler</button>
          <button className={role === "creator" ? "active" : ""} onClick={() => changeRole("creator")} type="button">Creator</button>
          <button className={role === "admin" ? "active admin" : ""} onClick={() => changeRole("admin")} type="button">Admin</button>
        </div>
      </section>

      {role === "admin" ? (
        <section className="adminHero">
          <div><span className="eyebrow">Admin console · Demo</span><h1>Vận hành & truy vết</h1><p>Theo dõi request, giao dịch và hàng đợi cần xử lý.</p></div>
          <div className="systemLive"><span />Demo environment</div>
        </section>
      ) : (
        <section className="profileHero">
          <div className={role === "creator" ? "profileAvatar creator" : "profileAvatar"}>T</div>
          <div className="profileIntro">
            <div className="profileName"><h1>nguyenminhtuan</h1><span>✓</span>{role === "creator" ? <Link href="/planner">＋ Tạo plan</Link> : null}</div>
            <p>{role === "creator" ? "Creator chuyên lịch trình ẩm thực và chuyến đi nhóm tại miền Trung." : "Thích food tour, road trip và lịch trình có nhịp độ vừa phải."}</p>
            <div className="profileNumbers">
              {role === "buyer" ? <><div><strong>8</strong><span>chuyến đi</span></div><div><strong>12</strong><span>plan đã lưu</span></div><div><strong>3</strong><span>giao dịch</span></div></> : <><div><strong>6</strong><span>listing</span></div><div><strong>128</strong><span>lượt mua</span></div><div><strong>4,8</strong><span>đánh giá</span></div></>}
            </div>
          </div>
        </section>
      )}

      <nav className="profileTabs" aria-label="Nội dung hồ sơ">
        {tabs.map((item) => <button className={tab === item ? "active" : ""} key={item} onClick={() => setTab(item)} type="button">{item}</button>)}
      </nav>

      {role === "buyer" ? <BuyerContent tab={tab} /> : null}
      {role === "creator" ? <CreatorContent tab={tab} /> : null}
      {role === "admin" ? <AdminContent filteredLogs={filteredLogs} query={query} setQuery={setQuery} tab={tab} setTab={setTab} /> : null}
    </main>
  );
}

function BuyerContent({ tab }: { tab: string }) {
  if (tab === "Giao dịch") return <TransactionTable rows={buyerTransactions} subtitle="Order và quyền truy cập plan minh họa cho luồng Traveler." title="Giao dịch mua plan" />;
  if (tab === "Chuyến đi") return <Trips />;
  return (
    <section className="profileSection">
      <div className="sectionTitle compact"><div><span className="eyebrow">Traveler</span><h2>Chuyến đi sắp tới</h2></div></div>
      <Trips />
    </section>
  );
}

function Trips() {
  return <div className="tripCards">{[["Đà Nẵng & Hội An", "12–15/08", "82%"], ["Hà Giang", "15–18/09", "45%"], ["Ninh Bình", "Đã hoàn thành", "100%"]].map((trip) => <article key={trip[0]}><span>{trip[1]}</span><h3>{trip[0]}</h3><div className="progress"><i style={{ width: trip[2] }} /></div><div><small>Hoàn thiện {trip[2]}</small><Link href={`/planner?destination=${encodeURIComponent(trip[0])}`}>Mở plan →</Link></div></article>)}</div>;
}

function CreatorContent({ tab }: { tab: string }) {
  if (tab === "Giao dịch") return <TransactionTable rows={creatorTransactions} subtitle="Doanh thu, số dư và hoàn tiền minh họa cho Creator." title="Giao dịch bán plan" />;
  if (tab === "Listing") return <ListingTable />;
  return (
    <section className="profileSection">
      <div className="metricGrid"><Metric label="Lượt xem tháng này" value="8.420" note="+12% so với tháng trước" /><Metric label="Lượt mua demo" value="128" note="Tỷ lệ chuyển đổi 3,4%" /><Metric label="Doanh thu demo" value="6,6 triệu" note="Chưa kết nối payment" /></div>
      <div className="sectionTitle compact"><div><span className="eyebrow">Creator Studio</span><h2>Listing gần đây</h2></div></div>
      <ListingTable />
    </section>
  );
}

function ListingTable() {
  return <DataTable headers={["Listing", "Trạng thái", "Giá", "Lượt mua"]} rows={[["Đà Nẵng & Hội An", "Published demo", "149.000đ", "84"], ["Food tour miền Trung", "Review demo", "79.000đ", "31"], ["Huế cho người đi lần đầu", "Draft", "—", "—"]]} />;
}

function AdminContent({ tab, query, setQuery, filteredLogs, setTab }: { tab: string; query: string; setQuery: (value: string) => void; filteredLogs: string[][]; setTab: (value: string) => void }) {
  if (tab === "Trace log") return <section className="profileSection"><div className="tableTitle"><div><h2>Trace log</h2><p>Request ID và audit event minh họa; chưa đọc log backend thật.</p></div><input aria-label="Tìm trace log" onChange={(event) => setQuery(event.target.value)} placeholder="Tìm request, actor, action..." value={query} /></div><DataTable headers={["Thời gian", "Request ID", "Actor", "Action", "Resource", "HTTP"]} rows={filteredLogs} /></section>;
  if (tab === "Giao dịch hệ thống") return <section className="profileSection"><div className="tableTitle"><div><h2>Giao dịch hệ thống</h2><p>Payment, refund và trạng thái đang là dữ liệu demo.</p></div></div><DataTable headers={["Mã", "Actor", "Loại", "Số tiền", "Trạng thái"]} rows={systemTransactions} /></section>;
  if (tab === "Báo cáo") return <section className="profileSection"><div className="reportGrid">{[["12", "Listing chờ duyệt"], ["4", "Refund cần kiểm tra"], ["7", "Báo cáo nội dung"]].map((item) => <article key={item[1]}><strong>{item[0]}</strong><h3>{item[1]}</h3><button disabled type="button">Mở hàng đợi</button></article>)}</div></section>;
  return <section className="profileSection"><div className="metricGrid four"><Metric label="Request hôm nay" value="18.420" note="99,4% thành công" /><Metric label="Giao dịch demo" value="426" note="4 cần kiểm tra" /><Metric label="Trace lỗi" value="17" note="2 lỗi mức cao" /><Metric label="Listing chờ duyệt" value="12" note="Tuổi hàng đợi: 4 giờ" /></div><div className="adminShortcuts"><button onClick={() => setTab("Trace log")} type="button"><span>⌁</span><strong>Mở Trace log</strong><small>Tìm request và audit event</small></button><button onClick={() => setTab("Giao dịch hệ thống")} type="button"><span>₫</span><strong>Xem giao dịch</strong><small>Payment, refund và trạng thái</small></button></div></section>;
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return <article className="metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function TransactionTable({ rows, title, subtitle }: { rows: string[][]; title: string; subtitle: string }) {
  return <section className="profileSection"><div className="tableTitle"><div><h2>{title}</h2><p>{subtitle}</p></div><span className="demoLabel">Dữ liệu demo</span></div><DataTable headers={["Mã giao dịch", "Plan", "Số tiền", "Trạng thái", "Ngày"]} rows={rows} /></section>;
}

function DataTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return <div className="tableWrap"><table><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={`${row[0]}-${rowIndex}`}>{row.map((cell, index) => <td key={`${cell}-${index}`}>{index === 0 && cell.includes("DEMO") ? <code>{cell}</code> : cell}</td>)}</tr>)}</tbody></table></div>;
}
