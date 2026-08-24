/**
 * Construit l'URL `mailto:` du formulaire de contact.
 *
 * Pas d'envoi côté serveur : le périmètre convenu exclut tout changement
 * backend, et il n'y a ni endpoint de contact ni SMTP configuré. Ouvrir le
 * client mail de l'utilisateur est honnête ; simuler un envoi qui n'aboutit
 * nulle part ne le serait pas — l'interface le dit donc explicitement.
 */
export const CONTACT_ADDRESS = "nomena@novity.io";

export function buildContactMailto(input: {
  from: string;
  subject: string;
  message: string;
}): string {
  const subject = input.subject.trim() || "Message depuis moozika";
  // L'adresse saisie est reportée dans le corps : `mailto:` ne permet pas de
  // forcer un expéditeur, et le client mail utilisera le compte de la personne.
  const body = input.from.trim()
    ? `${input.message}\n\n—\nRépondre à : ${input.from.trim()}`
    : input.message;
  const qs = new URLSearchParams({ subject, body });
  // URLSearchParams encode l'espace en « + », que les clients mail
  // n'interprètent pas dans un corps de message : on repasse en %20.
  return `mailto:${CONTACT_ADDRESS}?${qs.toString().replace(/\+/g, "%20")}`;
}
