import React from "react";
import { SectionHeading } from "../ui/SectionHeading";
import { JourneyCard } from "../ui/JourneyCard";
import { sampleJourneys } from "../../data/journeys";
import { MessageCircle } from "lucide-react";

export function JourneysSection() {
  return (
    <section
      id="journeys"
      aria-labelledby="journeys-heading"
      className="py-16 sm:py-24 bg-white"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="INSPIRATION & BLUEPRINTS"
          title="Sample Journeys You Can Plan in WhatsApp"
          subtitle="Discover representative travel plans generated through Dream Destiny's conversational AI assistant. Message the bot to craft your own itinerary."
        />

        {/* 4 Destination Cards Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 sm:gap-8 mb-12">
          {sampleJourneys.map((journey) => (
            <JourneyCard key={journey.id} journey={journey} />
          ))}
        </div>

        {/* Callout box reinforcing WhatsApp execution */}
        <div className="rounded-3xl bg-[#F6FAFA] p-6 sm:p-8 border border-[rgba(13,15,16,0.06)] flex flex-col sm:flex-row items-center justify-between gap-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-2xl bg-[#E8F1EF] text-[#79B66A] flex items-center justify-center shrink-0">
              <MessageCircle className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-base font-bold text-[#0D0F10]">
                Want a personalized route for any other destination?
              </h4>
              <p className="text-xs sm:text-sm text-[#5E6060] mt-0.5 max-w-xl">
                Just open WhatsApp and message Dream Destiny. Mention where you want to start, your preferred travel dates, and what kind of trip you love.
              </p>
            </div>
          </div>
          <a
            href="#overview"
            className="text-xs font-bold text-[#0B2345] hover:text-[#79B66A] transition-colors whitespace-nowrap bg-white px-5 py-2.5 rounded-full border border-[rgba(13,15,16,0.08)] shadow-sm"
          >
            Start WhatsApp Chat →
          </a>
        </div>
      </div>
    </section>
  );
}
