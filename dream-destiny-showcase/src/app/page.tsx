import React from "react";
import { HeroSection } from "../components/sections/HeroSection";
import { HowItWorksSection } from "../components/sections/HowItWorksSection";
import { FeaturesSection } from "../components/sections/FeaturesSection";
import { PoweredBySection } from "../components/sections/PoweredBySection";
import { JourneysSection } from "../components/sections/JourneysSection";
import { ReviewsSection } from "../components/sections/ReviewsSection";
import { FinalCtaSection } from "../components/sections/FinalCtaSection";

export default function Home() {
  return (
    <main id="main-content" className="flex-1 w-full focus:outline-none" tabIndex={-1}>
      <HeroSection />
      <HowItWorksSection />
      <FeaturesSection />
      <PoweredBySection />
      <JourneysSection />
      <ReviewsSection />
      <FinalCtaSection />
    </main>
  );
}
