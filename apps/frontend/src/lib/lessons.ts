import type { Notation } from "@/lib/navigation";

/**
 * Contenu pédagogique. Statique et côté front : décidé avec l'utilisateur
 * (périmètre « thème + écrans statiques », aucun changement backend).
 *
 * Les textes sont repris LITTÉRALEMENT de docs/Moozika.html. Aucune leçon n'a
 * encore de contenu détaillé derrière son titre — les cartes ne sont donc pas
 * cliquables (cf. LearnScreen) : une affordance qui ne mène nulle part est pire
 * qu'une absence d'affordance.
 */

export interface Lesson {
  n: string;
  title: string;
  body: string;
  meta: string;
}

export interface LessonSet {
  heading: string;
  intro: string;
  lessons: Lesson[];
}

export const LESSON_SETS: Record<Notation, LessonSet> = {
  solfa: {
    heading: "Apprendre le sol-fa",
    intro:
      "La notation tonic sol-fa note les degrés (d r m f s l t), les octaves par apostrophes " +
      "et virgules, et le rythme par les deux-points et barres.",
    lessons: [
      {
        n: "01",
        title: "Les sept degrés",
        body: "d r m f s l t : lire une gamme et repérer le Doh mobile.",
        meta: "6 min · débutant",
      },
      {
        n: "02",
        title: "Octaves : d’ et d̨",
        body: "Monter et descendre d’octave avec les apostrophes et virgules.",
        meta: "5 min",
      },
      {
        n: "03",
        title: "Le rythme en sol-fa",
        body: "Comprendre « : », « ! » et « . » pour découper temps et pulsations.",
        meta: "8 min",
      },
      {
        n: "04",
        title: "Plusieurs voix",
        body: "Lire une partition SATB alignée mesure par mesure.",
        meta: "10 min · intermédiaire",
      },
    ],
  },
  solfege: {
    heading: "Apprendre le solfège",
    intro:
      "Le solfège sur portée note les hauteurs par leur position sur les cinq lignes, " +
      "avec clé, armure et valeurs rythmiques.",
    lessons: [
      {
        n: "01",
        title: "La portée et les clés",
        body: "Placer les notes sur les lignes et interlignes en clé de sol.",
        meta: "6 min · débutant",
      },
      {
        n: "02",
        title: "Armure & tonalité",
        body: "Reconnaître dièses et bémols pour identifier la tonalité.",
        meta: "7 min",
      },
      {
        n: "03",
        title: "Valeurs rythmiques",
        body: "Rondes, blanches, noires, croches et leurs silences.",
        meta: "9 min",
      },
      {
        n: "04",
        title: "Du sol-fa au solfège",
        body: "Convertir une ligne sol-fa vers la portée et inversement.",
        meta: "10 min · intermédiaire",
      },
    ],
  },
};
