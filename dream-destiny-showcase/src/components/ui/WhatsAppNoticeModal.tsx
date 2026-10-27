"use client";

import React from "react";
import { X, MessageCircle, AlertCircle, Check } from "lucide-react";
import { Button } from "./Button";

interface WhatsAppNoticeModalProps {
  isOpen: boolean;
  onClose: () => void;
  isConfigured: boolean;
  phoneNumber?: string;
  url: string;
}

export function WhatsAppNoticeModal({
  isOpen,
  onClose,
  isConfigured,
  phoneNumber,
  url,
}: WhatsAppNoticeModalProps) {
  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="wa-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-[#0D0F10]/60 backdrop-blur-sm animate-in fade-in duration-200"
    >
      <div
        className="bg-white rounded-3xl max-w-md w-full p-6 sm:p-8 border border-[rgba(13,15,16,0.12)] shadow-2xl relative"
        tabIndex={-1}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute top-5 right-5 p-2 rounded-full text-[#5E6060] hover:bg-[#F2F6F6] hover:text-[#0D0F10] transition-colors focus-visible:outline-[#0B2345]"
          aria-label="Close dialog"
        >
          <X className="w-5 h-5" />
        </button>

        {isConfigured ? (
          <div>
            <div className="w-12 h-12 rounded-2xl bg-[#E8F1EF] text-[#79B66A] flex items-center justify-center mb-4">
              <MessageCircle className="w-6 h-6" />
            </div>
            <h3 id="wa-modal-title" className="text-xl font-bold text-[#0D0F10] mb-2">
              Connect to Dream Destiny on WhatsApp
            </h3>
            <p className="text-sm text-[#5E6060] leading-relaxed mb-4">
              You are being directed to the official Dream Destiny WhatsApp bot at <strong className="text-[#0D0F10]">{phoneNumber}</strong>.
            </p>
            <div className="p-3 bg-[#F2F6F6] rounded-2xl text-xs text-[#0D0F10] mb-6 flex items-center gap-2">
              <Check className="w-4 h-4 text-[#79B66A] shrink-0" />
              <span>Verified automated itinerary assistant. No extra app required.</span>
            </div>
            <div className="flex gap-3 justify-end">
              <Button variant="secondary" size="sm" onClick={onClose}>
                Cancel
              </Button>
              <Button
                variant="whatsapp"
                size="sm"
                href={url}
                external
                onClick={onClose}
                icon={<MessageCircle className="w-4 h-4" />}
              >
                Open WhatsApp
              </Button>
            </div>
          </div>
        ) : (
          <div>
            <div className="w-12 h-12 rounded-2xl bg-[#FCEFD8] text-[#856404] flex items-center justify-center mb-4">
              <AlertCircle className="w-6 h-6" />
            </div>
            <h3 id="wa-modal-title" className="text-xl font-bold text-[#0D0F10] mb-2">
              WhatsApp Bot Configuration Notice
            </h3>
            <p className="text-sm text-[#5E6060] leading-relaxed mb-4">
              The live bot phone number is not currently configured in the environment variables.
            </p>
            <div className="p-4 bg-[#F2F6F6] rounded-2xl text-xs text-[#0D0F10] mb-6 space-y-2">
              <p className="font-semibold text-[#0B2345]">Deployment Setup Step:</p>
              <p className="text-[#5E6060]">
                To activate direct WhatsApp chats, supply the international phone number in your environment:
              </p>
              <code className="block bg-white p-2 rounded border border-[rgba(13,15,16,0.08)] font-mono text-[11px] text-[#0D0F10]">
                NEXT_PUBLIC_WHATSAPP_NUMBER=91XXXXXXXXXX
              </code>
              <p className="text-[11px] text-[#5E6060]">
                Per product integrity rules, no placeholder or fabricated phone number is linked.
              </p>
            </div>
            <div className="flex justify-end">
              <Button variant="primary" size="sm" onClick={onClose}>
                Understood
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
