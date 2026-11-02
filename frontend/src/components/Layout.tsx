import { useState, type ReactNode } from "react";
import { Link, type Route } from "../router";
import { useProfile } from "../state/ProfileContext";
import { ShieldIcon } from "./icons";

const NAV: { to: string; label: string; match: Route["name"][] }[] = [
  { to: "dashboard", label: "Dashboard", match: ["dashboard"] },
  { to: "opportunities", label: "Opportunities", match: ["opportunities", "opportunity"] },
  { to: "profile", label: "Profile", match: ["profile"] },
  { to: "about", label: "How it works", match: ["about"] },
];

function Logo() {
  return (
    <Link to="" className="logo" aria-label="EligiCore home">
      <span className="logo__mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="28" height="28">
          <rect width="32" height="32" rx="8" fill="currentColor" />
          <path
            d="M9 16.5l4.5 4.5L23 11.5"
            fill="none"
            stroke="#fff"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span className="logo__text">EligiCore</span>
    </Link>
  );
}

function ProfilePill() {
  const { profile, isSample } = useProfile();
  if (!profile) {
    return (
      <Link to="profile" className="profile-pill profile-pill--empty">
        Add profile
      </Link>
    );
  }
  return (
    <Link to="profile" className={`profile-pill ${isSample ? "profile-pill--sample" : ""}`}>
      <span className="profile-pill__dot" aria-hidden="true" />
      {isSample ? "Sample profile (fictional)" : "Your profile"}
    </Link>
  );
}

export function Layout({ route, children }: { route: Route; children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="app">
      {/* Moves focus without touching the hash: with hash routing, href="#main" would be read
          as a route and land on "Page not found". */}
      <a
        className="skip-link"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar__inner">
          <Logo />
          <button
            type="button"
            className="menu-toggle"
            aria-expanded={menuOpen}
            aria-controls="primary-nav"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="visually-hidden">Menu</span>
            <span className={`menu-toggle__bars ${menuOpen ? "menu-toggle__bars--open" : ""}`} aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </button>
          <nav
            id="primary-nav"
            className={`nav ${menuOpen ? "nav--open" : ""}`}
            aria-label="Primary"
            onClick={() => setMenuOpen(false)}
          >
            {NAV.map((item) => {
              const active = item.match.includes(route.name);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`nav__link ${active ? "nav__link--active" : ""}`}
                  aria-current={active ? "page" : undefined}
                >
                  {item.label}
                </Link>
              );
            })}
            <ProfilePill />
          </nav>
        </div>
      </header>
      <main id="main" className="main" tabIndex={-1}>
        {children}
      </main>
      <footer className="footer">
        <div className="footer__inner">
          <div className="footer__brand">
            <Logo />
            <p>
              Helps students discover openings and understand their eligibility. It never applies on
              anyone's behalf.
            </p>
          </div>
          <nav className="footer__nav" aria-label="Footer">
            {NAV.map((item) => (
              <Link key={item.to} to={item.to} className="footer__link">
                {item.label}
              </Link>
            ))}
          </nav>
          <p className="footer__privacy">
            <ShieldIcon size={15} />
            Your profile stays in this browser tab. The server evaluates it and keeps nothing.
          </p>
        </div>
      </footer>
    </div>
  );
}
