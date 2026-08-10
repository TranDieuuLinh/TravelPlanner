"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { login, type AdminUser } from "../../lib/api/auth";

export default function LoginScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      router.push("/runs");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Không thể đăng nhập."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="loginPage">
      <section className="loginStory">
        <div className="brandMark">TravelPlanner</div>
        <p className="eyebrow">Planning control</p>
        <h1>Nhìn xuyên suốt từng quyết định của lịch trình.</h1>
        <p className="loginLead">
          Một bề mặt vận hành riêng cho Explorer, Planner, Finder và Checker —
          đủ chi tiết để điều tra, đủ an toàn để không phơi dữ liệu thô.
        </p>
        <div className="signalStrip" aria-label="Các stage được quan sát">
          {["Explorer", "Planner", "Finder", "Checker"].map((stage, index) => (
            <span key={stage}>
              <b>0{index + 1}</b>
              {stage}
            </span>
          ))}
        </div>
      </section>
      <section className="loginPanel">
        <form onSubmit={submit} className="loginCard">
          <p className="eyebrow">Khu vực hạn chế</p>
          <h2>Đăng nhập quản trị</h2>
          <p>Dùng tài khoản TravelPlanner có role admin.</p>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              placeholder="admin@travelplanner.local"
              required
            />
          </label>
          <label>
            Mật khẩu
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              placeholder="••••••••••••"
              required
            />
          </label>
          {error && <div className="formError">{error}</div>}
          <button type="submit" disabled={busy}>
            {busy ? "Đang xác thực…" : "Vào Planning Control"}
          </button>
          <small>
            Input nhạy cảm, media và toàn bộ prompt không được lưu trong console.
          </small>
        </form>
      </section>
    </main>
  );
}
