"use client";

import React, { useState } from "react";
import { MessageCircle, CheckCircle2, Sparkles } from "lucide-react";
import { Button } from "../ui/Button";
import { getWhatsAppLink } from "../../lib/whatsapp";
import { WhatsAppNoticeModal } from "../ui/WhatsAppNoticeModal";

export function FinalCtaSection() {
  const [isNoticeOpen, setIsNoticeOpen] = useState(false);
  const waLink = getWhatsAppLink();

  const handleWhatsAppClick = (e: React.MouseEvent) => {
    if (!waLink.isConfigured) {
      e.preventDefault();
      setIsNoticeOpen(true);
    }
  };

  return (
    <>
      <section
        id="final-cta"
        aria-labelledby="cta-heading"
        className="py-20 sm:py-28 bg-white relative overflow-hidden"
      >
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="relative rounded-[36px] bg-[#0B2345] text-white p-8 sm:p-12 lg:p-16 text-center overflow-hidden shadow-2xl">
            {/* Background subtle light accents */}
            <div className="absolute -top-24 -left-24 w-80 h-80 rounded-full bg-[#123B66] blur-3xl opacity-50 pointer-events-none" />
            <div className="absolute -bottom-24 -right-24 w-80 h-80 rounded-full bg-[#79B66A] blur-3xl opacity-20 pointer-events-none" />

            <div className="relative z-10 max-w-2xl mx-auto space-y-6">
              {/* Badge */}
              <div className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-white/10 backdrop-blur-sm border border-white/15 text-xs font-semibold text-[#B7D7AD]">
                <Sparkles className="w-3.5 h-3.5 text-[#79B66A]" />
                <span>Instant Travel Concierge</span>
              </div>

              {/* Headline */}
              <h2
                id="cta-heading"
                className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-[-0.025em] text-white leading-tight"
              >
                Your next journey starts with a message.
              </h2>

              {/* Supporting Text */}
              <p className="text-base sm:text-lg text-[#B9CCCA] leading-relaxed max-w-lg mx-auto">
                Open WhatsApp and start planning with Dream Destiny. Discover transport routes, verified stays, and day-by-day itineraries tailored to you.
              </p>

              {/* Action Button */}
              <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-4">
                <Button
                  variant="whatsapp"
                  size="lg"
                  href={waLink.url}
                  external={waLink.isConfigured}
                  onClick={handleWhatsAppClick}
                  icon={<MessageCircle className="w-5 h-5 fill-white/20" />}
                  className="shadow-xl px-8"
                >
                  Chat on WhatsApp
                </Button>
              </div>

              {/* Reinforcing microcopy */}
              <div className="pt-4 flex items-center justify-center gap-2 text-xs font-medium text-[#B7D7AD]">
                <CheckCircle2 className="w-4 h-4 text-[#79B66A]" />
                <span>No installation. No separate signup. Just WhatsApp.</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <WhatsAppNoticeModal
        isOpen={isNoticeOpen}
        onClose={() => setIsNoticeOpen(false)}
        isConfigured={waLink.isConfigured}
        phoneNumber={waLink.phoneNumber}
        url={waLink.url}
      />
    </>
  );
}
