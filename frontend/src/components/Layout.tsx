import { useState, type ReactNode } from "react";
import { Link, type Route } from "../router";
import { useProfile } from "../state/ProfileContext";
import { BookIcon, CompassIcon, GridIcon, ShieldIcon, UserIcon } from "./icons";

const NAV: { to: string; label: string; match: Route["name"][]; icon: ReactNode }[] = [
  { to: "dashboard", label: "Dashboard", match: ["dashboard"], icon: <GridIcon size={17} /> },
  { to: "opportunities", label: "Opportunities", match: ["opportunities", "opportunity"], icon: <CompassIcon size={17} /> },
  { to: "profile", label: "Profile", match: ["profile"], icon: <UserIcon size={17} /> },
  { to: "about", label: "How it works", match: ["about"], icon: <BookIcon size={17} /> },
];

function Logo() {
  return (
    <Link to="" className="logo" aria-label="EligiCore home">
      <span className="logo__mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="28" height="28">
          <rect x="0.5" y="0.5" width="31" height="31" rx="8" fill="#15130f" stroke="currentColor" strokeOpacity="0.55" />
          <path
            d="M9.5 16.5l4.2 4.2L22.5 11.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
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

/**
 * One shell, two compositions. The landing page gets an editorial top bar; every workspace
 * screen gets a sidebar on wide screens and a sheet menu on small ones. The markup is the
 * same in both, so navigation, accessible names and keyboard order never diverge.
 */
export function Layout({ route, children }: { route: Route; children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const mode = route.name === "landing" ? "marketing" : "workspace";
  return (
    <div className={`app app--${mode}`}>
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
      <header className="shell">
        <div className="shell__inner">
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
            <p className="nav__label" aria-hidden="true">
              Workspace
            </p>
            {NAV.map((item) => {
              const active = item.match.includes(route.name);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`nav__link ${active ? "nav__link--active" : ""}`}
                  aria-current={active ? "page" : undefined}
                >
                  <span className="nav__icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  {item.label}
                </Link>
              );
            })}
            <div className="nav__footer">
              <ProfilePill />
              <p className="nav__note">
                <ShieldIcon size={13} />
                Stays in this tab
              </p>
            </div>
          </nav>
        </div>
      </header>
      <div className="content">
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
    </div>
  );
}
