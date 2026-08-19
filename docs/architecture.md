# Moozika — Architecture & Plan d'implémentation

> Document dérivé de [base_plan.md](base_plan.md), enrichi après clarification des points fonctionnels.
> **Pivot du système : MusicXML.** Tout gravite autour de ce format standard.

## 1. Décisions actées

| Sujet | Décision |
| --- | --- |
| Notations converties | **Portée classique ⇄ sol-fa tonique malgache** (mouvable-do : `d r m f s l t` + chiffres 1-7, notation des *fihirana*) |
| Sens d'import | **Les deux** : on reconnaît une portée **et** une feuille sol-fa |
| Moteur OMR (portée) | **Audiveris** (Java, encapsulé, sort du MusicXML) |
| Reconnaissance sol-fa | **Parseur/OCR sur-mesure** (aucun moteur existant) — composant à spiker |
| Périmètre v1 | Import + OMR + conversion + **playback** + **édition** |
| Format pivot | **MusicXML** (canonique, stocké) |
| Manipulation musicale | **music21** (Python) — voir §7 (écart assumé vs base_plan) |
| Auth / quotas / admin | Phase 2 (mais fondation `User` dès la Phase 0 — voir §11) |
| Stockage v1 (acté) | **PostgreSQL** + **MinIO** (MusicXML en objet) — pas MongoDB ; JSONB optionnel pour le snapshot UI (`ScoreModel`) |
| Auth app v1 | **Aucune** (bibliothèque globale locale) ; credentials MinIO/Postgres uniquement côté serveur |

### Conséquences structurantes

1. **L'asymétrie des deux sens.** `portée → MusicXML` est un problème quasi résolu (Audiveris). `sol-fa → MusicXML` n'a **aucun** outil sur étagère : le sol-fa tonique est du texte relatif à une tonique, pas des têtes de notes sur une portée. → pipeline dédié, risqué, à isoler.
2. **Le sol-fa tonique est *mouvable-do*** : relatif à la tonalité. Convertir portée→sol-fa exige l'armure (fournie par MusicXML ✅). Convertir sol-fa→portée exige que la feuille déclare la tonique (`Doh = F`).
3. **OSMD ne sait pas rendre le sol-fa tonique** → rendu sol-fa maison en plus.

---

## 2. Architecture globale

```mermaid
flowchart TD
    subgraph client["Frontend — Next.js"]
        UP["Upload PDF/Image"]
        VIEW["Viewer double mode<br/>OSMD portée + rendu sol-fa"]
        EDIT["Éditeur (modèle)"]
        PLAY["Playback Tone.js"]
    end

    subgraph api["API métier — Symfony 7 + API Platform"]
        AUTH["Auth / Quotas / Stockage"]
        ORCH["Orchestration<br/>Messenger + Redis"]
    end

    subgraph omr["Service reconnaissance — FastAPI"]
        PRE["Prétraitement OpenCV"]
        AUD["Audiveris — portée"]
        SOLFA["Parseur sol-fa — sur-mesure"]
        CONV["Conversion music21<br/>MusicXML ⇄ sol-fa"]
    end

    subgraph data["Données"]
        PG[("PostgreSQL")]
        S3[("MinIO / R2<br/>fichiers")]
        RDS[("Redis<br/>queue + cache")]
    end

    UP --> AUTH
    AUTH --> ORCH
    ORCH -->|"job HTTP interne"| PRE
    PRE --> AUD
    PRE --> SOLFA
    AUD --> CONV
    SOLFA --> CONV
    CONV -->|"MusicXML"| ORCH
    ORCH --> PG
    AUTH --> S3
    ORCH --> RDS
    PG --> VIEW
    S3 --> VIEW
    VIEW --> EDIT
    VIEW --> PLAY
```

**Règle d'or (héritée de base_plan) :** le navigateur ne parle **jamais** directement à Python. Symfony reste l'unique point d'entrée (auth, quotas, historique, audit).

---

## 3. Découpage en modules (frontières nettes)

```mermaid
flowchart LR
    M1["Module Reconnaissance<br/>Image/PDF → MusicXML"]
    M2["Module Conversion<br/>MusicXML ⇄ sol-fa tonique"]
    M3["Module Affichage<br/>portée + sol-fa"]
    M4["Module Édition<br/>modif. du modèle"]
    M5["Module Playback<br/>MusicXML → MIDI → piano"]
    M6["Module Export<br/>PDF/MusicXML/MIDI/audio"]
    M7["Module Compte<br/>auth/quotas/admin/paiement"]

    M1 --> PIVOT["MusicXML"]
    PIVOT --> M2 & M3 & M5 & M6
    M4 --> PIVOT
    M3 --> M4
    M7 -.gouverne.-> M1
```

Chaque module ne connaît que le pivot MusicXML → on peut remplacer/améliorer un composant sans toucher aux autres (ex. changer Audiveris pour un modèle ML plus tard).

| Module | App | Responsabilité | Ne fait PAS |
| --- | --- | --- | --- |
| Reconnaissance | omr (FastAPI) | Image/PDF → MusicXML (2 pipelines) | logique métier, quotas |
| Conversion | omr (FastAPI) | MusicXML ⇄ sol-fa (music21) | stockage, rendu |
| Affichage | frontend | Rendu portée (OSMD) + sol-fa (maison) | reconnaissance |
| Édition | frontend | Modifier le modèle → nouveau MusicXML | reconnaissance |
| Playback | frontend | MusicXML → MIDI → son piano | — |
| Export | api (Symfony) + omr | Générer les livrables | reconnaissance IA |
| Compte | api (Symfony) | Utilisateurs, quotas, plans, paiement | traitement IA |

---

## 4. Format pivot & modèle de domaine

- **Canonique et stocké : MusicXML.** Il porte note, durée, mesure, clé, armure, altérations, tempo, nuances.
- **Modèle interne de travail :** objets `music21` côté Python (calcul d'intervalles, degrés, tonalité).
- **Modèle sol-fa :** représentation intermédiaire propre (voir §6) car le sol-fa a des concepts que MusicXML n'exprime pas nativement (syllabes relatives, marques d'octave Curwen).

> Un `Score` = 1 œuvre. Il possède **plusieurs versions** (chaque édition/conversion crée une version), et **plusieurs assets** (MusicXML, MIDI, PDF, PNG, audio) référencés en stockage objet.

---

## 5. Pipeline de reconnaissance (les deux sens)

```mermaid
flowchart TD
    IN["Upload PDF / Image"] --> DET{"Type de document ?"}
    DET -->|auto ou choix utilisateur| ROUTE

    ROUTE --> P1
    ROUTE --> P2

    subgraph P1["Pipeline A — Portée (fiable)"]
        A1["PDF → images 300 dpi<br/>(pdf2image)"] --> A2["OpenCV : deskew,<br/>contraste, débruitage"]
        A2 --> A3["Audiveris (CLI/conteneur)"]
        A3 --> A4["MusicXML + score de confiance"]
    end

    subgraph P2["Pipeline B — Sol-fa tonique (risqué, sur-mesure)"]
        B1["OpenCV : segmentation<br/>lignes / colonnes / mesures"] --> B2["OCR texte (Tesseract)<br/>syllabes d r m f s l t / chiffres"]
        B2 --> B3["Parseur rythmique<br/>| : . , et marques d'octave"]
        B3 --> B4["Lecture tonique 'Doh = X'"]
        B4 --> B5["Reconstruction hauteurs<br/>(music21) → MusicXML"]
    end

    A4 --> OUT["MusicXML pivot"]
    B5 --> OUT
```

**Détection du type de document (`DET`)** : heuristique OpenCV (présence de portées à 5 lignes horizontales continues = portée ; densité de glyphes texte alignés en colonnes = sol-fa) + possibilité pour l'utilisateur de forcer le type à l'upload.

**Pourquoi le Pipeline B est dur (à cadrer avec toi) :** le sol-fa tonique malgache encode le rythme par la **position horizontale** et des séparateurs (`|` mesure, `:` temps, `.` prolongation, `,` demi-temps), l'octave par des marques Curwen (`d'`, `,d`) ou des points au-dessus/dessous des chiffres, et empile souvent 4 voix (SATB). → **MVP recommandé : un sous-ensemble défini** (une voix, format d'un recueil précis) avant de généraliser.

---

## 6. Module de conversion (bidirectionnel)

```mermaid
flowchart LR
    subgraph toSolfa["MusicXML → sol-fa tonique"]
        X1["Lire armure → tonique"] --> X2["Pour chaque note :<br/>degré relatif au do (music21)"]
        X2 --> X3["Degré → syllabe<br/>d r m f s l t (+ altérations : de, ra, fe, se…)"]
        X3 --> X4["Octave → marques Curwen"]
        X4 --> X5["Durées → mise en page<br/>rythmique sol-fa"]
    end

    subgraph toStaff["sol-fa tonique → MusicXML"]
        Y1["Lire 'Doh = X' → tonique"] --> Y2["Syllabe → degré → hauteur absolue"]
        Y2 --> Y3["Marques d'octave → n° d'octave"]
        Y3 --> Y4["Layout rythmique → durées"]
        Y4 --> Y5["Générer MusicXML<br/>(clé, armure, mesure)"]
    end
```

- **Déterministe** dans les deux sens une fois la tonique connue → testable unitairement (jeux de correspondances `degré ↔ syllabe`).
- **Altérations chromatiques** : gérées par les syllabes intermédiaires (`de/di`, `ra/ri`, `fe`, `se/si`, `ta/te`).
- **Point d'attention** : le sol-fa étant relatif, une même portée en Do majeur et en Sol majeur donne la **même** suite de syllabes ; la tonique est une métadonnée à conserver absolument sur le `Score`.

---

## 7. Écart assumé vs base_plan : conversion en Python, pas en PHP

base_plan proposait la conversion sol-fa en **PHP** (« le mapping est simple »). Je recommande de la mettre en **Python (music21)** :

- le calcul degré/intervalle/tonalité est natif dans music21, trivial et fiable ;
- la génération `sol-fa → MusicXML` partage la logique avec le **parseur du Pipeline B** (colocalisation) ;
- Symfony reste focalisé sur le **métier** (comptes, quotas, orchestration, stockage), là où il excelle.

> Symfony ne fait aucun traitement musical : il **orchestre**. C'est cohérent avec la règle « pas d'IA/OpenCV en PHP » de base_plan.

---

## 8. Affichage & édition

```mermaid
flowchart TD
    MXL["MusicXML"] --> STORE["Store client (React Query)"]
    STORE --> R1["Rendu portée<br/>OpenSheetMusicDisplay"]
    STORE --> R2["Rendu sol-fa tonique<br/>composant maison (HTML/canvas)"]
    STORE --> R3["Panneau d'édition"]
    R3 -->|"modif note :<br/>hauteur/durée/octave/altération"| STORE
    STORE -->|"sérialise"| MXL2["Nouveau MusicXML → version"]
```

- **Deux vues, une seule source de vérité** (le MusicXML en mémoire) → toujours synchronisées.
- **Édition v1 = niveau modèle** : sélectionner une note → modifier hauteur/durée/octave/altération via contrôles ; re-rendu OSMD + sol-fa. **Pas** de glisser-déposer libre en v1 (OSMD est un moteur de rendu, pas un éditeur → l'édition « type Flat.io » est lourde, reportée).
- Chaque sauvegarde d'édition = **nouvelle `score_version`** (historique/undo).

---

## 9. Playback

```mermaid
flowchart LR
    MXL["MusicXML"] --> MIDI["→ MIDI (music21 côté serveur ou conversion client)"]
    MIDI --> TONE["Tone.js"]
    SF["SoundFont piano<br/>Salamander / FluidR3"] --> TONE
    TONE --> AUDIO["Son piano réaliste"]
    VIEW["Curseur OSMD"] -. surlignage synchronisé .-> TONE
```

Web Audio seul sonne artificiel → **Tone.js + SoundFont** (Salamander). Surlignage de la note jouée via le curseur OSMD.

---

## 10. Flux asynchrone (upload → résultat)

```mermaid
sequenceDiagram
    participant C as Client (Next.js)
    participant S as Symfony API
    participant Q as Redis (Messenger)
    participant P as FastAPI (OMR)
    participant DB as PostgreSQL
    participant O as MinIO/R2

    C->>S: POST /scores (fichier + type)
    S->>S: vérifie quota + auth
    S->>O: stocke le fichier source
    S->>DB: crée Score + Job (status=queued)
    S-->>C: 202 { jobId, scoreId }
    S->>Q: dispatch RecognizeMessage
    Q->>P: POST /recognize (url fichier, type)
    P->>O: télécharge le fichier
    P->>P: prétraitement → Audiveris | parseur sol-fa
    P->>P: MusicXML (+ conversion sol-fa)
    P-->>S: { musicxml, confidence }
    S->>O: stocke asset MusicXML
    S->>DB: Job=done, Score prêt
    S-->>C: notification (Mercure/SSE ou polling)
    C->>S: GET /scores/{id}
    S-->>C: MusicXML + métadonnées
```

**Queue = Messenger + Redis** (suffisant, base_plan a raison). Temporal seulement quand le workflow s'allongera (correction IA, paroles, transposition, multi-export). Notification temps réel : **Mercure** (natif Symfony) ou polling simple en v1.

---

## 11. Comptes, quotas, admin (Phase 2 — avec réserve)

> Tu n'as **pas** coché ce bloc pour la v1. **Réserve importante :** « gérer les notes stockées **pour l'utilisateur** » et les quotas (5/25 par mois) impliquent une **identité**. Recommandation : créer l'entité `User` et un mode mono-utilisateur/dev dès la Phase 0, et repousser seulement le SSO/quotas/back-office/paiement.

- Auth : login/mdp + **Google SSO** (OIDC).
- Rôles : `USER`, `ADMIN` (back-office : gérer utilisateurs et plans).
- Quotas : compteur mensuel `quota_usage` décrémenté à chaque **conversion réussie** (5 gratuit / 25 payant), reset mensuel.
- Paiement : **Vanilla Pay** (Madagascar) — à confirmer ; interface `PaymentProvider` abstraite pour ne pas se coupler trop tôt.

---

## 12. Modèle de données

```mermaid
erDiagram
    USER ||--o{ SCORE : possede
    USER ||--o| SUBSCRIPTION : a
    USER ||--o{ QUOTA_USAGE : consomme
    SCORE ||--o{ SCORE_VERSION : historise
    SCORE ||--o{ JOB : declenche
    SCORE ||--o{ ASSET : contient
    SCORE_VERSION ||--o{ ASSET : produit
    SUBSCRIPTION ||--o{ PAYMENT : facture

    USER {
        uuid id
        string email
        string password_hash
        string google_sub
        string role
    }
    SCORE {
        uuid id
        uuid user_id
        string title
        string source_type "staff|solfa"
        string tonic "Doh = X"
        string status
    }
    SCORE_VERSION {
        uuid id
        uuid score_id
        int number
        string musicxml_asset_id
        string origin "omr|edit|conversion"
    }
    ASSET {
        uuid id
        string kind "source|musicxml|midi|pdf|png|audio"
        string storage_key
        string mime
    }
    JOB {
        uuid id
        uuid score_id
        string type "recognize|convert|export"
        string status "queued|running|done|failed"
        float confidence
        string error
    }
    SUBSCRIPTION {
        uuid id
        uuid user_id
        string plan "free|paid"
        int monthly_quota
    }
    QUOTA_USAGE {
        uuid id
        uuid user_id
        string period "YYYY-MM"
        int used
    }
    PAYMENT {
        uuid id
        string provider "vanillapay"
        string status
        int amount
    }
```

Fichiers en **stockage objet** (MinIO dev / R2 prod), jamais en base. La table `ASSET` référence les clés.

---

## 13. Structure monorepo & déploiement

Conforme à base_plan (monorepo, 3 apps indépendantes) :

```
moozika/
├── apps/
│   ├── frontend/            # Next.js + Tailwind + shadcn + OSMD + Tone.js
│   ├── api/                 # Symfony 7 + API Platform + Messenger + Doctrine
│   └── omr-service/         # FastAPI + OpenCV + music21 + Audiveris + Tesseract
├── packages/
│   └── shared-contracts/    # schémas d'API (OpenAPI) partagés
├── infra/                   # nginx/traefik, postgres, redis, minio
├── docker/                  # Dockerfiles par app
├── compose.yml
└── .github/workflows/       # CI : une image Docker par app
```

```mermaid
flowchart LR
    GH["GitHub push"] --> CI["CI GitHub Actions"]
    CI --> I1["frontend:tag"]
    CI --> I2["api:tag"]
    CI --> I3["omr:tag"]
    I1 & I2 & I3 --> COOL["Coolify"]
    COOL --> SRV["Serveur (Docker)"]
```

- `docker compose up` en dev démarre : frontend, api, omr, postgres, redis, minio, mailpit.
- Communication interne Symfony ⇄ FastAPI : **HTTP** (`POST /recognize`, `POST /convert`). Pas de gRPC avant d'avoir des milliers de req/min.
- **Attention Audiveris** : c'est du Java → l'image `omr-service` doit embarquer un JRE + Audiveris (ou un conteneur séparé `audiveris` appelé par le service). Alourdit l'image ; à valider en Phase 1.

---

## 14. Roadmap phasée

```mermaid
gantt
    title Roadmap Moozika
    dateFormat YYYY-MM-DD
    axisFormat %m/%y

    section Phase 0 — Fondations
    Monorepo + compose + CI          :p0a, 2026-07-22, 10d
    Entité User + squelette API      :p0b, after p0a, 7d
    Contrat MusicXML + schémas API   :p0c, after p0a, 7d

    section Phase 1 — Portée → sol-fa (chemin fiable)
    Audiveris intégré (spike image)  :p1a, after p0c, 10d
    Pipeline A + queue Messenger     :p1b, after p1a, 10d
    Conversion MusicXML→sol-fa       :p1c, after p1b, 10d
    Viewer OSMD + rendu sol-fa       :p1d, after p1b, 12d
    Playback Tone.js                 :p1e, after p1d, 8d

    section Phase 2 — Édition + inverse + export
    Édition niveau modèle            :p2a, after p1d, 12d
    Conversion sol-fa→MusicXML       :p2b, after p1c, 10d
    Export PDF/MIDI/MusicXML         :p2c, after p2a, 8d

    section Phase 3 — Reconnaissance sol-fa (risqué)
    SPIKE parseur sol-fa (sous-ensemble) :crit, p3a, after p2b, 15d
    Pipeline B intégré               :p3b, after p3a, 15d

    section Phase 4 — Comptes & business
    Auth login/mdp + Google SSO      :p4a, after p2c, 10d
    Quotas 5/25 + back-office admin  :p4b, after p4a, 12d
    Vanilla Pay (à confirmer)        :p4c, after p4b, 10d

    section Phase 5 — IA
    Transposition / analyse / erreurs :p5a, after p4b, 20d
```

**Logique de séquencement :** livrer d'abord le chemin **fiable** (portée→sol-fa, affichage, son), garder le composant **risqué** (reconnaissance sol-fa) pour un spike isolé en Phase 3 — pour ne pas bloquer tout le produit dessus.

---

## 15. Risques & recommandations

| Risque | Impact | Mitigation |
| --- | --- | --- |
| **Reconnaissance sol-fa** sans outil existant | Élevé | Spike Phase 3 sur un **sous-ensemble** (1 voix, format d'un recueil précis) ; option de repli : **saisie manuelle** du sol-fa au lieu d'OMR |
| Précision Audiveris sur partitions denses/scannées | Moyen | Bon prétraitement OpenCV ; afficher le **score de confiance** ; édition pour corriger |
| **Édition** interactive plus lourde que prévu | Moyen | v1 = édition **niveau modèle** (pas de drag libre) |
| Poids/complexité image Audiveris (Java dans service Python) | Moyen | Conteneur `audiveris` séparé, appelé en CLI/HTTP |
| SATB / multi-voix en sol-fa | Moyen | v1 monophonique/une voix, polyphonie plus tard |
| Vanilla Pay non spécifié | Faible (Phase 4) | Interface `PaymentProvider` abstraite |

---

## 16. Points encore ouverts (à trancher plus tard)

- Format(s) sol-fa cible(s) précis : **lettres** `d r m f s l t` (dialecte confirmé par l'échantillon), chromatismes en `-i`. Chiffres 1-7 à supporter ?
- ~~Recueil/gabarit de référence pour cadrer le Pipeline B~~ → **fait** : `docs/jesoa-tsy-mba-mandao.pdf` sert de référence. Le module `app/pdf` lit les PDF **typographiés** (ToUnicode) et bascule en **OCR** (OpenCV + Tesseract) pour les PDF/images **scannés**.
- ~~Changement de tonalité en cours de partition (modulation)~~ → **fait** : géré dans **les deux sens** (mouvable-do). Le marqueur `(Doh=X)` en tête de mesure est lu par le parseur sol-fa (`lexer`/`parser` : tonique effective par cellule, `key_tonic`/`key_fifths` sur la mesure) et écrit par `to_solfa` ; côté portée, `from_musicxml` reporte tout changement d'armure `<key>` sur la mesure (au lieu de le refuser). Le front réémet `(Doh=X)` dans la notation renvoyée au parseur. **Convention** : `doh_octave` unique pour toute la voix — la section modulée s'épelle dans le registre naturel du nouveau doh (le compositeur ajuste avec `'`/`,`). Le **mode** seul (même armure, ex. Do maj ↔ La min) ne change pas le doh (la-based).
- Monophonie vs polyphonie (SATB) pour la v1.
- Notification temps réel : Mercure vs polling.
- Confirmation Vanilla Pay + tarification du plan payant.
- Hébergement : Coolify auto-hébergé (le free tier dépend du serveur que tu fournis).
