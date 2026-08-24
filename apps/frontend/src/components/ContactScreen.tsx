"use client";

import { useState } from "react";
import { buildContactMailto, CONTACT_ADDRESS } from "@/lib/contactMailto";
import { IconSend } from "@/components/icons";

export function ContactScreen() {
  const [from, setFrom] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");

  const canSend = message.trim().length > 0;

  return (
    <div className="mx-auto w-full max-w-[640px] px-8 py-8">
      <div className="moo-kicker mb-1.5">Contact</div>
      <h1 className="mb-2 text-[34px]">Me contacter</h1>
      <p className="mb-6 text-sm opacity-70">
        Une question, un bug de transcription, une partition qui ne passe pas ? Écrivez-moi.
      </p>

      <form
        className="flex flex-col gap-[18px]"
        onSubmit={(e) => {
          // `mailto:` ouvre le client mail : on laisse le navigateur suivre le
          // lien plutôt que de simuler un envoi côté app.
          e.preventDefault();
          window.location.href = buildContactMailto({ from, subject, message });
        }}
      >
        <div className="moo-field">
          <label htmlFor="contact-from">Adresse e-mail</label>
          <input
            id="contact-from"
            className="moo-input"
            type="email"
            placeholder="vous@exemple.com"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>
        <div className="moo-field">
          <label htmlFor="contact-subject">Sujet</label>
          <input
            id="contact-subject"
            className="moo-input"
            placeholder="Objet de votre message"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
        </div>
        <div className="moo-field">
          <label htmlFor="contact-message">Message</label>
          <textarea
            id="contact-message"
            className="moo-input min-h-[150px]"
            placeholder="Décrivez votre demande…"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
        </div>
        <div>
          <button type="submit" className="moo-btn moo-btn--primary gap-2" disabled={!canSend}>
            <IconSend size={15} />
            Envoyer le message
          </button>
          {/* Dit franchement ce que fait le bouton : il n'y a pas d'envoi
              serveur, et laisser croire le contraire ferait perdre des messages. */}
          <p className="mt-2.5 text-xs opacity-55">
            Le bouton ouvre votre logiciel de messagerie avec le message prérempli, à
            destination de <span className="font-mono">{CONTACT_ADDRESS}</span>. Rien n&apos;est
            envoyé depuis cette page.
          </p>
        </div>
      </form>
    </div>
  );
}
