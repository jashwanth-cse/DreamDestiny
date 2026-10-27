import React from "react";
import Image from "next/image";
import { providerLegalDisclaimer } from "../../data/providers";

const footerLinks = [
  { href: "#overview", label: "Overview" },
  { href: "#how-it-works", label: "How It Works" },
  { href: "#features", label: "Features" },
  { href: "#powered-by", label: "Powered By" },
  { href: "#journeys", label: "Journeys" },
  { href: "#reviews", label: "Our Users" },
];

export function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="bg-white border-t border-[rgba(13,15,16,0.08)] pt-16 pb-12 mt-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-10 pb-12 border-b border-[rgba(13,15,16,0.06)]">
          {/* Brand Column */}
          <div className="md:col-span-2 space-y-4">
            <div className="flex items-center gap-3">
              <div className="relative w-9 h-9 rounded-full flex items-center justify-center overflow-hidden shrink-0 border border-[rgba(11,35,69,0.08)] shadow-sm">
                <Image
                  src="/brand/dream-destiny-logo.png"
                  alt="Dream Destiny logo mark"
                  width={36}
                  height={36}
                  className="w-full h-full object-cover"
                />
              </div>
              <span className="text-xl font-extrabold text-[#0D0F10] tracking-tight">
                Dream Destiny
              </span>
            </div>
            <p className="text-sm text-[#5E6060] max-w-md leading-relaxed">
              Your AI travel companion on WhatsApp. Plan personalized trips, discover train and bus routes, compare flight options, and find verified stays—all through a single message.
            </p>
            <div className="inline-block bg-[#F2F6F6] text-[#0B2345] text-xs font-semibold px-3 py-1.5 rounded-full border border-[rgba(13,15,16,0.06)]">
              No installation. No separate signup. Just WhatsApp.
            </div>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-[#0D0F10] mb-4">
              Explore Showcase
            </h4>
            <ul className="space-y-2.5">
              {footerLinks.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    className="text-sm text-[#5E6060] hover:text-[#0D0F10] transition-colors"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {/* Product & Legal Context */}
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-[#0D0F10] mb-4">
              Product Integrity
            </h4>
            <ul className="space-y-2.5 text-xs text-[#5E6060] leading-relaxed">
              <li>• WhatsApp-first conversational interface</li>
              <li>• Official provider API integrations</li>
              <li>• Verified data & schedules</li>
              <li className="pt-2 text-[11px] text-[#5E6060]/70">
                Privacy policy and terms of service will be published upon commercial rollout.
              </li>
            </ul>
          </div>
        </div>

        {/* Legal & Trademark Notices */}
        <div className="pt-8 space-y-4">
          <p className="text-xs text-[#5E6060] leading-relaxed">
            {providerLegalDisclaimer}
          </p>
          <p className="text-[11px] text-[#5E6060]/80 leading-relaxed">
            Google Maps, Google Flights, and Google Hotels are trademarks of Google LLC. When mapping interfaces are displayed, Google Maps attribution is preserved per Google Maps Platform terms. Amazon Bedrock and AWS are trademarks of Amazon.com, Inc. or its affiliates. ixigo is a registered trademark of Le Travenues Technology Ltd. redBus is a trademark of ibibo Group / MakeMyTrip.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-[rgba(13,15,16,0.06)] text-xs text-[#5E6060]">
            <p>© {currentYear} Dream Destiny. All rights reserved.</p>
            <p className="text-[11px]">
              Built with Next.js static export. Fully client-side delivery.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
