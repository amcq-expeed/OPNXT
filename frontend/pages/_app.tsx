import type { AppProps } from "next/app";
import Head from "next/head";
import "../styles/globals.css";
import "../styles/tokens.css";
import "../styles/tailwind.css";
import "../styles/theme.css";
import "../styles/auth.css";
import "../styles/dashboard.css";
import "../styles/support-widget.css";
import "../styles/accelerator.css";
import AppShell from "../components/AppShell";

export default function MyApp({ Component, pageProps }: AppProps) {
  return (
    <AppShell>
      <Head>
        <link rel="icon" href="/opnxt-logo.svg" type="image/svg+xml" />
        <link rel="apple-touch-icon" href="/opnxt-logo.svg" />
      </Head>
      <Component {...pageProps} />
    </AppShell>
  );
}
