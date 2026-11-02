import type { ReactNode } from "react";
import { describeError, ApiError } from "../api/client";
import type { EligibilityState } from "../api/types";
import { VERDICTS, type Tone } from "../lib/eligibility";
import { AlertIcon, CheckIcon, CrossIcon, InfoIcon, QuestionIcon, SearchIcon } from "./icons";

export function Badge({ tone = "neutral", children }: { tone?: Tone | "accent"; children: ReactNode }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

/** The glyph beside a verdict, so its meaning never depends on colour alone. */
function VerdictGlyph({ tone }: { tone: Tone }) {
  if (tone === "success" || tone === "info") return <CheckIcon size={13} />;
  if (tone === "danger") return <CrossIcon size={13} />;
  return <QuestionIcon size={13} />;
}

export function VerdictBadge({ state }: { state: EligibilityState }) {
  const meta = VERDICTS[state];
  return (
    <span className={`verdict verdict--${meta.tone}`}>
      <VerdictGlyph tone={meta.tone} />
      {meta.label}
    </span>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`.trim()}>{children}</section>;
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="spinner" role="status">
      <span className="spinner__ring" aria-hidden="true" />
      <span className="visually-hidden">{label}</span>
    </span>
  );
}

export function SkeletonCards({ count = 6 }: { count?: number }) {
  return (
    <div className="job-grid" aria-busy="true" aria-label="Loading opportunities">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="card skeleton-card" aria-hidden="true">
          <div className="skeleton-card__top">
            <div className="skeleton skeleton--avatar" />
            <div className="skeleton skeleton--pill" />
          </div>
          <div className="skeleton skeleton--title" />
          <div className="skeleton skeleton--line" />
          <div className="skeleton skeleton--line skeleton--short" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = "We couldn't load this",
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  const offline = error instanceof ApiError && (error.isNetworkError || error.status >= 500);
  return (
    <div className="state state--error" role="alert">
      <div className="state__icon state__icon--error" aria-hidden="true">
        <AlertIcon size={20} />
      </div>
      <h2 className="state__title">{offline ? "The EligiCore API isn't responding" : title}</h2>
      <p className="state__text">{describeError(error)}</p>
      {offline && (
        <p className="state__hint">
          Start the backend with <code>uvicorn app.main:app</code>, then try again.
        </p>
      )}
      {error instanceof ApiError && error.requestId && (
        <p className="state__meta">Reference: {error.requestId}</p>
      )}
      {onRetry && (
        <button type="button" className="button button--secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
  icon,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="state">
      <div className="state__icon" aria-hidden="true">
        {icon ?? <SearchIcon size={20} />}
      </div>
      <h2 className="state__title">{title}</h2>
      {children && <div className="state__text">{children}</div>}
      {action && <div className="state__action">{action}</div>}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  children,
  actions,
}: {
  eyebrow?: string;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-header__text">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="page-title">{title}</h1>
        {children && <div className="page-lead">{children}</div>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}

/** States, every time it matters, that the catalogue is synthetic. */
export function CatalogueNotice() {
  return (
    <p className="notice notice--info">
      <InfoIcon />
      <span>
        <strong>Demo catalogue.</strong> These openings come from EligiCore's curated synthetic
        dataset. Every employer is fictional, and application links are placeholders.
      </span>
    </p>
  );
}

/** A section heading inside a card, with an optional action on the right. */
export function SectionHead({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="section-head">
      <div>
        <h2 className="section-head__title">{title}</h2>
        {children && <div className="section-head__text">{children}</div>}
      </div>
      {action && <div className="section-head__action">{action}</div>}
    </div>
  );
}
