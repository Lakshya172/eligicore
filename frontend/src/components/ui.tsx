import type { ReactNode } from "react";
import { describeError, ApiError } from "../api/client";
import type { EligibilityState } from "../api/types";
import { VERDICTS, type Tone } from "../lib/eligibility";

export function Badge({ tone = "neutral", children }: { tone?: Tone | "accent"; children: ReactNode }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function VerdictBadge({ state }: { state: EligibilityState }) {
  const meta = VERDICTS[state];
  return (
    <span className={`verdict verdict--${meta.tone}`}>
      <span className="verdict__dot" aria-hidden="true" />
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
    <div className="job-grid" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="card skeleton-card">
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
      <div className="state__icon" aria-hidden="true">!</div>
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
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="state">
      <div className="state__icon state__icon--muted" aria-hidden="true">○</div>
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
      <div>
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
      <strong>Demo catalogue.</strong> These openings come from EligiCore's curated synthetic
      dataset. Every employer is fictional, and application links are placeholders.
    </p>
  );
}
