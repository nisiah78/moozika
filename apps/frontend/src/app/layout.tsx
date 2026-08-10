import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "moozika",
  description: "Conversion de partitions sol-fa tonique ⇄ portée",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="min-h-screen bg-[#f3efe8] text-stone-900 antialiased">{children}</body>
    </html>
  );
}
