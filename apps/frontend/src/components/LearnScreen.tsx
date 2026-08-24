import { LESSON_SETS } from "@/lib/lessons";
import { NOTATION_LABEL, type Notation } from "@/lib/navigation";

/**
 * Composant serveur : contenu purement statique, rien à hydrater.
 * Les cartes ne sont volontairement PAS cliquables — aucune leçon n'a encore
 * de contenu derrière son titre. Pas de `cursor:pointer` sur un élément inerte.
 */
export function LearnScreen({ notation }: { notation: Notation }) {
  const set = LESSON_SETS[notation];
  return (
    <div className="mx-auto w-full max-w-[900px] px-8 py-8">
      <div className="moo-kicker mb-1.5">Apprendre · {NOTATION_LABEL[notation]}</div>
      <h1 className="mb-2 text-[34px]">{set.heading}</h1>
      <p className="mb-6 max-w-[620px] text-sm opacity-70">{set.intro}</p>

      <div className="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-0.5 bg-divider">
        {set.lessons.map((l) => (
          <article key={l.n} className="flex flex-col gap-2 bg-surface p-5">
            <div className="flex items-center gap-2.5">
              <span className="grid h-[30px] w-[30px] flex-none place-items-center bg-accent font-sans text-[13px] font-extrabold text-bg">
                {l.n}
              </span>
              <span className="font-sans text-[15px] font-extrabold">{l.title}</span>
            </div>
            <p className="m-0 text-[13px] leading-[1.55] opacity-70">{l.body}</p>
            <span className="mt-auto font-sans text-xs font-extrabold text-accent">{l.meta}</span>
          </article>
        ))}
      </div>

      <p className="mt-6 text-[13px] opacity-55">
        Les leçons sont en cours d&apos;écriture : les fiches détaillées ne sont pas encore
        disponibles.
      </p>
    </div>
  );
}
