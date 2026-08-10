import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FPL Tool",
  description: "Local-first Fantasy Premier League decision support"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
