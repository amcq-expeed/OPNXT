import { useEffect } from "react";
import { useRouter } from "next/router";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    if (router.asPath !== "/login") {
      router.replace("/login");
    }
  }, [router]);

  return null;
}
