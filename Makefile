.PHONY: test docker-test docker-up pdf-demo staff-demo

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
