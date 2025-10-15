import { useEffect } from "react";
import { useRouter } from "next/router";
import Head from "next/head";
import { logout } from "../lib/api";

export default function LogoutPage() {
  const router = useRouter();

  useEffect(() => {
    logout();
    const target = router.query.returnTo;
    const nextPath = typeof target === "string" && target.startsWith("/") ? target : "/login";
    router.replace(nextPath);
  }, [router]);

  return (
    <div className="auth-page" aria-live="polite">
      <Head>
        <title>Signing out · OPNXT</title>
      </Head>
      <div className="auth-page__panel" style={{ textAlign: "center" }}>
        <span className="badge">Signing out</span>
        <h1>See you soon</h1>
        <p>We’re wrapping up your session and will redirect you momentarily.</p>
      </div>
    </div>
  );
}
