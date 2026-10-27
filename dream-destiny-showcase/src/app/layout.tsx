import type { Metadata, Viewport } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import { Navbar } from "../components/layout/Navbar";
import { Footer } from "../components/layout/Footer";

const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-jakarta",
  display: "swap",
});

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://dreamdestiny.ai";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "Dream Destiny | Your AI Travel Companion on WhatsApp",
  description:
    "Plan personalized journeys with Dream Destiny on WhatsApp. Discover travel options, stays, and places to explore—without installing another app or creating a separate account.",
  keywords: [
    "WhatsApp travel planner",
    "AI trip itinerary",
    "travel companion",
    "train discovery",
    "bus routes",
    "flight fare discovery",
    "hotel recommendations",
    "India travel planning",
  ],
  authors: [{ name: "Dream Destiny Team" }],
  openGraph: {
    title: "Dream Destiny | Your AI Travel Companion on WhatsApp",
    description:
      "Plan personalized journeys with Dream Destiny on WhatsApp. Discover travel options, stays, and places to explore—without installing another app or creating a separate account.",
    url: siteUrl,
    siteName: "Dream Destiny",
    images: [
      {
        url: "/og-image.svg",
        width: 1200,
        height: 630,
        alt: "Dream Destiny AI Travel Companion on WhatsApp",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Dream Destiny | Your AI Travel Companion on WhatsApp",
    description:
      "Plan personalized journeys with Dream Destiny on WhatsApp. No installation. No separate signup.",
    images: ["/og-image.svg"],
  },
  icons: {
    icon: "/brand/dream-destiny-logo.png",
    shortcut: "/brand/dream-destiny-logo.png",
    apple: "/brand/dream-destiny-logo.png",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export const viewport: Viewport = {
  themeColor: "#F2F6F6",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${siteUrl}/#organization`,
        name: "Dream Destiny",
        url: siteUrl,
        logo: `${siteUrl}/brand/dream-destiny-logo.png`,
        description: "AI-assisted travel planning bot operating directly on WhatsApp.",
      },
      {
        "@type": "SoftwareApplication",
        "@id": `${siteUrl}/#application`,
        name: "Dream Destiny WhatsApp Travel Bot",
        applicationCategory: "TravelApplication",
        operatingSystem: "WhatsApp",
        offers: {
          "@type": "Offer",
          price: "0",
          priceCurrency: "INR",
        },
        description:
          "AI-driven conversational itinerary and multi-modal travel discovery assistant on WhatsApp.",
      },
    ],
  };

  return (
    <html lang="en" className={`${plusJakartaSans.variable} scroll-smooth`}>
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body className="min-h-screen flex flex-col bg-[#F2F6F6] text-[#0D0F10] selection:bg-[#B7D7AD] selection:text-[#0D0F10]">
        {/* Skip to Content for Keyboard Accessibility */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-[#0B2345] focus:text-white focus:rounded-full focus:shadow-lg focus:outline-none"
        >
          Skip to main content
        </a>

        <Navbar />
        {children}
        <Footer />
      </body>
    </html>
  );
}
