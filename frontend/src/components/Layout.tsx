import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { isCommandShortcut, MODIFIER_LABEL } from "../lib/shortcuts";
import { Link, type Route } from "../router";
import { useProfile } from "../state/ProfileContext";
import { CommandMenu } from "./CommandMenu";
import { BookIcon, CompassIcon, GridIcon, SearchIcon, ShieldIcon, UserIcon } from "./icons";

const NAV: { to: string; label: string; match: Route["name"][]; icon: ReactNode }[] = [
  { to: "dashboard", label: "Dashboard", match: ["dashboard"], icon: <GridIcon /> },
  { to: "opportunities", label: "Opportunities", match: ["opportunities", "opportunity"], icon: <CompassIcon /> },
  { to: "profile", label: "Profile", match: ["profile"], icon: <UserIcon /> },
  { to: "about", label: "How it works", match: ["about"], icon: <BookIcon /> },
];

/** Matches --t-base in styles.css: the dialog's exit runs before it unmounts. */
const COMMAND_EXIT_MS = 200;

function Logo() {
  return (
    <Link to="" className="logo" aria-label="EligiCore home">
      <span className="logo__mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="26" height="26">
          <rect x="0.75" y="0.75" width="30.5" height="30.5" rx="7" fill="#0f1216" stroke="currentColor" strokeOpacity="0.6" strokeWidth="1.5" />
          <path
            d="M9.5 16.5l4.2 4.2L22.5 11.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
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

type CommandPhase = "closed" | "open" | "leaving";

/**
 * One shell, two compositions. The landing page gets an editorial top bar; every workspace
 * screen gets a sidebar on wide screens and a sheet menu on small ones. The markup is the
 * same in both, so navigation, accessible names and keyboard order never diverge.
 */
export function Layout({ route, children }: { route: Route; children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [command, setCommand] = useState<CommandPhase>("closed");
  const returnFocus = useRef<HTMLElement | null>(null);
  const leaveTimer = useRef<number | undefined>(undefined);
  const mode = route.name === "landing" ? "marketing" : "workspace";
  const activeIndex = NAV.findIndex((item) => item.match.includes(route.name));

  const openCommand = useCallback(() => {
    window.clearTimeout(leaveTimer.current);
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setMenuOpen(false);
    setCommand("open");
  }, []);

  const closeCommand = useCallback(({ restoreFocus = true }: { restoreFocus?: boolean } = {}) => {
    setCommand("leaving");
    window.clearTimeout(leaveTimer.current);
    leaveTimer.current = window.setTimeout(() => setCommand("closed"), COMMAND_EXIT_MS);
    if (restoreFocus) returnFocus.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isCommandShortcut(event)) return;
      event.preventDefault();
      if (command === "open") closeCommand();
      else openCommand();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [command, openCommand, closeCommand]);

  // The page behind the dialog must not scroll while it is open.
  useEffect(() => {
    if (command === "closed") return;
    const root = document.documentElement;
    const previous = root.style.overflow;
    root.style.overflow = "hidden";
    return () => {
      root.style.overflow = previous;
    };
  }, [command]);

  useEffect(() => () => window.clearTimeout(leaveTimer.current), []);

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
            <button type="button" className="nav__command" onClick={openCommand} aria-keyshortcuts="Control+K Meta+K">
              <SearchIcon size={15} />
              <span className="nav__command-label">Quick navigation</span>
              <kbd className="kbd" aria-hidden="true">
                {MODIFIER_LABEL} K
              </kbd>
            </button>
            <p className="nav__label" aria-hidden="true">
              Workspace
            </p>
            <div className="nav__list" style={{ "--nav-index": Math.max(activeIndex, 0) } as CSSProperties}>
              {/* One indicator that travels between items, so a route change reads as movement. */}
              <span className={`nav__indicator ${activeIndex < 0 ? "nav__indicator--hidden" : ""}`} aria-hidden="true" />
              {NAV.map((item, index) => {
                const active = index === activeIndex;
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
            </div>
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
              <ShieldIcon size={14} />
              Your profile stays in this browser tab. The server evaluates it and keeps nothing.
              <span className="footer__shortcut">
                <kbd className="kbd">{MODIFIER_LABEL} K</kbd> quick navigation
              </span>
            </p>
          </div>
        </footer>
      </div>
      {command !== "closed" && <CommandMenu route={route} leaving={command === "leaving"} onClose={closeCommand} />}
    </div>
  );
}
