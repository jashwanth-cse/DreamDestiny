import React from "react";
import { SectionHeading } from "../ui/SectionHeading";
import { ProviderCard } from "../ui/ProviderCard";
import { providersData, providerLegalDisclaimer } from "../../data/providers";
import { ShieldCheck, Info } from "lucide-react";

export function PoweredBySection() {
  return (
    <section
      id="powered-by"
      aria-labelledby="powered-by-heading"
      className="py-16 sm:py-24 bg-[#F2F6F6]"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="POWERED BY"
          title="Engineered with Trusted Travel Data Providers"
          subtitle="Dream Destiny integrates with established industry providers to power transit schedules, geospatial context, and generative planning."
        />

        {/* Grouped Providers Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8 mb-12">
          {providersData.map((provider) => (
            <ProviderCard key={provider.id} provider={provider} />
          ))}
        </div>

        {/* Attribution & Legal Notice Box */}
        <div className="rounded-3xl bg-white p-6 sm:p-8 border border-[rgba(13,15,16,0.08)] shadow-[0_4px_20px_-2px_rgba(13,15,16,0.04)]">
          <div className="flex items-start gap-3.5 mb-4">
            <div className="w-8 h-8 rounded-full bg-[#E8F1EF] text-[#0B2345] flex items-center justify-center shrink-0">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-[#0D0F10] tracking-tight">
                Brand & Attribution Compliance
              </h4>
              <p className="text-xs text-[#5E6060] mt-0.5">
                Dream Destiny respects provider intellectual property and adheres to platform terms.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs text-[#5E6060] pt-3 border-t border-[rgba(13,15,16,0.06)] leading-relaxed">
            <div className="space-y-1.5">
              <p className="font-semibold text-[#0B2345] flex items-center gap-1.5">
                <Info className="w-3.5 h-3.5 text-[#79B66A]" />
                Google Maps Platform Attribution
              </p>
              <p>
                When map displays or place recommendations are viewed, Google logo and copyright attribution remain visible on the map canvas per Google Maps Platform terms.
              </p>
            </div>

            <div className="space-y-1.5">
              <p className="font-semibold text-[#0B2345] flex items-center gap-1.5">
                <Info className="w-3.5 h-3.5 text-[#79B66A]" />
                AWS & Partner Trademarks
              </p>
              <p>
                Amazon Bedrock uses official AWS architecture assets. {providerLegalDisclaimer}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
