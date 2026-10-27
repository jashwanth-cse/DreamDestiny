import React from "react";
import { PublicReview } from "../../types/review";
import { Star, CheckCircle, Quote } from "lucide-react";

interface TestimonialCardProps {
  review: PublicReview;
}

export function TestimonialCard({ review }: TestimonialCardProps) {
  return (
    <article className="flex flex-col bg-white rounded-3xl p-6 border border-[rgba(13,15,16,0.08)] shadow-[0_4px_20px_-2px_rgba(13,15,16,0.04)] hover:shadow-[0_12px_36px_rgba(13,15,16,0.07)] transition-all duration-300">
      {/* Top Header: Rating & Destination */}
      <div className="flex items-center justify-between gap-2 mb-4">
        {review.rating ? (
          <div className="flex items-center gap-1" aria-label={`Rating: ${review.rating} out of 5 stars`}>
            {Array.from({ length: 5 }).map((_, index) => (
              <Star
                key={index}
                className={`w-4 h-4 ${
                  index < (review.rating || 0)
                    ? "fill-[#FBBC05] text-[#FBBC05]"
                    : "fill-gray-200 text-gray-200"
                }`}
                aria-hidden="true"
              />
            ))}
          </div>
        ) : (
          <div className="w-4 h-4" />
        )}

        {review.tripOrDestination && (
          <span className="text-[10px] font-bold text-[#0B2345] bg-[#E8F1EF] px-2.5 py-0.5 rounded-full uppercase tracking-wider">
            {review.tripOrDestination}
          </span>
        )}
      </div>

      {/* Review Text */}
      <div className="relative mb-6 flex-1">
        <Quote className="w-5 h-5 text-[#B9CCCA] opacity-40 mb-2" aria-hidden="true" />
        <p className="text-sm text-[#0D0F10] leading-relaxed italic">
          &ldquo;{review.reviewText}&rdquo;
        </p>
      </div>

      {/* Reviewer Meta */}
      <div className="flex items-center gap-2.5 pt-4 border-t border-[rgba(13,15,16,0.06)] mt-auto">
        <div className="w-8 h-8 rounded-full bg-[#E8F1EF] text-[#0B2345] font-bold text-xs flex items-center justify-center shrink-0">
          {review.displayName.charAt(0).toUpperCase()}
        </div>
        <div className="flex flex-col">
          <span className="text-xs font-bold text-[#0D0F10]">
            {review.displayName}
          </span>
          <span className="inline-flex items-center gap-1 text-[10px] text-[#79B66A] font-medium">
            <CheckCircle className="w-3 h-3" aria-hidden="true" />
            Verified WhatsApp Traveler
          </span>
        </div>
      </div>
    </article>
  );
}
