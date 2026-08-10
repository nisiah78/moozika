"use client";

import type { TripletBracketRole } from "@/lib/triplets";

/** Crochet de triolet (demi-carré + chiffre 3), style solfège. */
export function TripletBracket({ role }: { role: TripletBracketRole }) {
  return (
    <span
      className={`solfa-triplet-bracket solfa-triplet-bracket--${role}`}
      aria-label="Triolet"
    >
      <span className="solfa-triplet-bracket__num" aria-hidden>
        3
      </span>
      <span className="solfa-triplet-bracket__rail" aria-hidden />
    </span>
  );
}
