import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { AppShell } from "@/components/AppShell";
import { AuthProvider } from "@/features/auth/components/AuthProvider";

export const metadata: Metadata = {
  title: "TravelPlanner",
  description: "Khám phá plan du lịch và tạo lịch trình với AI.",
  icons: {
    icon: "/images/penguin-logo.png",
    apple: "/images/penguin-logo.png",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#f6f7fb",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html data-scroll-behavior="smooth" lang="vi">
      <body>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
