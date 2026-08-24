import type { Metadata } from "next";

export const metadata: Metadata = { title: "À propos — moozika" };

/** Composant serveur : texte statique, repris littéralement de la maquette. */
export default function AboutPage() {
  return (
    <div className="mx-auto w-full max-w-[720px] px-8 py-8">
      <div className="moo-kicker mb-1.5">À propos</div>
      <h1 className="mb-[18px] text-[38px] leading-[1.05]">
        moozika transcrit vos partitions, sol-fa comme solfège.
      </h1>
      <hr className="moo-hr" />
      <p className="text-[15px] leading-[1.7] opacity-85">
        moozika lit vos partitions au format PDF, image ou MusicXML et les convertit en
        notation lisible et jouable. La reconnaissance optique (OMR) tourne en tâche de
        fond&nbsp;: vous déposez un fichier, une notification vous prévient dès que la
        transcription est prête.
      </p>
      <p className="text-[15px] leading-[1.7] opacity-85">
        Chaque partition peut être consultée en <b>sol-fa</b> (notation tonic sol-fa,
        tradition malgache) ou en <b>solfège</b> sur portée, éditée note à note, annotée de
        nuances, puis réexportée fidèlement à l&apos;original.
      </p>

      <div className="mt-[26px] grid grid-cols-3 gap-0.5 bg-divider">
        {[
          { k: "2", v: "notations : sol-fa & solfège" },
          { k: "PDF · MXL", v: "formats d’import" },
          { k: "async", v: "transcription en tâche de fond" },
        ].map((s) => (
          <div key={s.k} className="bg-surface p-5">
            <div className="font-sans text-[26px] font-extrabold text-accent">{s.k}</div>
            <div className="mt-1 text-xs opacity-70">{s.v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
