"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/features/auth/components/AuthProvider";
import { APIError } from "@/shared/api/client";

export default function RegisterPage() {
  const router = useRouter();
  const { loading, register, user } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!loading && user) router.replace("/profile");
  }, [loading, router, user]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (password.length < 10) {
      setError("Mật khẩu phải có ít nhất 10 ký tự.");
      return;
    }
    if (!/[a-z]/.test(password)) {
      setError("Mật khẩu phải có ít nhất một chữ thường.");
      return;
    }
    if (!/[A-Z]/.test(password)) {
      setError("Mật khẩu phải có ít nhất một chữ hoa.");
      return;
    }
    if (!/\d/.test(password)) {
      setError("Mật khẩu phải có ít nhất một chữ số.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Hai mật khẩu chưa trùng nhau.");
      return;
    }

    setBusy(true);
    try {
      await register(fullName, email, password);
      router.replace("/profile");
    } catch (reason) {
      if (reason instanceof APIError) {
        setError(Object.values(reason.fieldErrors)[0] ?? reason.message);
      } else {
        setError("Không thể kết nối đến backend.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="authPage">
      <section className="authPanel" aria-labelledby="register-title">
        <div className="authHeading">
          <span className="eyebrow">Bắt đầu với TravelPlanner</span>
          <h1 id="register-title">Tạo tài khoản</h1>
          <p>Một tài khoản dùng chung cho Planner và Marketplace.</p>
        </div>
        <form className="authForm" onSubmit={submit}>
          <label htmlFor="register-name">Họ và tên</label>
          <input
            autoComplete="name"
            id="register-name"
            minLength={2}
            onChange={(event) => setFullName(event.target.value)}
            required
            value={fullName}
          />
          <label htmlFor="register-email">Email</label>
          <input
            autoComplete="email"
            id="register-email"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
          <label htmlFor="register-password">Mật khẩu</label>
          <input
            aria-describedby="password-help"
            autoComplete="new-password"
            id="register-password"
            minLength={10}
            onChange={(event) => setPassword(event.target.value)}
            required
            type={showPassword ? "text" : "password"}
            value={password}
          />
          <small id="password-help">Tối thiểu 10 ký tự, có chữ hoa, chữ thường và số.</small>
          <label htmlFor="register-confirm-password">Nhập lại mật khẩu</label>
          <input
            autoComplete="new-password"
            id="register-confirm-password"
            minLength={10}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
            type={showPassword ? "text" : "password"}
            value={confirmPassword}
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
            {busy ? "Đang tạo tài khoản..." : "Tạo tài khoản"}
          </button>
        </form>
        <p className="authSwitch">Đã có tài khoản? <Link href="/login">Đăng nhập</Link></p>
      </section>
    </main>
  );
}
