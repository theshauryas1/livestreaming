import type { Metadata } from "next";
import "./globals.css";

const siteTitle = process.env.NEXT_PUBLIC_SITE_TITLE ?? "Pi Live Stream";

export const metadata: Metadata = {
  title: siteTitle,
  description: "Live streaming from Raspberry Pi Camera Module 3",
  keywords: ["raspberry pi", "live stream", "camera", "mjpeg"],
  openGraph: {
    title: siteTitle,
    description: "Live streaming from Raspberry Pi Camera Module 3",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
