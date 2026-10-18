"""Projection de l'espace de fiches depuis le stockage canonique StudyPilot."""
from urllib.parse import quote
import re
from src.courses import service
from src.courses.card_presentation import render_text, prose, MATH

LABELS={'rule':'Règle','definition':'Définition','concept':'Concept','property':'Propriété','theorem':'Théorème','formula':'Formule','method':'Méthode','protocol':'Protocole','syntax':'Syntaxe','command':'Commande','example':'Exemple','remark':'Remarque'}


def card_summary(sections, title):
    """Aperçu court sans couper une formule ou afficher son code TeX brut."""
    for section in sections:
        content = section['content']
        if section['kind'] != 'text' or re.search(MATH, content):
            continue
        text = prose(content).strip()
        if not text or text == title:
            continue
        if len(text) > 180:
            text = text[:177].rsplit(' ', 1)[0] + '…'
        return text
    # Les exemples peuvent conclure en prose après une longue matrice :
    # privilégier cette conclusion à une matrice miniature ou défilante.
    display_math = r'\\\[[\s\S]*?\\\]|\$\$[\s\S]*?\$\$'
    for section in sections:
        if section['kind'] != 'text' or not re.search(display_math, section['content']):
            continue
        tail = re.split(display_math, section['content'])[-1].strip()
        if (tail[:1].isupper() and 6 <= len(tail.split()) and len(tail) <= 220
                and not tail.startswith('Cette précision complète')):
            return tail
    for section in sections:
        if section['kind'] == 'text':
            match = re.search(display_math, section['content'])
            if match and len(match.group()) <= 220:
                return match.group()
    for section in sections:
        if section['kind'] == 'text':
            match = re.search(MATH, section['content'])
            if match and len(match.group()) <= 220:
                return match.group()
    return title

def presentation_data():
    data=[]
    for course in service.list_courses():
        plan=service.load_course_plan(course)
        if not plan:continue
        reviewed=service._reviewed_collection(course)
        seen=set();cards=[];pending=False
        for part in plan['parts']:
            pending = pending or bool(service.load_part_unavailable(course, str(part['id'])))
            for item in service.load_part_cards(course,str(part['id'])):
                if item['card_id'] in seen:continue
                seen.add(item['card_id'])
                sections=[]
                for sec in item['sections']:
                    content=sec['content'];kind='text'
                    if content.startswith('```'):
                        header,_,body=content.partition('\n');content=body.rsplit('```',1)[0].rstrip();kind='math' if header=='```text' else 'code'
                    elif all(line[:1].isdigit() for line in content.splitlines() if line.strip()):
                        kind='steps';content='\n'.join(re.sub(r'^\d+[.)]\s*','',line) for line in content.splitlines())
                    sections.append(dict(title=sec['title'],kind=kind,content=content,html=render_text(sec['content'])))
                qa=reviewed.questions.get(item['card_id'],{}) if reviewed and not item.get('compact') else {}
                meaningful=[s for s in sections if not s['content'].startswith('Le passage original est conservé ci-dessous')]
                first=card_summary(meaningful,item['title'])
                if item.get('compact'):
                    # Garder une phrase entière et ses symboles, jamais un λ isolé.
                    lead = re.split(r'\\\[|\$\$|```|\n\n', item['sections'][0]['content'], maxsplit=1)[0].strip()
                    if len(lead) > 350:
                        # Couper sur une fin de phrase hors formule, sans tronquer TeX.
                        protected = {}
                        def protect(match):
                            key = f'ZZMATH{len(protected)}ZZ'
                            protected[key] = match.group()
                            return key
                        plain = re.sub(MATH, protect, lead)
                        lead = re.split(r'(?<=[.!?])\s+', plain, maxsplit=1)[0]
                        for key, value in protected.items():
                            lead = lead.replace(key, value)
                    first = lead if lead else item.get('objective', item['title'])
                answer='\n\n'.join(s['title']+'\n'+s['content'] for s in meaningful)
                cards.append(dict(id=item['card_id'],title=item['title'],type=LABELS.get(item['concept_type'],item['concept_type']),provenance=item.get('review_provenance'),pages=item['source_pages'],summary=first,summary_html=render_text(first),sections=sections,question=qa.get('question','Que faut-il retenir de « '+item['title']+' » ?'),answer=qa.get('answer',answer),answer_html=render_text(qa.get('answer',answer)),part_number=part['number'], resources=item.get('resources', []), aliases=item.get('aliases', []), compact=item.get('compact', False)))
        cid=course['course_id']
        count=len(plan['parts'])
        from src.courses.study_guide import load_guide, resource_view
        guide = load_guide(course, plan)
        resources = [resource_view(e, guide) for e in guide['entries'] if e['role'] != 'core'] if guide else []
        part_numbers = {p['id']: p['number'] for p in plan['parts']}
        for resource in resources:
            resource['part_number'] = part_numbers[resource['part_id']]
        data.append(dict(id=cid,title=course['title'],subtitle=f"{count} {'partie' if count == 1 else 'parties'} · cours StudyPilot",tag='Cours',color='#7065e9',pending=pending or (not cards and not guide),pdf='/pdf/'+quote(course['source_filename']),source_prefix='/course/'+cid+'/source-page/',course_url='/course/'+cid,revision_url='/revision?course_id='+quote(cid),cards=cards,resources=resources))
    return data
