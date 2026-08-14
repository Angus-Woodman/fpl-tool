import type { Metadata } from "next";
import "./globals.css";

import { AppShell } from "@/components/layout/app-shell";

export const metadata: Metadata = {
  title: "FPL Tool",
  description: "Local-first Fantasy Premier League decision support",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
