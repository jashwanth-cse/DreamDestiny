import React from "react";

interface SectionHeadingProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  align?: "left" | "center";
  className?: string;
}

export function SectionHeading({
  eyebrow,
  title,
  subtitle,
  align = "center",
  className = "",
}: SectionHeadingProps) {
  const alignmentClass = align === "center" ? "text-center mx-auto" : "text-left";

  return (
    <div className={`max-w-2xl ${alignmentClass} ${className} mb-12 lg:mb-16`}>
      {eyebrow && (
        <span className="inline-block text-[11px] font-bold tracking-[0.08em] text-[#0B2345] uppercase bg-[#E8F1EF] px-3.5 py-1 rounded-full mb-3">
          {eyebrow}
        </span>
      )}
      <h2 className="text-3xl sm:text-4xl lg:text-[40px] font-extrabold text-[#0D0F10] tracking-[-0.025em] leading-[1.18] mb-4">
        {title}
      </h2>
      {subtitle && (
        <p className="text-base sm:text-lg text-[#5E6060] leading-relaxed">
          {subtitle}
        </p>
      )}
    </div>
  );
}
