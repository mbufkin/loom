import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Loom",
  description: "District Workspace — paste a Packet, start a Run, read plates.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
