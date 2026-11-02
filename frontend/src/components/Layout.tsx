import { useState, type ReactNode } from "react";
import { Link, type Route } from "../router";
import { useProfile } from "../state/ProfileContext";

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
      <a className="skip-link" href="#main">
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
            <span aria-hidden="true">{menuOpen ? "✕" : "☰"}</span>
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
          <p>
            <strong>EligiCore</strong> helps you discover openings and understand your eligibility.
            It never applies on your behalf.
          </p>
          <p className="footer__privacy">
            Your profile stays in this browser tab. The server evaluates it and keeps nothing.
          </p>
        </div>
      </footer>
    </div>
  );
}
