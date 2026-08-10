# frontend (Next.js)

Interface web de Moozika. Base v1 : bandeau titre **moozika**, import d'un
**PDF sol-fa**, puis affichage avec bascule **Portée (OSMD) ⇄ Sol-fa**.

## Structure

```
src/
  app/
    layout.tsx              # bandeau "moozika" + coquille
    page.tsx                # upload PDF + bascule + viewer
    globals.css
    api/pdf/parse/route.ts  # proxy serveur -> omr-service /pdf/parse
    api/pdf/parse/stream/   # proxy SSE -> omr-service /pdf/parse/stream
  components/
    Header.tsx
    ScoreViewer.tsx         # rendu OSMD (portée) ou sol-fa (texte)
    PlaybackControls.tsx    # lecture piano (Tone.js + Salamander)
  lib/
    types.ts                # types de la réponse omr-service
    playback.ts             # scheduling notes depuis le ScoreResult
```

Le navigateur appelle `/api/pdf/parse` (route Next), qui relaie vers le service
OMR (`OMR_SERVICE_URL`). Cette route passera par Symfony quand le backend
métier existera (cf. [docs/architecture.md](../../docs/architecture.md) §13).

## Démarrer

Il faut que **omr-service** tourne (voir `apps/omr-service`).

```bash
cp .env.example .env.local      # ajuster OMR_SERVICE_URL si besoin
npm install
npm run dev                     # http://localhost:3000
```

Puis importer un PDF sol-fa (ex. `docs/jesoa-tsy-mba-mandao.pdf`).

## Notes

- **Tailwind** pour le style ; shadcn/ui pourra être ajouté ensuite.
- **OSMD** est importé dynamiquement (client only) car il manipule le DOM.
- **Playback** : bouton Lecture → Tone.js + samples piano Salamander (CDN).
  Les notes sont lues depuis le modèle `ScoreResult` (pas une 2ᵉ conversion MIDI).
