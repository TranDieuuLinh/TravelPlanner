import { z } from "zod";

export const userCreateSchema = z.object({
  email: z.string().email("Email khong hop le"),
  fullName: z.string().min(2, "Ten can it nhat 2 ky tu"),
  role: z.enum(["traveler", "host", "creator", "admin"]).default("traveler"),
  travelPreferences: z.string().optional()
});

export type UserCreateInput = z.infer<typeof userCreateSchema>;
