import React from "react";
import Image from "next/image";
import { Provider } from "../../types/provider";
import { CheckCircle2, ShieldCheck, ExternalLink } from "lucide-react";

interface ProviderCardProps {
  provider: Provider;
}

export function ProviderCard({ provider }: ProviderCardProps) {
  return (
    <article className="flex flex-col bg-white rounded-3xl p-6 border border-[rgba(13,15,16,0.08)] shadow-[0_4px_20px_-2px_rgba(13,15,16,0.04)] hover:shadow-[0_12px_36px_rgba(13,15,16,0.07)] transition-all duration-300">
      {/* Top Group & Status header */}
      <div className="flex items-center justify-between gap-2 mb-5">
        <span className="text-[11px] font-bold text-[#0B2345] bg-[#E8F1EF] px-3 py-1 rounded-full uppercase tracking-wider">
          {provider.group}
        </span>
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#27521D] bg-[#B7D7AD]/30 px-2.5 py-0.5 rounded-full border border-[#79B66A]/20">
          <CheckCircle2 className="w-3 h-3 text-[#79B66A]" aria-hidden="true" />
          <span>{provider.status}</span>
        </span>
      </div>

      {/* Official Provider Logo Container with clear space */}
      <div className="relative h-14 w-full bg-[#F6FAFA] rounded-2xl flex items-center justify-center p-3 mb-5 border border-[rgba(13,15,16,0.05)]">
        <Image
          src={provider.logoSrc}
          alt={provider.logoAlt}
          width={180}
          height={48}
          className="max-h-10 w-auto object-contain"
          loading="lazy"
        />
      </div>

      {/* Description */}
      <h3 className="text-base font-bold text-[#0D0F10] mb-1.5 flex items-center gap-1.5">
        <span>{provider.name}</span>
        {provider.officialSite && (
          <a
            href={provider.officialSite}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[#5E6060] hover:text-[#0D0F10] transition-colors focus-visible:outline-[#0B2345] rounded"
            aria-label={`Visit official ${provider.name} website`}
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </h3>

      <p className="text-xs sm:text-sm text-[#5E6060] leading-relaxed mb-4">
        {provider.shortDescription}
      </p>

      {/* Attribution & Legal Note */}
      {provider.attributionNote && (
        <div className="mt-auto pt-3 border-t border-[rgba(13,15,16,0.06)] flex items-start gap-1.5 text-[10px] text-[#5E6060]/80">
          <ShieldCheck className="w-3 h-3 text-[#0B2345] shrink-0 mt-0.5" aria-hidden="true" />
          <p className="leading-snug">{provider.attributionNote}</p>
        </div>
      )}
    </article>
  );
}
