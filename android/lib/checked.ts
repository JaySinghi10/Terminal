// When the app last asked the server about each flight, for the label that says
// so.
//
// ── A CONTEXT OF ITS OWN, AND WHY IT IS NOT ON THE RECORD ────────────────────
//
// THE RECORD ALREADY HAS updatedAt, AND IT MEANS SOMETHING ELSE. updatedAt is
// how old the PROVIDER'S answer is -- now minus data_age_seconds -- and it gates
// whether a live countdown can be trusted. The passive reader in lib/saved.tsx
// fetches once a minute, but what it fetches is the server's stored copy, which
// may be five minutes old; writing the fetch time into updatedAt would make a
// five-minute-old estimate look brand new and keep it looking so every minute.
// So the two times are kept apart: the record says how old the data is, this
// says when we last looked.
//
// IN MEMORY ONLY, DELIBERATELY. It exists so a person can see the app is
// watching while it is open. Persisting it would mean a cold start showing
// "updated 30s ago" for a fetch that happened before the phone was off, which
// is the opposite of what the label is for. Absent, the label falls back to the
// data's own age, which is the honest thing to show.
//
// ITS OWN FILE SO THAT BOTH SIDES CAN IMPORT IT. lib/saved.tsx provides it and
// lib/flightstatus.tsx reads it, and flightstatus already imports from saved;
// putting this in either would add to a cycle that has so far stayed harmless.
import { createContext, useContext } from 'react';

export type CheckedAt = Readonly<Record<string, number>>;

export const CheckedContext = createContext<CheckedAt>({});

/** When the app last fetched this flight from the server, or null. */
export function useCheckedAt(id: string): number | null {
  const all = useContext(CheckedContext);
  const t = all[id];
  return typeof t === 'number' ? t : null;
}
