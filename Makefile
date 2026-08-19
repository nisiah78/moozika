.PHONY: test test-audiveris test-front docker-test docker-up pdf-demo staff-demo \
        lint lint-py lint-php lint-front gate gate-report hooks

# Tests en local (cœur stdlib ; OCR skip si tesseract absent).
test:
	cd apps/omr-service && python3 -m unittest discover -s tests -v

# Tests dans Docker (rebuild pour prendre en compte OCR / deps système).
docker-test:
	docker compose build omr-test
	docker compose run --rm omr-test

# Lance stack complète (postgres, minio, api, omr, audiveris, frontend).
docker-up:
	docker compose up --build postgres minio minio-init api audiveris omr-service frontend

# Démonstration : lit le PDF d'exemple et écrit le MusicXML SATB.
pdf-demo:
	cd apps/omr-service && python3 -m app.pdf.cli ../../docs/jesoa-tsy-mba-mandao.pdf --out /tmp/jesoa.musicxml

# Démonstration portée : PDF solfège → MusicXML via Audiveris (Docker requis).
staff-demo:
	curl -sS -F "file=@docs/solfege/bpi-bp1340.pdf" http://localhost:8000/recognize | python3 -m json.tool | head -40

# --- Tests des autres stacks -----------------------------------------------
# audiveris-service : app/merge.py est stdlib pure → tourne en local, pas besoin
# de l'image Java (vérifié : 8 tests en 0.004 s).
test-audiveris:
	cd apps/audiveris-service && python3 -m unittest discover -s tests -t . -v

# frontend : les *.test.ts sont du node:assert pur, exécutés par tsx.
test-front:
	cd apps/frontend && npm test

# --- Qualité (Niveau 2 de la porte) ---------------------------------------
# pip est cassé en local → pylint vit dans l'image `omr-lint`.
lint-py:
	docker compose run --rm -T -w /app omr-lint pylint --rcfile=/app/.pylintrc app tests
	docker compose run --rm -T -w /audiveris omr-lint pylint --rcfile=/app/.pylintrc app tests

lint-php:
	cd apps/api && vendor/bin/phpstan analyse -c phpstan.dist.neon --no-progress
	cd apps/api && vendor/bin/php-cs-fixer check --config=.php-cs-fixer.dist.php --show-progress=none

lint-front:
	cd apps/frontend && npm run lint
	cd apps/frontend && npm run typecheck

lint: lint-py lint-php lint-front

# --- Porte pré-commit ------------------------------------------------------
# gate         : ce qui est INDEXÉ (git add) — bloque si Niveau 1 rouge.
# gate-report  : mesure tout le worktree modifié, ne bloque jamais.
gate:
	python3 scripts/quality/gate.py

gate-report:
	python3 scripts/quality/gate.py --all-files --report-only

# Active le hook pre-commit versionné (à lancer une fois par clone).
hooks:
	git config core.hooksPath scripts/hooks
	@echo "core.hooksPath = scripts/hooks"
