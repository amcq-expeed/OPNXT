declare module "event-source-polyfill" {
  export const EventSourcePolyfill: {
    new (
      url: string | URL,
      init?: EventSourceInit & { headers?: Record<string, string> },
    ): EventSource;
  };
}
