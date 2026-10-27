"use client";

import React, { useState } from "react";
import { MessageCircle, ArrowRight, Train, Bus, Plane, Hotel, Compass, CheckCircle2, Sparkles } from "lucide-react";
import { Button } from "../ui/Button";
import { getWhatsAppLink } from "../../lib/whatsapp";
import { WhatsAppNoticeModal } from "../ui/WhatsAppNoticeModal";

const featureChips = [
  { label: "Trains", icon: Train },
  { label: "Buses", icon: Bus },
  { label: "Flights", icon: Plane },
  { label: "Hotels", icon: Hotel },
  { label: "Places to Explore", icon: Compass },
];

export function HeroSection() {
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
        id="overview"
        aria-labelledby="hero-heading"
        className="relative pt-8 pb-16 sm:pt-12 sm:pb-24 lg:pt-16 lg:pb-28 overflow-hidden"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-8 items-center">
            {/* Left Column (7 cols): Copy & CTAs */}
            <div className="lg:col-span-7 flex flex-col items-start text-left">
              {/* Eyebrow badge */}
              <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#E8F1EF] border border-[#B9CCCA]/40 mb-6 shadow-sm">
                <span className="w-2 h-2 rounded-full bg-[#79B66A] animate-pulse" />
                <span className="text-[11px] font-bold tracking-[0.08em] text-[#0B2345] uppercase">
                  YOUR TRAVEL COMPANION
                </span>
              </div>

              {/* H1 Headline */}
              <h1
                id="hero-heading"
                className="text-4xl sm:text-5xl lg:text-[56px] font-extrabold text-[#0D0F10] tracking-[-0.03em] leading-[1.1] mb-6"
              >
                Create Personalized Trip Plans in Seconds with AI
              </h1>

              {/* Supporting Copy */}
              <p className="text-base sm:text-lg lg:text-xl text-[#5E6060] leading-relaxed mb-8 max-w-xl">
                Plan your next journey right inside WhatsApp. Dream Destiny brings transport options, stays, places to explore, and an AI-generated itinerary together in a familiar chat.
              </p>

              {/* CTAs */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3.5 w-full sm:w-auto mb-6">
                <Button
                  variant="whatsapp"
                  size="lg"
                  href={waLink.url}
                  external={waLink.isConfigured}
                  onClick={handleWhatsAppClick}
                  icon={<MessageCircle className="w-5 h-5 fill-white/20" />}
                  className="shadow-md"
                >
                  Chat with Dream Destiny
                </Button>
                <Button
                  variant="secondary"
                  size="lg"
                  href="#how-it-works"
                  icon={<ArrowRight className="w-4 h-4 text-[#0B2345]" />}
                >
                  See How It Works
                </Button>
              </div>

              {/* Prominent Trust Microcopy Banner */}
              <div className="flex items-center gap-2.5 p-3 px-4 rounded-2xl bg-white border border-[rgba(13,15,16,0.08)] shadow-[0_2px_8px_rgba(13,15,16,0.03)] mb-8">
                <CheckCircle2 className="w-4 h-4 text-[#79B66A] shrink-0" />
                <p className="text-xs sm:text-sm font-bold text-[#0D0F10] tracking-tight">
                  No installation. No separate signup. Just WhatsApp.
                </p>
              </div>

              {/* Transit Chips */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold text-[#5E6060] mr-1">
                  Discover:
                </span>
                {featureChips.map((chip) => {
                  const Icon = chip.icon;
                  return (
                    <span
                      key={chip.label}
                      className="inline-flex items-center gap-1.5 text-xs font-medium text-[#0D0F10] bg-white px-3 py-1.5 rounded-full border border-[rgba(13,15,16,0.08)] shadow-sm"
                    >
                      <Icon className="w-3.5 h-3.5 text-[#0B2345]" />
                      <span>{chip.label}</span>
                    </span>
                  );
                })}
              </div>
            </div>

            {/* Right Column (5 cols): WhatsApp Chat Mockup */}
            <div className="lg:col-span-5 flex justify-center lg:justify-end">
              <div className="relative w-full max-w-[380px] rounded-[36px] bg-[#0D0F10] p-3 shadow-[0_24px_50px_-12px_rgba(13,15,16,0.25)] border-4 border-[#D1DEDC]">
                {/* Phone screen bezel */}
                <div className="relative rounded-[28px] overflow-hidden bg-[#EFEAE2] flex flex-col h-[580px]">
                  {/* Speaker Notch */}
                  <div className="absolute top-0 left-1/2 -translate-x-1/2 w-32 h-4 bg-[#0D0F10] rounded-b-xl z-20" />

                  {/* WhatsApp Chat Header */}
                  <div className="bg-[#0B2345] px-4 pt-6 pb-3 text-white flex items-center gap-3 z-10 shrink-0">
                    <div className="w-9 h-9 rounded-full bg-[#123B66] flex items-center justify-center font-bold text-xs">
                      DD
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-bold truncate">
                          Dream Destiny
                        </span>
                        <span className="w-3.5 h-3.5 rounded-full bg-[#79B66A] text-[9px] flex items-center justify-center font-bold text-white">
                          ✓
                        </span>
                      </div>
                      <p className="text-[10px] text-[#B9CCCA] truncate">
                        Online • Replies in seconds
                      </p>
                    </div>
                  </div>

                  {/* Chat Bubbles Scroll Area */}
                  <div className="p-3.5 space-y-3 flex-1 overflow-y-auto text-xs">
                    {/* Bot Message 1 */}
                    <div className="max-w-[85%] bg-white p-3 rounded-2xl rounded-tl-sm shadow-sm border border-[rgba(13,15,16,0.05)]">
                      <div className="flex items-center gap-1 text-[10px] font-bold text-[#0B2345] mb-1">
                        <Sparkles className="w-3 h-3 text-[#79B66A]" />
                        <span>Dream Destiny Assistant</span>
                      </div>
                      <p className="text-[#0D0F10] leading-relaxed">
                        Where would you like to travel? Share your origin, destination, and pace!
                      </p>
                      <span className="text-[9px] text-[#5E6060] float-right mt-1">10:02 AM</span>
                    </div>

                    {/* User Message */}
                    <div className="max-w-[85%] ml-auto bg-[#D9FDD3] p-3 rounded-2xl rounded-tr-sm shadow-sm text-[#0D0F10]">
                      <p className="leading-relaxed">
                        Planning a 3-day weekend from Mumbai to Udaipur with my partner. Want scenic spots, lakes, and good food.
                      </p>
                      <span className="text-[9px] text-[#5E6060] float-right mt-1">10:03 AM ✓✓</span>
                    </div>

                    {/* Bot Itinerary Card Preview */}
                    <div className="max-w-[95%] bg-white p-3.5 rounded-2xl rounded-tl-sm shadow-md border border-[#B9CCCA]/60 space-y-2">
                      <div className="flex items-center justify-between pb-1.5 border-b border-gray-100">
                        <span className="font-extrabold text-[#0B2345] text-xs">
                          3-Day Udaipur Blueprint
                        </span>
                        <span className="text-[9px] font-bold bg-[#E8F1EF] text-[#27521D] px-2 py-0.5 rounded-full">
                          AI Curated
                        </span>
                      </div>

                      {/* Transport summary */}
                      <div className="p-2 rounded-xl bg-[#F6FAFA] text-[11px] space-y-1">
                        <div className="flex items-center gap-1 font-semibold text-[#0D0F10]">
                          <Train className="w-3 h-3 text-[#E42529]" />
                          <span>BDTS UDZ SF EXP (Overnight Rail)</span>
                        </div>
                        <p className="text-[10px] text-[#5E6060]">
                          Direct overnight link from Bandra Terminus.
                        </p>
                      </div>

                      {/* Day summary */}
                      <div className="text-[11px] text-[#0D0F10] space-y-1 pt-1">
                        <p><strong>Day 1:</strong> Lake Pichola boat ride & Ambrai dinner</p>
                        <p><strong>Day 2:</strong> City Palace & Bagore Ki Haveli show</p>
                        <p><strong>Day 3:</strong> Sajjangarh Monsoon Palace & bazars</p>
                      </div>

                      {/* Action buttons inside chat */}
                      <div className="pt-2 flex gap-1.5">
                        <span className="flex-1 text-center py-1 rounded-lg bg-[#E8F1EF] text-[#0B2345] font-bold text-[10px]">
                          🏨 View Stays
                        </span>
                        <span className="flex-1 text-center py-1 rounded-lg bg-[#79B66A] text-white font-bold text-[10px]">
                          🗺️ View Map
                        </span>
                      </div>
                      <span className="text-[9px] text-[#5E6060] float-right">10:04 AM</span>
                    </div>
                  </div>

                  {/* Chat Input Placeholder Bar */}
                  <div className="bg-white p-2.5 px-3 border-t border-[rgba(13,15,16,0.06)] flex items-center gap-2">
                    <div className="flex-1 bg-[#F0F2F5] px-3 py-1.5 rounded-full text-xs text-[#5E6060]">
                      Type a travel preference...
                    </div>
                    <div className="w-7 h-7 rounded-full bg-[#79B66A] flex items-center justify-center text-white text-xs">
                      ➤
                    </div>
                  </div>
                </div>

                {/* Replaceable asset label */}
                <div className="absolute -bottom-3 left-1/2 -translate-x-1/2 bg-[#0B2345] text-white text-[9px] font-semibold px-3 py-1 rounded-full shadow-md whitespace-nowrap">
                  Interactive WhatsApp Bot Mockup • Replaceable
                </div>
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
