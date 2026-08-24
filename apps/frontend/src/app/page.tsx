import { redirect } from "next/navigation";
import { ROUTES } from "@/lib/navigation";

/** La racine n'a pas de contenu propre : la bibliothèque est l'écran d'accueil. */
export default function Home() {
  redirect(ROUTES.library());
}
