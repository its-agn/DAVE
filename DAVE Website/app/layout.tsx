import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "D.A.V.E Assistant",
  description: "A stylish chat UI for the D.A.V.E assistant",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
