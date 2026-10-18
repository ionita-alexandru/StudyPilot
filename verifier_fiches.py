"""Contrôle local des fiches éditoriales, des sources et de leur disponibilité."""
import json
from src.config import PROJECT_ROOT
from src.courses import service
from src.courses.card_presentation import publication_issue


def main():
    total, actual, errors = 0, {}, []
    for course in service.list_courses():
        reviewed = service._reviewed_collection(course)
        if reviewed is None:
            continue
        plan = service.load_course_plan(course)
        cards = {c['card_id']: c for part in plan['parts']
                 for c in service.load_part_cards(course, part['id'])}
        expected = {c.card_id for c in reviewed.cards}
        actual[course['course_id']] = expected
        if not expected <= cards.keys():
            errors.append(f"{course['title']} : fiche indisponible dans l’interface")
        if set(reviewed.questions) != expected:
            errors.append(f"{course['title']} : questions de révision incohérentes")
        for card in cards.values():
            if issue := publication_issue(card):
                errors.append(f"{card['title']} : {issue}")
        for cid, qa in reviewed.questions.items():
            if not qa.get('question', '').strip() or not qa.get('answer', '').strip():
                errors.append(f'{cid} : question ou réponse vide')
        total += len(cards)
        print(f"{course['title']} : {len(cards)} fiches disponibles, sources et révision vérifiées.")
    audit_path = PROJECT_ROOT / 'docs' / 'audit_fiches_2026-10-16.json'
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
        expected = {}
        for item in audit['cards']:
            if item['decision'] != 'fusionnée':
                expected.setdefault(item['course_id'], set()).add(item['card_id'])
        if actual != expected:
            errors.append('Les fiches disponibles ne correspondent pas au relevé éditorial.')
    if not actual:
        errors.append('Aucune collection éditoriale disponible.')
    if errors:
        print('\n'.join('ÉCHEC : ' + error for error in errors))
        return 1
    print(f'OK : {total} fiches éditoriales accessibles avec leurs pages sources et leurs questions.')
    print('Ce contrôle structurel ne remplace pas la relecture du contenu ni le contrôle du rendu LaTeX.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
