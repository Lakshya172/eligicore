// A minimal hash router. Hash URLs need no server rewrite rules, so the built app works
// from `vite preview` or any static host without configuration.

import { useEffect, useState, type AnchorHTMLAttributes, type ReactNode } from "react";

export type Route =
  | { name: "landing" }
  | { name: "dashboard" }
  | { name: "opportunities" }
  | { name: "opportunity"; jobId: string }
  | { name: "profile" }
  | { name: "about" }
  | { name: "not-found" };

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, "").replace(/^\/+|\/+$/g, "");
  if (path === "") return { name: "landing" };
  const [first, second, ...rest] = path.split("/");
  if (rest.length > 0) return { name: "not-found" };
  switch (first) {
    case "dashboard":
      return second ? { name: "not-found" } : { name: "dashboard" };
    case "opportunities":
      return second
        ? { name: "opportunity", jobId: decodeURIComponent(second) }
        : { name: "opportunities" };
    case "profile":
      return second ? { name: "not-found" } : { name: "profile" };
    case "about":
      return second ? { name: "not-found" } : { name: "about" };
    default:
      return { name: "not-found" };
  }
}

export function href(path: string): string {
  return `#/${path.replace(/^\/+/, "")}`;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parseRoute(window.location.hash));
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function navigate(path: string): void {
  window.location.hash = href(path);
}

interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  to: string;
  children: ReactNode;
}

export function Link({ to, children, ...rest }: LinkProps) {
  return (
    <a href={href(to)} {...rest}>
      {children}
    </a>
  );
}
