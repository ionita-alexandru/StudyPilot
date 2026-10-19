from pathlib import Path

from flask import Flask, Response, jsonify, redirect, render_template, request, send_from_directory, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from src.ai.client import AIUnavailableError, AIUsageLimitError
from src.revision_service import revision_course_data

from src.config import COURSE_PDF_DIR, STUDY_MODEL
from src.courses import service as course_service
from src.part_study import (
    answer_part_question,
    build_course_outline_context,
    is_course_overview_question,
    normalize_chat_history,
    retrieve_pdf_contexts,
    select_part,
)
from src.storage.repository import StorageError
from src.upload_service import MAX_PDF_BYTES, UploadError, enqueue_pdf, job_status, resume_job
from src.courses.overview import overview_view
from src.courses.card_presentation import render_text


app = Flask(__name__)
app.add_template_filter(overview_view, 'overview_view')
CARD_TYPE_LABELS = {
    "rule": "Règle",
    "definition": "Définition",
    "concept": "Concept",
    "property": "Propriété",
    "theorem": "Théorème",
    "formula": "Formule",
    "method": "Méthode",
    "protocol": "Protocole",
    "syntax": "Syntaxe",
    "command": "Commande",
    "example": "Exemple",
    "remark": "Remarque",
}


@app.template_filter("card_type_label")
def card_type_label(value: str) -> str:
    key = str(value or "").strip().lower()
    return CARD_TYPE_LABELS.get(key, key.capitalize())

app.config["MAX_CONTENT_LENGTH"] = MAX_PDF_BYTES + 256 * 1024


def _load_course_and_plan(course_id: str) -> tuple[dict, dict | None]:
    course = course_service.load_course(course_id)
    return course, course_service.load_course_plan(course)


@app.get("/")
def index():
    return render_template("index.html", courses=course_service.list_courses())


@app.get("/course/<course_id>")
def course(course_id: str):
    """Parcours du cours ; une question explicite ouvre directement le chat."""
    try:
        course_data, plan = _load_course_and_plan(course_id)

    except ValueError:
        return "Identifiant de cours invalide.", 400

    except FileNotFoundError:
        return "Cours introuvable.", 404

    except StorageError as error:
        return f"Impossible de charger ce cours : {error}", 500


    if plan is None:
        return "Plan du cours indisponible.", 409


    parts = plan.get("parts") or []

    if not parts:
        return "Ce cours ne contient aucune partie.", 409


    first_part = parts[0]

    part_number = str(
        first_part.get("number") or ""
    ).strip()

    if not part_number:
        return "Première partie invalide.", 409


    question = request.args.get(
        "q",
        "",
    ).strip()


    if not question:
        from src.learning_view import learning_view
        return render_template('course.html', course=course_data, plan=plan,
            learning=learning_view(course_data, plan), pdf_url=url_for('course_pdf',filename=course_data['source_filename']))
    return redirect(
        url_for(
            "part",
            course_id=course_data["course_id"],
            part_number=part_number,
            **({"q": question} if question else {}),
        )
    )


@app.get('/course/<course_id>/discover')
def discover(course_id):
    from src.learning_view import learning_view
    try:
        data, plan = _load_course_and_plan(course_id)
        if not plan:
            return 'Plan indisponible.', 409
        learning = learning_view(data, plan)
        entries = learning['entries']
        selected = request.args.get('card')
        position = next((i for i,e in enumerate(entries) if e['id']==selected), 0)
        if selected and (not entries or entries[position]['id'] != selected):
            return 'Notion introuvable.', 404
        return render_template('discover.html',course=data,plan=plan,learning=learning,position=position,
            entry=entries[position] if entries else None,pdf_url=url_for('course_pdf',filename=data['source_filename']))
    except (ValueError, FileNotFoundError, StorageError):
        return 'Cours introuvable.',404


@app.post('/api/study-feedback')
def study_feedback():
    from src.courses.study_guide import load_guide
    from src.storage.repository import write_json_atomic
    import uuid
    from datetime import datetime, timezone
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload,dict) or not isinstance(payload.get('comment'),str) or not 5 <= len(payload['comment'].strip()) <= 2000:
        return jsonify(error='Décris le problème en 5 à 2 000 caractères.'),400
    try:
        data, plan = _load_course_and_plan(payload.get('course_id'))
        guide = load_guide(data,plan)
        entry = next((e for e in (guide or {}).get('entries',[]) if e['id']==payload.get('card_id')),None)
        if not entry:
            return jsonify(error='Fiche introuvable.'),404
        root = course_service._repository().paths(data['course_id']).root
        report = dict(id=str(uuid.uuid4()),card_id=entry['id'],revision=guide['revision'],source_ids=entry['source_ids'],
            comment=payload['comment'].strip(),created_at=datetime.now(timezone.utc).isoformat(),status='open')
        write_json_atomic(root/'feedback'/(report['id']+'.json'),report)
        return jsonify(message='Signalement enregistré localement avec la version de la fiche. Il reste à examiner ; le contenu n’a pas été corrigé automatiquement.')
    except (ValueError,FileNotFoundError,StorageError):
        return jsonify(error='Impossible d’enregistrer ce signalement.'),400


@app.get("/course/<course_id>/part/<part_number>")
def part(course_id: str, part_number: str):
    """Affiche une partie du plan avec son aperçu et le chat contextuel."""
    try:
        course_data, plan = _load_course_and_plan(course_id)
    except ValueError:
        return "Identifiant de cours invalide.", 400
    except FileNotFoundError:
        return "Cours introuvable.", 404

    if plan is None:
        return "Plan du cours indisponible.", 409
    selected = select_part(plan, part_number)
    if selected is None:
        return "Partie introuvable.", 404

    part_id = str(selected.get("id") or "").strip()

    cards = (
       course_service.load_part_cards(
           course_data,
           part_id,
        )
        if part_id
        else []
    )

    pdf_name = course_data["source_filename"]
    return render_template(
    "part.html",
    course=course_data,
    courses=course_service.list_courses(),
    plan=plan,
    part=selected,
    cards=cards,
    unavailable_cards=course_service.load_part_unavailable(course_data, part_id) if part_id else [],
    ignored_mentions=course_service.load_part_ignored(course_data, part_id) if part_id else [],
    pdf_url=url_for("course_pdf", filename=pdf_name),
)


@app.get('/api/conversation/<course_id>/<identifier>')
def restore_conversation(course_id, identifier):
    from src.tutor import restore
    try:
        data, plan = _load_course_and_plan(course_id)
        if not plan:
            return jsonify(error='Plan indisponible.'), 409
        return jsonify(restore(data, plan, identifier))
    except (ValueError, FileNotFoundError, StorageError):
        return jsonify(error='Conversation indisponible.'), 404
    except RuntimeError:
        return jsonify(error='Une réponse est déjà en cours.'), 409


@app.post("/api/part-chat")
def part_chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Requête invalide."}), 400

    course_id = payload.get("course_id")
    part_number = payload.get("part_number")
    question = payload.get("question")
    if (
        not all(isinstance(value, str) and value.strip() for value in (course_id, part_number, question))
        or len(question) > 1000
        or len(part_number) > 40
    ):
        return jsonify({"error": "Paramètres invalides."}), 400

    try:
        course_data, plan = _load_course_and_plan(course_id)
    except (ValueError, FileNotFoundError, StorageError):
        return jsonify({"error": "Cours introuvable."}), 404
    if plan is None:
        return jsonify({"error": "Plan du cours indisponible."}), 409

    selected = select_part(plan, part_number)
    if selected is None:
        return jsonify({"error": "Partie introuvable."}), 404

    history = normalize_chat_history(payload.get("history"))
    clean_question = question.strip()
    course_title = str(course_data.get("title") or "Cours sans titre")
    whole_course = is_course_overview_question(clean_question, history)
    course_outline = build_course_outline_context(plan)

    pdf_path = COURSE_PDF_DIR / course_data["source_filename"]
    model = STUDY_MODEL
    if payload.get('contextual') or payload.get('card_id') or payload.get('conversation_id'):
        from src.tutor import answer as tutor_answer
        try:
            result = tutor_answer(course_data, plan, selected, clean_question,
                card_id=payload.get('card_id'), conversation_id=payload.get('conversation_id'),
                intent=payload.get('intent', 'question'), model=model)
            return jsonify(result)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except RuntimeError as error:
            if str(error).startswith('Une réponse est déjà'):
                return jsonify(error=str(error)), 409
            if isinstance(error, (AIUnavailableError, AIUsageLimitError)):
                return jsonify(error=str(error)), 503
            app.logger.exception('Erreur du tutorat contextuel')
            return jsonify(error='Réponse interrompue. Tu peux réessayer, ton cours est conservé.'), 503
        except Exception:
            app.logger.exception('Erreur du tutorat contextuel')
            return jsonify(error='Réponse momentanément indisponible.'), 503
    try:
        if whole_course:
            contexts = []
        else:
            contexts = retrieve_pdf_contexts(
                pdf_path,
                selected,
                clean_question,
                course_title,
                expand_terms=None,
            )

        answer = answer_part_question(
            clean_question,
            contexts,
            model,
            course_title=course_title,
            part=selected,
            course_outline=course_outline,
            history=history,
            course_overview=whole_course,
        )
    except (AIUnavailableError, AIUsageLimitError) as error:
        return jsonify({'error': str(error)}), 503
    except Exception:
        app.logger.exception("Erreur du chat StudyPilot")
        return jsonify({"error": "StudyPilot est momentanément indisponible."}), 503

    return jsonify(
        {
            "answer": answer,
            "answer_html": render_text(answer),
            "pages": sorted({context["page"] for context in contexts}),
            "scope": "course_overview" if whole_course else "pdf_and_knowledge",
        }
    )


@app.get("/pdf/<path:filename>")
def course_pdf(filename: str):
    if Path(filename).name != filename or not filename.lower().endswith(".pdf"):
        return "Nom de fichier invalide.", 400
    if not (COURSE_PDF_DIR / filename).is_file():
        return "PDF introuvable.", 404
    return send_from_directory(COURSE_PDF_DIR.resolve(), filename, mimetype="application/pdf")


@app.get("/upload")
def upload_page():
    return render_template("upload.html")


@app.get("/course/<course_id>/card/<card_id>/illustration/<int:index>")
def card_illustration(course_id, card_id, index):
    from src.courses.illustrations import render_card_illustration
    try:
        png = render_card_illustration(course_id, card_id, index)
    except (FileNotFoundError, StorageError):
        return "Illustration introuvable.", 404
    except ValueError:
        return "La source de cette illustration a changé.", 409
    return Response(png, mimetype="image/png", headers={"Cache-Control": "private, no-cache"})


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(error):
    if request.path == "/api/upload":
        return jsonify({"error": "Le PDF dépasse la limite de 20 Mo."}), 413
    return "Fichier trop volumineux.", 413


@app.post("/api/upload")
def upload_pdf():
    incoming = request.files.get("pdf")
    if incoming is None or not incoming.filename:
        return jsonify({"error": "Sélectionne un fichier PDF."}), 400
    try:
        job_id = enqueue_pdf(incoming.stream, incoming.filename)
    except UploadError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        app.logger.exception("Échec d'enregistrement du fichier PDF")
        return jsonify({"error": "Impossible d'enregistrer le PDF."}), 500
    return jsonify({"job_id": job_id, "status_url": url_for("upload_status", job_id=job_id)}), 202


@app.get("/api/upload/status/<job_id>")
def upload_status(job_id: str):
    status = job_status(job_id)
    if status is None:
        return jsonify({"error": "Import introuvable."}), 404
    if status["status"] in ("ready", "partial", "interrupted", "error") and status.get("course_id"):
        try:
            saved_course = course_service.load_course(status['course_id'])
            if course_service.load_course_plan(saved_course):
                status["course_url"] = url_for("course", course_id=status["course_id"])
        except (FileNotFoundError, ValueError, StorageError):
            pass
    if status['status'] in {'partial', 'interrupted', 'error'}:
        status['resume_url'] = url_for('resume_upload', job_id=job_id)
    return jsonify(status)


@app.post('/api/upload/resume/<job_id>')
def resume_upload(job_id: str):
    try:
        resume_job(job_id)
    except UploadError as error:
        return jsonify(error=str(error)), 409
    return jsonify(status_url=url_for('upload_status', job_id=job_id)), 202

@app.get("/api/revision")
def revision_data():
    course_id = str(
        request.args.get("course_id") or ""
    ).strip()

    part_number = str(
        request.args.get("part_number") or ""
    ).strip()


    if not course_id:
        return jsonify(
            {
                "error": "Cours manquant."
            }
        ), 400


    try:
        data = revision_course_data(
            course_id,
            part_number or None,
        )

    except ValueError as error:
        return jsonify(
            {
                "error": str(error)
            }
        ), 400

    except (
        FileNotFoundError,
        StorageError,
    ):
        return jsonify(
            {
                "error": "Cours introuvable."
            }
        ), 404


    return jsonify(data)

@app.get("/revision")
def revision_page():
    courses = course_service.list_courses()
    selected = next((c for c in courses if c['course_id'] == request.args.get('course_id')), None)
    return render_template(
        "revision.html",
        courses=courses,
        course=selected or (courses[0] if courses else None),
    )


@app.get('/presentation')
def presentation():
    return render_template('presentation.html')

@app.get('/api/presentation')
def presentation_api():
    from src.presentation import presentation_data
    return jsonify(presentation_data())

@app.get('/course/<course_id>/source-page/<int:page>')
def source_page(course_id, page):
    import fitz
    try:
        course_data = course_service.load_course(course_id)
        if not 1 <= page <= course_data['page_count']:
            return 'Page introuvable.', 404
        pdf = COURSE_PDF_DIR / course_data['source_filename']
        if pdf.parent.resolve() != COURSE_PDF_DIR.resolve():
            return 'Source invalide.', 400
        with fitz.open(pdf) as document:
            pix = document[page-1].get_pixmap(matrix=fitz.Matrix(1.5,1.5), alpha=False)
            return Response(pix.tobytes('png'), mimetype='image/png')
    except (ValueError, FileNotFoundError, StorageError):
        return 'Source introuvable.', 404

if __name__ == "__main__":
    from src.console import configure_console
    configure_console()
    from src.upload_service import restore_jobs
    restore_jobs()
    # Les traitements actifs après redémarrage demandent une reprise explicite.
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
