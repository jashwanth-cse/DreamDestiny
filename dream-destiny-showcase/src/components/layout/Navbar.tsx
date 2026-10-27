"use client";

import React, { useState, useEffect } from "react";
import Image from "next/image";
import { MessageCircle, Menu, X } from "lucide-react";
import { Button } from "../ui/Button";
import { getWhatsAppLink } from "../../lib/whatsapp";
import { WhatsAppNoticeModal } from "../ui/WhatsAppNoticeModal";

const navLinks = [
  { href: "#overview", label: "Overview" },
  { href: "#how-it-works", label: "How It Works" },
  { href: "#features", label: "Features" },
  { href: "#powered-by", label: "Powered By" },
  { href: "#journeys", label: "Journeys" },
  { href: "#reviews", label: "Our Users" },
];

export function Navbar() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isNoticeOpen, setIsNoticeOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);

  const waLink = getWhatsAppLink();

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 16);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsMobileMenuOpen(false);
        setIsNoticeOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleWhatsAppClick = (e: React.MouseEvent) => {
    if (!waLink.isConfigured) {
      e.preventDefault();
      setIsNoticeOpen(true);
    }
  };

  return (
    <>
      <header
        className={`sticky top-0 z-40 w-full transition-all duration-300 ${
          isScrolled
            ? "bg-[#F2F6F6]/90 backdrop-blur-md shadow-[0_4px_20px_rgba(13,15,16,0.03)] border-b border-[rgba(13,15,16,0.06)]"
            : "bg-[#F2F6F6] border-b border-transparent"
        }`}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
          {/* Brand Logo & Tagline */}
          <a
            href="#overview"
            className="flex items-center gap-3 group focus-visible:outline-2 focus-visible:outline-[#0B2345] rounded-xl p-1"
            aria-label="Dream Destiny - Return to Overview"
          >
            <div className="relative w-10 h-10 rounded-full flex items-center justify-center overflow-hidden shrink-0 shadow-sm border border-[rgba(11,35,69,0.08)]">
              <Image
                src="/brand/dream-destiny-logo.png"
                alt="Dream Destiny brand icon"
                width={40}
                height={40}
                className="w-full h-full object-cover"
                priority
              />
            </div>
            <div className="flex flex-col">
              <span className="text-base sm:text-lg font-extrabold text-[#0D0F10] tracking-[-0.02em] leading-tight group-hover:text-[#0B2345] transition-colors">
                Dream Destiny
              </span>
              <span className="text-[10px] sm:text-[11px] font-semibold text-[#5E6060] tracking-[0.04em] uppercase">
                Your Travel Companion
              </span>
            </div>
          </a>

          {/* Desktop Navigation Links */}
          <nav
            aria-label="Main Navigation"
            className="hidden md:flex items-center gap-1 lg:gap-2 bg-white/70 backdrop-blur-sm px-4 py-1.5 rounded-full border border-[rgba(13,15,16,0.06)] shadow-sm"
          >
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-xs lg:text-sm font-medium text-[#5E6060] hover:text-[#0D0F10] hover:bg-[#F2F6F6] px-3.5 py-1.5 rounded-full transition-all duration-150 focus-visible:outline-[#0B2345]"
              >
                {link.label}
              </a>
            ))}
          </nav>

          {/* Primary CTA Button */}
          <div className="hidden sm:flex items-center gap-3">
            <Button
              variant="whatsapp"
              size="sm"
              href={waLink.url}
              external={waLink.isConfigured}
              onClick={handleWhatsAppClick}
              icon={<MessageCircle className="w-4 h-4 fill-white/20" />}
              aria-label="Chat with Dream Destiny on WhatsApp"
            >
              Chat on WhatsApp
            </Button>
          </div>

          {/* Mobile Menu Button */}
          <button
            type="button"
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="md:hidden p-2 rounded-xl text-[#0D0F10] hover:bg-white focus-visible:outline-[#0B2345] transition-colors"
            aria-expanded={isMobileMenuOpen}
            aria-controls="mobile-navigation"
            aria-label={isMobileMenuOpen ? "Close menu" : "Open menu"}
          >
            {isMobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {/* Mobile Navigation Drawer */}
        {isMobileMenuOpen && (
          <div
            id="mobile-navigation"
            className="md:hidden bg-white/98 border-b border-[rgba(13,15,16,0.08)] px-6 py-6 shadow-xl backdrop-blur-lg animate-in slide-in-from-top-2 duration-200"
          >
            <nav aria-label="Mobile Navigation" className="flex flex-col gap-2 mb-6">
              {navLinks.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="text-base font-semibold text-[#0D0F10] hover:text-[#79B66A] py-2 px-3 rounded-lg hover:bg-[#F2F6F6] transition-colors"
                >
                  {link.label}
                </a>
              ))}
            </nav>
            <div className="pt-4 border-t border-[rgba(13,15,16,0.08)] flex flex-col gap-3">
              <Button
                variant="whatsapp"
                size="md"
                href={waLink.url}
                external={waLink.isConfigured}
                onClick={(e) => {
                  handleWhatsAppClick(e);
                  setIsMobileMenuOpen(false);
                }}
                icon={<MessageCircle className="w-4 h-4" />}
                className="w-full justify-center"
              >
                Chat on WhatsApp
              </Button>
              <p className="text-center text-[11px] font-medium text-[#5E6060]">
                No app installation. No separate signup. Just WhatsApp.
              </p>
            </div>
          </div>
        )}
      </header>

      {/* WhatsApp Configuration notice modal */}
      <WhatsAppNoticeModal
        isOpen={isNoticeOpen}
        onClose={() => setIsNoticeOpen(false)}
        isConfigured={waLink.isConfigured}
        phoneNumber={waLink.phoneNumber}
        url={waLink.url}
      />
    </>
  );
}
