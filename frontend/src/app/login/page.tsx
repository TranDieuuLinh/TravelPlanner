"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/features/auth/components/AuthProvider";
import { APIError } from "@/shared/api/client";

export default function LoginPage() {
  return <Suspense fallback={<div className="routeLoading">Đang mở đăng nhập...</div>}><LoginForm /></Suspense>;
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { loading, login, user } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestedNext = params.get("next");
  const nextPath = requestedNext?.startsWith("/") && !requestedNext.startsWith("//")
    ? requestedNext
    : "/profile";

  useEffect(() => {
    if (!loading && user) router.replace(nextPath);
  }, [loading, nextPath, router, user]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      router.replace(nextPath);
    } catch (reason) {
      setError(reason instanceof APIError ? reason.message : "Không thể kết nối đến backend.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="authPage">
      <section className="authPanel" aria-labelledby="login-title">
        <div className="authHeading">
          <span className="eyebrow">Tài khoản TravelPlanner</span>
          <h1 id="login-title">Đăng nhập</h1>
          <p>Tiếp tục quản lý hồ sơ và những chuyến đi của bạn.</p>
        </div>
        <form className="authForm" onSubmit={submit}>
          <label htmlFor="login-email">Email</label>
          <input
            autoComplete="email"
            id="login-email"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
          <label htmlFor="login-password">Mật khẩu</label>
          <input
            autoComplete="current-password"
            id="login-password"
            minLength={10}
            onChange={(event) => setPassword(event.target.value)}
            required
            type={showPassword ? "text" : "password"}
            value={password}
          />
          <label className="passwordToggle">
            <input
              checked={showPassword}
              onChange={(event) => setShowPassword(event.target.checked)}
              type="checkbox"
            />
            Hiện mật khẩu
          </label>
          {error ? <p className="authError" role="alert">{error}</p> : null}
          <button className="authSubmit" disabled={busy} type="submit">
            {busy ? "Đang đăng nhập..." : "Đăng nhập"}
          </button>
        </form>

        <div style={{ marginTop: "16px", paddingTop: "12px", borderTop: "1px solid #e2e8f0" }}>
          <p style={{ fontSize: "0.8rem", color: "#64748b", marginBottom: "8px" }}>Tài khoản thử nghiệm nhanh:</p>
          <button
            disabled={busy}
            onClick={async () => {
              setEmail("creator@example.com");
              setPassword("Password123!");
              setBusy(true);
              setError("");
              try {
                await login("creator@example.com", "Password123!");
                router.replace("/creator/listings");
              } catch (reason) {
                setError(reason instanceof APIError ? reason.message : "Không thể đăng nhập Creator.");
              } finally {
                setBusy(false);
              }
            }}
            style={{
              width: "100%",
              padding: "8px 12px",
              background: "#eef6f3",
              color: "#167c68",
              border: "1px solid #c8e4dc",
              borderRadius: "8px",
              fontSize: "0.82rem",
              fontWeight: 600,
              cursor: "pointer"
            }}
            type="button"
          >
            ⚡ Đăng nhập Creator Demo (creator@example.com)
          </button>
        </div>

        <p className="authSwitch">Chưa có tài khoản? <Link href="/register">Đăng ký</Link></p>
      </section>
    </main>
  );
}
