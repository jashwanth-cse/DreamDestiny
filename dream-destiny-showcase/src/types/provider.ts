export type ProviderGroup = "By Rail" | "By Road" | "By Air" | "Stay & Explore" | "Smart Planning";

export type IntegrationStatus = "Live Integrated Source" | "Configured Integration" | "Planned Integration";

export interface Provider {
  id: string;
  name: string;
  group: ProviderGroup;
  shortDescription: string;
  detailedDescription: string;
  status: IntegrationStatus;
  logoSrc: string;
  logoAlt: string;
  attributionNote?: string;
  officialSite?: string;
}
