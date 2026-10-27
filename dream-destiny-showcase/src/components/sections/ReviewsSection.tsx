"use client";

import React, { useEffect, useState } from "react";
import { SectionHeading } from "../ui/SectionHeading";
import { TestimonialCard } from "../ui/TestimonialCard";
import { fetchPublicReviews } from "../../lib/reviews";
import { isFirebaseConfigured } from "../../lib/firebase";
import { PublicReview } from "../../types/review";
import { MessageSquare, ShieldCheck, RefreshCw } from "lucide-react";

export function ReviewsSection() {
  const [reviews, setReviews] = useState<PublicReview[]>([]);
  const [status, setStatus] = useState<"loading" | "configured" | "unconfigured" | "error">("loading");

  useEffect(() => {
    let isMounted = true;

    async function loadReviews() {
      if (!isFirebaseConfigured) {
        if (isMounted) setStatus("unconfigured");
        return;
      }

      try {
        const result = await fetchPublicReviews(6);
        if (isMounted) {
          setStatus(result.status);
          setReviews(result.reviews);
        }
      } catch {
        if (isMounted) {
          setStatus("error");
        }
      }
    }

    loadReviews();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <section
      id="reviews"
      aria-labelledby="reviews-heading"
      className="py-16 sm:py-24 bg-[#F2F6F6]"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="COMMUNITY VOICE"
          title="What Travelers Say About Planning on WhatsApp"
          subtitle="Real reviews from verified WhatsApp users. Only publicly approved, authentic experiences are displayed."
        />

        {/* Loading State */}
        {status === "loading" && (
          <div className="flex flex-col items-center justify-center p-12 bg-white rounded-3xl border border-[rgba(13,15,16,0.08)] text-center max-w-md mx-auto">
            <RefreshCw className="w-6 h-6 text-[#79B66A] animate-spin mb-3" />
            <p className="text-sm font-semibold text-[#0D0F10]">Checking verified reviews...</p>
            <p className="text-xs text-[#5E6060]">Connecting to public testimonial records</p>
          </div>
        )}

        {/* Active Reviews Loaded */}
        {status === "configured" && reviews.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8">
            {reviews.map((rev) => (
              <TestimonialCard key={rev.id} review={rev} />
            ))}
          </div>
        )}

        {/* Empty State when Configured but 0 reviews published yet */}
        {status === "configured" && reviews.length === 0 && (
          <div className="bg-white rounded-3xl p-8 sm:p-12 text-center max-w-xl mx-auto border border-[rgba(13,15,16,0.08)] shadow-[0_4px_20px_-2px_rgba(13,15,16,0.04)]">
            <div className="w-12 h-12 rounded-2xl bg-[#E8F1EF] text-[#0B2345] flex items-center justify-center mx-auto mb-4">
              <MessageSquare className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-[#0D0F10] mb-2">
              Reviews Coming Soon
            </h3>
            <p className="text-sm text-[#5E6060] leading-relaxed mb-4">
              Our travelers are actively exploring India with Dream Destiny. Verified customer reviews will appear here following standard moderation.
            </p>
            <p className="text-xs font-semibold text-[#0B2345]">
              No fabricated reviews are ever published.
            </p>
          </div>
        )}

        {/* Unconfigured / Fallback State (e.g. before Firebase variables are connected) */}
        {status === "unconfigured" && (
          <div className="bg-white rounded-3xl p-8 sm:p-12 text-center max-w-2xl mx-auto border border-[rgba(13,15,16,0.08)] shadow-[0_4px_20px_-2px_rgba(13,15,16,0.04)]">
            <div className="w-12 h-12 rounded-2xl bg-[#E8F1EF] text-[#79B66A] flex items-center justify-center mx-auto mb-4">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <h3 className="text-lg sm:text-xl font-bold text-[#0D0F10] mb-2">
              Verified User Reviews Integration
            </h3>
            <p className="text-sm text-[#5E6060] leading-relaxed mb-6 max-w-md mx-auto">
              Dream Destiny displays user feedback via a client-side Firestore connection. In accordance with data integrity guidelines, placeholder or fabricated reviews are not shown.
            </p>
            <div className="p-4 bg-[#F6FAFA] rounded-2xl text-left border border-[rgba(13,15,16,0.06)] max-w-lg mx-auto text-xs text-[#5E6060] space-y-2">
              <p className="font-bold text-[#0B2345]">To enable live community reviews:</p>
              <p>Configure public Firebase keys in your showcase environment variables:</p>
              <code className="block bg-white p-2 rounded border border-[rgba(13,15,16,0.08)] font-mono text-[11px] text-[#0D0F10]">
                NEXT_PUBLIC_FIREBASE_API_KEY=...<br />
                NEXT_PUBLIC_FIREBASE_PROJECT_ID=...
              </code>
              <p className="text-[11px] text-[#5E6060]">
                Requires a read-only <span className="font-mono text-[#0B2345]">public_reviews</span> Firestore collection with <span className="font-mono text-[#0B2345]">published: true</span>.
              </p>
            </div>
          </div>
        )}

        {/* Error State */}
        {status === "error" && (
          <div className="bg-white rounded-3xl p-8 text-center max-w-md mx-auto border border-[rgba(13,15,16,0.08)]">
            <p className="text-sm text-[#5E6060]">
              Could not load reviews at this time. Please check your network or Firestore rules.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
