import "./globals.css";
import type { Metadata } from "next";
import { Archivo, JetBrains_Mono } from "next/font/google";
import { TranscriptionsProvider } from "@/components/TranscriptionsProvider";
import { ScoreDraftProvider } from "@/components/ScoreDraftProvider";
import { ToastProvider } from "@/components/Toasts";
import { AppShell } from "@/components/AppShell";

/**
 * Archivo porte les titres ET le corps ; JetBrains Mono porte toute valeur
 * musicale (sol-fa, cellules d'édition, nuances, tempo, abréviations de voix).
 *
 * Le poids 800 est chargé explicitement : la maquette n'embarque qu'Archivo
 * 400, donc tous ses titres en 800 sont du faux-gras synthétisé par le
 * navigateur. Charger le vrai ExtraBold est une amélioration de fidélité.
 *
 * `next/font` télécharge les fichiers au BUILD et les sert depuis
 * /_next/static/media : aucun appel à fonts.googleapis.com au runtime, donc
 * rien à demander au visiteur (ni cookie, ni requête tierce).
 */
const archivo = Archivo({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "600", "800"],
  display: "swap",
  variable: "--font-archivo",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "600"],
  display: "swap",
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  title: "moozika",
  description: "Conversion de partitions sol-fa tonique ⇄ solfège",
};

/**
 * Les providers sont montés ICI et non dans une page : le layout survit aux
 * navigations, une page non. C'est ce qui permet à une transcription en cours
 * de continuer d'être suivie quand l'utilisateur va voir « À propos », et à une
 * partition importée non enregistrée de traverser la frontière de route.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={`${archivo.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen antialiased">
        <TranscriptionsProvider>
          <ScoreDraftProvider>
            <ToastProvider>
              <AppShell>{children}</AppShell>
            </ToastProvider>
          </ScoreDraftProvider>
        </TranscriptionsProvider>
      </body>
    </html>
  );
}
