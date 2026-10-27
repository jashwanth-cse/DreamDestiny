import React from "react";
import { SectionHeading } from "../ui/SectionHeading";
import { ScreenshotPlaceholder } from "../ui/ScreenshotPlaceholder";

const stepsData = [
  {
    stepNumber: 1,
    title: "Start on WhatsApp",
    description: "Send a message to Dream Destiny on WhatsApp. No app store downloads, no passwords to create, and no new platform to master.",
    src: "/images/whatsapp/step-1-start-chat.png",
    alt: "WhatsApp screenshot showing greeting and onboarding conversation with Dream Destiny bot",
  },
  {
    stepNumber: 2,
    title: "Share your preferences",
    description: "Tell the bot your travel dates, origin, destination, budget, and travel style. Dream Destiny coordinates with verified travel APIs.",
    src: "/images/whatsapp/step-2-preferences.png",
    alt: "WhatsApp screenshot showing transport options and tourist attractions recommendations",
  },
  {
    stepNumber: 3,
    title: "Explore your plan",
    description: "Receive a structured day-by-day itinerary with train, bus, flight, and hotel ideas. Ask follow-up questions to customize any detail.",
    src: "/images/whatsapp/step-3-itinerary.png",
    alt: "WhatsApp screenshot showing day-wise itinerary display",
  },
];

export function HowItWorksSection() {
  return (
    <section
      id="how-it-works"
      aria-labelledby="how-it-works-heading"
      className="py-16 sm:py-24 bg-[#F2F6F6]"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="HOW IT WORKS"
          title="Plan Your Journey in 3 Effortless Steps"
          subtitle="From your first message to an organized, multi-modal itinerary—the entire experience happens in your WhatsApp conversation."
        />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 lg:gap-10">
          {stepsData.map((step) => (
            <ScreenshotPlaceholder
              key={step.stepNumber}
              stepNumber={step.stepNumber}
              title={step.title}
              description={step.description}
              src={step.src}
              alt={step.alt}
            />
          ))}
        </div>

        {/* Microcopy footnote */}
        <div className="mt-12 text-center">
          <p className="text-xs text-[#5E6060]">
            * Actual screenshots will replace placeholders upon official bot release. No personal user data is ever displayed publicly.
          </p>
        </div>
      </div>
    </section>
  );
}
