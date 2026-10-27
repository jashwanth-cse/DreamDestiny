import React from "react";
import Image from "next/image";

interface ScreenshotPlaceholderProps {
  src: string;
  alt: string;
  stepNumber: number;
  title: string;
  description: string;
  badgeLabel?: string;
}

export function ScreenshotPlaceholder({
  src,
  alt,
  stepNumber,
  title,
  description,
  badgeLabel = "Live WhatsApp Flow",
}: ScreenshotPlaceholderProps) {
  return (
    <article className="flex flex-col bg-white rounded-3xl p-5 sm:p-6 border border-[rgba(13,15,16,0.08)] shadow-[0_4px_20px_-2px_rgba(13,15,16,0.04)] hover:shadow-[0_12px_36px_rgba(13,15,16,0.08)] transition-all duration-300">
      {/* Device Bezel container */}
      <div className="relative aspect-[1312/1199] w-full rounded-2xl overflow-hidden bg-[#F0F4F4] border border-[rgba(13,15,16,0.06)] flex items-center justify-center mb-6">
        <Image
          src={src}
          alt={alt}
          width={1312}
          height={1199}
          className="w-full h-full object-contain"
          loading="lazy"
        />
        {/* Placeholder tag pill */}
        <div className="absolute top-3 left-3 right-3 flex justify-between items-center pointer-events-none">
          <span className="text-[10px] font-bold text-[#0D0F10] bg-white/90 backdrop-blur-sm px-2.5 py-1 rounded-full border border-[rgba(13,15,16,0.08)] shadow-sm">
            Step 0{stepNumber}
          </span>
          <span className="text-[9px] font-semibold text-[#5E6060] bg-white/90 backdrop-blur-sm px-2 py-0.5 rounded-full border border-[rgba(13,15,16,0.08)]">
            {badgeLabel}
          </span>
        </div>
      </div>

      {/* Step description */}
      <div className="flex items-start gap-3.5 mt-auto">
        <div className="w-8 h-8 rounded-full bg-[#0B2345] text-white flex items-center justify-center font-bold text-sm shrink-0">
          {stepNumber}
        </div>
        <div>
          <h3 className="text-lg font-bold text-[#0D0F10] tracking-[-0.01em] mb-1">
            {title}
          </h3>
          <p className="text-sm text-[#5E6060] leading-relaxed">
            {description}
          </p>
        </div>
      </div>
    </article>
  );
}
