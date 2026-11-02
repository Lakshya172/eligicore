// The student's profile lives in this browser tab only. EligiCore's server stores no
// candidate data (ADR-001, ADR-011, INV-1): the profile is sent with each evaluation
// request and kept here, in sessionStorage, which the browser clears when the tab closes.

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { CandidateProfile } from "../api/types";
import { withoutResumeText } from "../lib/profile";

const STORAGE_KEY = "eligicore.profile.v1";

interface StoredProfile {
  profile: CandidateProfile;
  isSample: boolean;
  /** Changes whenever the profile changes, so cached evaluations are discarded. */
  revision: number;
}

interface ProfileContextValue {
  profile: CandidateProfile | null;
  isSample: boolean;
  revision: number;
  setProfile: (profile: CandidateProfile, options?: { isSample?: boolean }) => void;
  clearProfile: () => void;
}

const ProfileContext = createContext<ProfileContextValue | null>(null);

function readStored(): StoredProfile | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredProfile;
    return parsed && typeof parsed === "object" && parsed.profile ? parsed : null;
  } catch {
    return null;
  }
}

function writeStored(value: StoredProfile | null): void {
  try {
    if (value) window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage can be unavailable (private mode, quota). The profile still works in memory.
  }
}

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [stored, setStored] = useState<StoredProfile | null>(() => readStored());

  const setProfile = useCallback(
    (profile: CandidateProfile, options?: { isSample?: boolean }) => {
      setStored((previous) => {
        const next: StoredProfile = {
          profile: withoutResumeText(profile),
          isSample: options?.isSample ?? false,
          revision: (previous?.revision ?? 0) + 1,
        };
        writeStored(next);
        return next;
      });
    },
    [],
  );

  const clearProfile = useCallback(() => {
    writeStored(null);
    setStored(null);
  }, []);

  const value = useMemo<ProfileContextValue>(
    () => ({
      profile: stored?.profile ?? null,
      isSample: stored?.isSample ?? false,
      revision: stored?.revision ?? 0,
      setProfile,
      clearProfile,
    }),
    [stored, setProfile, clearProfile],
  );

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile(): ProfileContextValue {
  const value = useContext(ProfileContext);
  if (!value) throw new Error("useProfile must be used inside ProfileProvider");
  return value;
}
