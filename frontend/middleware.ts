import { NextResponse, NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const url = req.nextUrl;
  const p = url.pathname;

  // Allow static assets and Next internals
  if (
    p.startsWith("/_next") ||
    p.startsWith("/api") ||
    p.startsWith("/opnxt-logo.svg") ||
    p.startsWith("/favicon") ||
    p.startsWith("/fonts") ||
    p.startsWith("/images")
  ) {
    return NextResponse.next();
  }

  // Keep MVP and root
  if (p === "/" || p === "/mvp") {
    return NextResponse.next();
  }

  // For anything else, force redirect to MVP
  url.pathname = "/mvp";
  return NextResponse.redirect(url);
}
