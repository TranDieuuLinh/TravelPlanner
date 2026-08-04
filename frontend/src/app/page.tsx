"use client";

import { useEffect, useState } from "react";
import { UserCreateForm } from "@/modules/users/components/UserCreateForm";
import { UserList } from "@/modules/users/components/UserList";
import { userApi } from "@/modules/users/api/user-api";
import type { User } from "@/modules/users/types/user";

const productAreas = [
  "AI Planner tao lich trinh theo ngay, ngan sach va so thich",
  "Marketplace de creator dang ban plan du lich",
  "Ban do, route optimization va goi y phuong tien",
  "Thanh toan, danh gia, thanh tuu va dashboard doanh thu"
];

export default function HomePage() {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadUsers() {
    try {
      setIsLoading(true);
      setError(null);
      setUsers(await userApi.list());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Khong ket noi duoc backend");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadUsers();
  }, []);

  return (
    <main>
      <section className="hero">
        <div>
          <p className="eyebrow">VSF Travel Starter</p>
          <h1>Travel planner marketplace cho host, buyer va creator</h1>
          <p>
            Codebase Next.js + FastAPI duoc chia module de phat trien cac tinh nang tai khoan,
            lap ke hoach bang AI, marketplace, thanh toan va dashboard creator.
          </p>
        </div>
      </section>

      <section className="featureBand">
        {productAreas.map((area) => (
          <div key={area}>{area}</div>
        ))}
      </section>

      {error ? <div className="errorBox">{error}</div> : null}

      <section className="workspace">
        <UserCreateForm onCreated={loadUsers} />
        <UserList users={users} isLoading={isLoading} />
      </section>
    </main>
  );
}
