"use client";

import type { User } from "@/modules/users/types/user";

type Props = {
  users: User[];
  isLoading: boolean;
};

export function UserList({ users, isLoading }: Props) {
  return (
    <section className="panel stack">
      <div>
        <h2>Nguoi dung</h2>
        <p>Danh sach tai khoan dang co trong he thong.</p>
      </div>

      {isLoading ? <p>Dang tai...</p> : null}

      {!isLoading && users.length === 0 ? <p>Chua co nguoi dung nao.</p> : null}

      <div className="userGrid">
        {users.map((user) => (
          <article className="userCard" key={user.id}>
            <div>
              <strong>{user.fullName}</strong>
              <small>{user.email}</small>
            </div>
            <span>{user.role}</span>
            <p>{user.travelPreferences.length ? user.travelPreferences.join(", ") : "Chua co so thich"}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
