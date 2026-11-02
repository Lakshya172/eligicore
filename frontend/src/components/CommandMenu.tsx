import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { navigate, type Route } from "../router";
import { BookIcon, CompassIcon, GridIcon, HomeIcon, SearchIcon, UserIcon } from "./icons";

interface Destination {
  to: string;
  label: string;
  description: string;
  keywords: string;
  match: Route["name"][];
  icon: ReactNode;
}

/** Every entry is an existing route. The menu only navigates; it never acts on data. */
const DESTINATIONS: Destination[] = [
  { to: "", label: "Home", description: "What EligiCore does", keywords: "landing start", match: ["landing"], icon: <HomeIcon /> },
  { to: "dashboard", label: "Dashboard", description: "Your eligibility at a glance", keywords: "overview results summary", match: ["dashboard"], icon: <GridIcon /> },
  { to: "opportunities", label: "Opportunities", description: "Browse and filter the catalogue", keywords: "jobs internships roles search", match: ["opportunities", "opportunity"], icon: <CompassIcon /> },
  { to: "profile", label: "Profile", description: "Education, backlogs and résumé", keywords: "resume upload education cgpa", match: ["profile"], icon: <UserIcon /> },
  { to: "about", label: "How it works", description: "How each verdict is decided", keywords: "help verdicts rules ai about", match: ["about"], icon: <BookIcon /> },
];

export function CommandMenu({
  route,
  leaving,
  onClose,
}: {
  route: Route;
  leaving: boolean;
  onClose: (options?: { restoreFocus: boolean }) => void;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  const titleId = useId();

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return DESTINATIONS;
    return DESTINATIONS.filter((item) =>
      `${item.label} ${item.description} ${item.keywords}`.toLowerCase().includes(needle),
    );
  }, [query]);
  const activeIndex = Math.min(active, Math.max(results.length - 1, 0));

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function open(item: Destination) {
    navigate(item.to);
    onClose({ restoreFocus: false });
    // Land keyboard users on the new page's content rather than on <body>.
    window.requestAnimationFrame(() => document.getElementById("main")?.focus());
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (results.length) setActive((activeIndex + 1) % results.length);
        break;
      case "ArrowUp":
        event.preventDefault();
        if (results.length) setActive((activeIndex - 1 + results.length) % results.length);
        break;
      case "Enter": {
        event.preventDefault();
        const item = results[activeIndex];
        if (item) open(item);
        break;
      }
      case "Escape":
        event.preventDefault();
        onClose();
        break;
      case "Tab":
        // The search field is the dialog's only tab stop; options are reached with the arrows.
        event.preventDefault();
        break;
    }
  }

  return (
    <div className={`command ${leaving ? "command--leaving" : ""}`}>
      <div className="command__backdrop" aria-hidden="true" onMouseDown={() => onClose()} />
      <div className="command__panel" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <h2 id={titleId} className="visually-hidden">
          Quick navigation
        </h2>
        <div className="command__search">
          <SearchIcon />
          <input
            ref={inputRef}
            className="command__input"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={results[activeIndex] ? `${listId}-${activeIndex}` : undefined}
            aria-label="Go to page"
            placeholder="Go to…"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
          />
          <kbd className="kbd">Esc</kbd>
        </div>
        <ul id={listId} className="command__list" role="listbox" aria-label="Pages">
          {results.map((item, index) => (
            <li
              key={item.to}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === activeIndex}
              className={`command__item ${index === activeIndex ? "command__item--active" : ""}`}
              onMouseMove={() => setActive(index)}
              onClick={() => open(item)}
            >
              <span className="command__icon" aria-hidden="true">
                {item.icon}
              </span>
              <span className="command__text">
                <span className="command__label">{item.label}</span>
                <span className="command__description">{item.description}</span>
              </span>
              {item.match.includes(route.name) && <span className="command__current">Current</span>}
            </li>
          ))}
        </ul>
        {results.length === 0 && <p className="command__empty">No page matches “{query.trim()}”.</p>}
        <p className="command__footer" aria-hidden="true">
          <span>
            <kbd className="kbd">↑</kbd>
            <kbd className="kbd">↓</kbd> move
          </span>
          <span>
            <kbd className="kbd">↵</kbd> open
          </span>
          <span>
            <kbd className="kbd">Esc</kbd> close
          </span>
        </p>
      </div>
    </div>
  );
}
