"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { userApi } from "@/modules/users/api/user-api";
import { userCreateSchema, type UserCreateInput } from "@/modules/users/schemas/user-schema";

type Props = {
  onCreated: () => void;
};

export function UserCreateForm({ onCreated }: Props) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting }
  } = useForm<UserCreateInput>({
    resolver: zodResolver(userCreateSchema),
    defaultValues: {
      role: "traveler"
    }
  });

  async function onSubmit(input: UserCreateInput) {
    await userApi.create({
      email: input.email,
      fullName: input.fullName,
      role: input.role,
      travelPreferences: input.travelPreferences
        ? input.travelPreferences.split(",").map((item) => item.trim()).filter(Boolean)
        : []
    });
    reset({ role: "traveler" });
    onCreated();
  }

  return (
    <form className="panel stack" onSubmit={handleSubmit(onSubmit)}>
      <div>
        <h2>Them nguoi dung</h2>
        <p>Tao traveler, host hoac creator dau tien cho workspace.</p>
      </div>

      <label>
        Email
        <input type="email" placeholder="creator@vsf.travel" {...register("email")} />
        {errors.email ? <span>{errors.email.message}</span> : null}
      </label>

      <label>
        Ho ten
        <input placeholder="Linh Tran" {...register("fullName")} />
        {errors.fullName ? <span>{errors.fullName.message}</span> : null}
      </label>

      <label>
        Vai tro
        <select {...register("role")}>
          <option value="traveler">Traveler</option>
          <option value="host">Host</option>
          <option value="creator">Creator</option>
          <option value="admin">Admin</option>
        </select>
      </label>

      <label>
        So thich du lich
        <input placeholder="bien, am thuc, di bo" {...register("travelPreferences")} />
      </label>

      <button disabled={isSubmitting} type="submit">
        {isSubmitting ? "Dang tao..." : "Tao nguoi dung"}
      </button>
    </form>
  );
}
