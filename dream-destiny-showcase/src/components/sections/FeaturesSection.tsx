import React from "react";
import { SectionHeading } from "../ui/SectionHeading";
import { featuresData } from "../../data/features";
import { Sparkles, Route, Hotel, Compass, MessageCircle, MapPin, ShieldAlert } from "lucide-react";

const iconMap = {
  sparkles: Sparkles,
  route: Route,
  hotel: Hotel,
  compass: Compass,
  "message-circle": MessageCircle,
  "map-pin": MapPin,
};

export function FeaturesSection() {
  return (
    <section
      id="features"
      aria-labelledby="features-heading"
      className="py-16 sm:py-24 bg-white"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="CAPABILITIES"
          title="Everything You Need for Smarter Travel"
          subtitle="Dream Destiny brings multiple specialized travel intelligence sources into one unified WhatsApp experience."
        />

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8">
          {featuresData.map((feature) => {
            const Icon = iconMap[feature.icon as keyof typeof iconMap] || Sparkles;

            return (
              <article
                key={feature.id}
                className="flex flex-col bg-[#F6FAFA] rounded-3xl p-6 sm:p-8 border border-[rgba(13,15,16,0.06)] hover:border-[#B9CCCA] hover:bg-white hover:shadow-[0_12px_36px_rgba(13,15,16,0.06)] transition-all duration-300"
              >
                {/* Icon Pill */}
                <div className="w-12 h-12 rounded-2xl bg-white flex items-center justify-center border border-[rgba(13,15,16,0.06)] shadow-sm mb-6 shrink-0">
                  <Icon className="w-6 h-6 text-[#0B2345]" aria-hidden="true" />
                </div>

                {/* Subtitle / Tagline */}
                <span className="text-[11px] font-bold tracking-wider text-[#79B66A] uppercase mb-1">
                  {feature.tagline}
                </span>

                {/* Title */}
                <h3 className="text-xl font-bold text-[#0D0F10] tracking-[-0.015em] mb-3">
                  {feature.title}
                </h3>

                {/* Description */}
                <p className="text-sm text-[#5E6060] leading-relaxed mb-6">
                  {feature.description}
                </p>

                {/* Disclaimer Footnote */}
                {feature.disclaimer && (
                  <div className="mt-auto pt-4 border-t border-[rgba(13,15,16,0.06)] flex items-start gap-1.5 text-[11px] text-[#5E6060]/75">
                    <ShieldAlert className="w-3.5 h-3.5 text-[#0B2345]/50 shrink-0 mt-0.5" aria-hidden="true" />
                    <span>{feature.disclaimer}</span>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
