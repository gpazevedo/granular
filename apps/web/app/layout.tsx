import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Granular — Course Discovery",
  description: "Find Purdue CS courses by describing what you want to learn.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
