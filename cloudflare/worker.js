/**
 * Cloudflare Worker: Reverse Proxy & Edge Cache for TrainWatch & Transport Service
 *
 * Routes incoming traffic from `https://trains.jashh.me/*`
 * to Google Cloud Run with automatic host routing and edge caching.
 *
 * Configurable Environment Variables (env):
 * - ORIGIN_URL / TRAIN_API_BASE_URL: Backend origin base URL (e.g. https://dreamdestiny.cloud.run)
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Retrieve origin from Cloudflare Worker environment variables
    const rawOrigin = env?.ORIGIN_URL || env?.TRAIN_API_BASE_URL || "https://dreamdestiny.cloud.run";
    const originUrl = rawOrigin.replace(/\/+$/, "");

    // Target Google Cloud Run origin
    const targetUrl = originUrl + url.pathname + url.search;

    const isSchedule = url.pathname.includes("/schedule");

    // fetch() automatically sets the correct Host header from targetUrl.
    // Do NOT manually override the "Host" header as Cloudflare blocks that with Error 1003.
    return fetch(targetUrl, {
      method: request.method,
      headers: request.headers,
      body: request.method !== "GET" && request.method !== "HEAD" ? request.body : null,
      redirect: "follow",
      cf: isSchedule
        ? {
            cacheEverything: true,
            cacheTtl: 86400, // 24 hours edge cache for schedule
          }
        : undefined,
    });
  },
};
