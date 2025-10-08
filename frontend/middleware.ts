import { NextResponse, NextRequest } from "next/server";

const PUBLIC_MODE =
  process.env.NEXT_PUBLIC_PUBLIC_MODE === "1" ||
  process.env.NEXT_PUBLIC_PUBLIC_MODE === "true";

export function middleware(req: NextRequest) {
  if (!PUBLIC_MODE) {
    return NextResponse.next();
  }
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
