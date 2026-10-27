/**
 * Helper to generate an official WhatsApp deep link.
 * Reads NEXT_PUBLIC_WHATSAPP_NUMBER environment variable.
 * If not set or invalid, indicates unconfigured status to avoid linking to fake numbers.
 */

const DEFAULT_GREETING = "Hello Dream Destiny! I'd like to plan a trip.";

export interface WhatsAppLinkInfo {
  isConfigured: boolean;
  url: string;
  phoneNumber?: string;
  message: string;
}

export function getWhatsAppLink(customGreeting?: string): WhatsAppLinkInfo {
  const rawNumber = process.env.NEXT_PUBLIC_WHATSAPP_NUMBER?.trim();
  const greeting = customGreeting || DEFAULT_GREETING;
  const encodedGreeting = encodeURIComponent(greeting);

  // Validate that the number is only digits and has an international phone length (e.g. 10 to 15 digits)
  const sanitizedNumber = rawNumber ? rawNumber.replace(/[^0-9]/g, "") : "";

  if (sanitizedNumber && sanitizedNumber.length >= 10) {
    return {
      isConfigured: true,
      url: `https://wa.me/${sanitizedNumber}?text=${encodedGreeting}`,
      phoneNumber: `+${sanitizedNumber}`,
      message: greeting,
    };
  }

  return {
    isConfigured: false,
    url: "#whatsapp-unconfigured",
    phoneNumber: undefined,
    message: greeting,
  };
}
