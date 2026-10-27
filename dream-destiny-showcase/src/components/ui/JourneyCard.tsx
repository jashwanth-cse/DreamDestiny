"use client";

import React, { useState } from "react";
import Image from "next/image";
import { Journey } from "../../types/journey";
import { MapPin, Clock, Users, X, MessageCircle } from "lucide-react";
import { Button } from "./Button";

interface JourneyCardProps {
  journey: Journey;
  onSelect?: (journey: Journey) => void;
}

export function JourneyCard({ journey }: JourneyCardProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  return (
    <>
      <article className="flex flex-col bg-white rounded-3xl p-4 border border-[rgba(13,15,16,0.08)] shadow-[0_4px_20px_-2px_rgba(13,15,16,0.04)] hover:shadow-[0_12px_36px_rgba(13,15,16,0.09)] transition-all duration-300 group">
        {/* Destination Image Container */}
        <div className="relative aspect-[16/10] w-full rounded-2xl overflow-hidden bg-[#F0F4F4] mb-4">
          <Image
            src={journey.image}
            alt={journey.imageAlt}
            fill
            sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
            className="object-cover group-hover:scale-[1.02] transition-transform duration-500"
            loading="lazy"
          />
          {/* Top Duration badge */}
          <div className="absolute top-3 right-3">
            <span className="text-[11px] font-bold text-[#0D0F10] bg-white/95 backdrop-blur-sm px-3 py-1 rounded-full border border-[rgba(13,15,16,0.08)] shadow-sm">
              {journey.duration}
            </span>
          </div>
          {/* Factual Sample Tag */}
          <div className="absolute bottom-3 left-3">
            <span className="text-[10px] font-semibold text-white bg-[#0B2345]/85 backdrop-blur-sm px-2.5 py-1 rounded-full">
              Sample Itinerary
            </span>
          </div>
        </div>

        {/* Content */}
        <div className="flex flex-col flex-1 px-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-[#5E6060] mb-1">
            <MapPin className="w-3.5 h-3.5 text-[#79B66A] shrink-0" aria-hidden="true" />
            <span>
              {journey.destination}, {journey.stateOrRegion}
            </span>
          </div>

          <h3 className="text-xl font-bold text-[#0D0F10] tracking-[-0.015em] mb-2 leading-snug">
            {journey.title}
          </h3>

          <p className="text-sm text-[#5E6060] line-clamp-2 leading-relaxed mb-4">
            {journey.description}
          </p>

          {/* Tags */}
          <div className="flex flex-wrap gap-1.5 mb-5 mt-auto">
            {journey.tags.map((tag) => (
              <span
                key={tag}
                className="text-[11px] font-medium text-[#0B2345] bg-[#E8F1EF] px-2.5 py-0.5 rounded-full"
              >
                {tag}
              </span>
            ))}
          </div>

          {/* Action Trigger */}
          <div className="pt-3 border-t border-[rgba(13,15,16,0.06)] flex items-center justify-between">
            <button
              type="button"
              onClick={() => setIsModalOpen(true)}
              className="text-xs font-bold text-[#0D0F10] hover:text-[#79B66A] transition-colors flex items-center gap-1 group/btn focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B2345] rounded-md px-1 py-1"
            >
              <span>Explore sample blueprint</span>
              <span className="group-hover/btn:translate-x-0.5 transition-transform" aria-hidden="true">
                →
              </span>
            </button>
            <span className="text-[10px] text-[#5E6060]/70 font-mono">
              Plan in WhatsApp
            </span>
          </div>
        </div>
      </article>

      {/* Lightweight Accessible Modal for Journey Details */}
      {isModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby={`modal-title-${journey.id}`}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-[#0D0F10]/60 backdrop-blur-sm animate-in fade-in duration-200"
        >
          <div
            className="bg-white rounded-3xl max-w-lg w-full p-6 sm:p-8 border border-[rgba(13,15,16,0.12)] shadow-2xl relative max-h-[90vh] overflow-y-auto"
            tabIndex={-1}
          >
            {/* Close button */}
            <button
              type="button"
              onClick={() => setIsModalOpen(false)}
              className="absolute top-5 right-5 p-2 rounded-full text-[#5E6060] hover:bg-[#F2F6F6] hover:text-[#0D0F10] transition-colors focus-visible:outline-[#0B2345]"
              aria-label="Close dialog"
            >
              <X className="w-5 h-5" />
            </button>

            <span className="inline-block text-[11px] font-bold tracking-wider text-[#0B2345] bg-[#E8F1EF] px-3 py-1 rounded-full uppercase mb-2">
              Sample Journey Blueprint
            </span>

            <h3
              id={`modal-title-${journey.id}`}
              className="text-2xl font-extrabold text-[#0D0F10] tracking-tight mb-1"
            >
              {journey.destination}: {journey.title}
            </h3>

            <div className="flex items-center gap-3 text-xs text-[#5E6060] mb-4">
              <span className="flex items-center gap-1 font-medium">
                <Clock className="w-3.5 h-3.5 text-[#79B66A]" /> {journey.duration}
              </span>
              <span>•</span>
              <span className="flex items-center gap-1 font-medium">
                <Users className="w-3.5 h-3.5 text-[#79B66A]" /> {journey.idealFor}
              </span>
            </div>

            <div className="p-4 bg-[#F2F6F6] rounded-2xl mb-5 text-sm text-[#0D0F10]">
              <h4 className="font-bold text-xs uppercase tracking-wider text-[#0B2345] mb-1.5">
                Representative Daily Schedule
              </h4>
              <p className="leading-relaxed text-[#3B4A54]">
                {journey.sampleItinerarySnippet}
              </p>
            </div>

            <div className="p-4 rounded-2xl bg-[#E8F1EF]/60 border border-[rgba(13,15,16,0.06)] text-xs text-[#5E6060] mb-6">
              <p className="font-semibold text-[#0B2345] mb-1">
                Notice: All planning occurs directly in WhatsApp
              </p>
              <p>
                This website showcases representative plans. To customize dates, transport modes, and hotels for your own journey, message Dream Destiny on WhatsApp.
              </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-3 justify-end">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsModalOpen(false)}
              >
                Close
              </Button>
              <Button
                variant="whatsapp"
                size="sm"
                href="#overview"
                onClick={() => setIsModalOpen(false)}
                icon={<MessageCircle className="w-4 h-4" />}
              >
                Plan this on WhatsApp
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
