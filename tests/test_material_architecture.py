"""Régressions structurelles v15, modèle contrôlé et stockage réel isolé.

Les réponses simulées permettent d'injecter des décisions contradictoires, des
pannes et de mauvaises associations. Elles ne mesurent pas la qualité d'Ollama.
Les tests de PDF complémentaires emploient les trois documents fournis.
"""
import json
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.courses import pedagogy, learning_material, cards, service
from src.courses.card_presentation import publication_view, present_card
from src.models.card import CardCollection, StudyCard
from src.storage.course_repository import CourseRepository
from test_pedagogy import FakeModel, MODEL, SHA, PLAN, fact, inventory, notion, page


def payload(kw):
    return json.loads(kw['messages'][-1]['content'].split('\nRéponse précédente rejetée : ')[0])


class MaterialArchitectureTests(unittest.TestCase):
    def prepare(self, concepts, pages, reply, folder, plan=PLAN):
        with patch.object(pedagogy, 'chat_json', side_effect=reply):
            return pedagogy.prepare_material(inventory(*concepts), dict(file_hash=SHA, pages=pages),
                plan, CourseRepository(Path(folder)), model=MODEL)

    def test_autonomy_is_decided_without_any_target_catalogue(self):
        text = 'Un polynôme trigonométrique est une combinaison linéaire finie de sinus et de cosinus.'
        c = notion('poly', 'Polynôme trigonométrique', text)
        fake = FakeModel({1: [fact(text)]})
        with TemporaryDirectory() as folder:
            result = self.prepare([c], [page(1, text)], fake, folder)
        self.assertFalse(result.issues)
        self.assertEqual([x.concept_id for x in result.inventory.concepts], ['poly'])
        requests = [p for name,p in fake.calls if name == 'ContentAssessment']
        self.assertEqual(len(requests), 1)
        self.assertNotIn('possible_targets', requests[0])
        self.assertFalse(any(name == 'GroupProposal' for name,_ in fake.calls))

    def test_label_wrongly_typed_as_explanation_is_ignored_with_trace(self):
        c = notion('logo', 'Logo', 'Logo')
        fake = FakeModel({1:[fact('Logo', 'explanation')]}, {'logo':('mention',None)})
        with TemporaryDirectory() as folder:
            result = self.prepare([c], [page(1,'Logo')], fake, folder)
            state = json.loads(CourseRepository(Path(folder)).paths('cours-test').root.joinpath('pedagogy.json').read_text())
        self.assertFalse(result.issues)
        self.assertEqual(result.inventory.concepts[0].relevance,'mention_only')
        review = state['content_reviews']['logo']
        self.assertEqual(review['assessment']['teaching_check']['disposition'],'name_only')
        self.assertTrue(review['recovery']['searched_sources'])
        self.assertEqual(state['decisions']['logo']['decision']['action'],'mention')

    def test_behavior_is_retained_even_when_first_pass_calls_it_mention(self):
        text = 'Browsers automatically add a border to image links.'
        c = notion('border', 'Bordure des liens images', text)
        fake = FakeModel({1:[fact(text, 'mention')]}, {'border':('mention',None)})
        with TemporaryDirectory() as folder:
            result = self.prepare([c], [page(1,text)], fake, folder)
        self.assertFalse(result.issues)
        self.assertEqual(result.inventory.concepts[0].relevance,'active')
        self.assertEqual(result.inventory.concepts[0].learning_points[0].quote,text)

    def test_mutual_duplicate_requests_produce_one_stable_root_with_both_origins(self):
        text = 'Les coefficients se calculent par intégration sur une période.'
        a = notion('a', 'Calcul des coefficients', text)
        b = notion('b', 'Coefficients de la série', text)
        fake = FakeModel({1:[fact(text,ids=['c1','c2'])]}, {'a':('merge','b'), 'b':('merge','a')})
        fake.target_titles = {'a':a.title,'b':b.title}
        with TemporaryDirectory() as folder:
            result = self.prepare([a,b], [page(1,text)], fake, folder)
        self.assertFalse(result.issues)
        self.assertEqual([c.concept_id for c in result.inventory.concepts],['a'])
        self.assertEqual([(r['concept_id'],r['target_id']) for r in result.relations],[('b','a')])
        self.assertEqual(result.relations[0]['grounding']['relation'],'same_notion')
        self.assertEqual(len(result.inventory.concepts[0].learning_points),1)

    def test_refused_merge_keeps_independently_valid_teaching_and_rejection_trace(self):
        a = notion('a'); b = notion('b','Noyau','Le noyau contient du matériel génétique.')
        text = a.evidence[0].excerpt+'\n'+b.evidence[0].excerpt
        fake = FakeModel({1:[fact(a.evidence[0].excerpt),fact(b.evidence[0].excerpt,ids=['c2'])]}, {'b':('merge','a')})
        fake.target_titles={'a':a.title};fake.links_supported=False
        with TemporaryDirectory() as folder:
            result=self.prepare([a,b],[page(1,text)],fake,folder)
            state=json.loads(CourseRepository(Path(folder)).paths('cours-test').root.joinpath('pedagogy.json').read_text())
            fake.calls.clear();again=self.prepare([a,b],[page(1,text)],fake,folder)
            self.assertFalse(fake.calls)
        self.assertEqual(result,again);self.assertFalse(result.issues)
        self.assertEqual(len(result.inventory.concepts),2);self.assertFalse(result.relations)
        self.assertIn('Rattachement non justifié',state['group_reviews']['b']['last_error'])

    def test_supporting_content_only_sees_autonomous_roots(self):
        texts=['La fonction lire charge le fichier demandé en mémoire.','out = lire(fichier)','print(out)']
        cs=[notion(key,title,text) for key,title,text in zip(['a','b','c'],['Lire un fichier','Exemple de lecture','Afficher le résultat'],texts)]
        fake=FakeModel({1:[fact(t, 'explanation' if i==0 else 'example', ids=[f'c{i+1}']) for i,t in enumerate(texts)]},
            {'b':('attach','a'),'c':('attach','b')})
        fake.target_titles={c.concept_id:c.title for c in cs}
        with TemporaryDirectory() as folder:
            result=self.prepare(cs,[page(1,'\n'.join(texts))],fake,folder)
        requests=[p for n,p in fake.calls if n=='GroupProposal']
        self.assertTrue(all([t['title'] for t in p['possible_targets']]==['Lire un fichier'] for p in requests))
        self.assertEqual([(r['concept_id'],r['target_id']) for r in result.relations],[('b','a')])
        self.assertEqual(result.issues[0]['concept_id'],'c')

    def test_recovery_selects_exact_continuation_and_is_not_repeated(self):
        first='La méthode comporte deux phases.';next_text='On mesure la durée.\nPuis on calcule la moyenne des mesures.'
        c=notion('measure','Mesurer une durée',first)
        fake=FakeModel({1:[fact(first)],2:[]})
        def reply(**kw):
            name=kw['response_model'].__name__;data=payload(kw)
            if name=='ContentAssessment':
                raw=fake(**kw)
                if len(data['points'])==1:raw.update(disposition='incomplete',missing_information=['Deux phases annoncées'])
                return raw
            if name=='EvidenceRecovery':
                fake.calls.append((name,data));unit=next(s for s in data['sources'] if s['page']==2)
                return dict(selections=[dict(source_ref=unit['ref'],start_line=1,end_line=2,kind='steps')],reason='Continuation sur la page suivante.')
            if name=='EvidenceScope':return dict(verdict='about_this_notion',reason='Les phases poursuivent explicitement la méthode.')
            return fake(**kw)
        with TemporaryDirectory() as folder:
            result=self.prepare([c],[page(1,first),page(2,next_text)],reply,folder)
            before=len(fake.calls);again=self.prepare([c],[page(1,first),page(2,next_text)],reply,folder)
            self.assertEqual(len(fake.calls),before)
        self.assertEqual(result,again);self.assertFalse(result.issues)
        self.assertEqual(result.inventory.concepts[0].source_pages,[1,2])
        self.assertEqual(result.inventory.concepts[0].learning_points[-1].quote,next_text)

    def test_recovery_rejects_a_neighbor_example_and_remains_bounded(self):
        c=notion(text='La cellule.'); fake=FakeModel({1:[fact('La cellule.')],2:[]},{'cellule':('uncertain',None)})
        counts={'recovery':0,'scope':0}
        def reply(**kw):
            name=kw['response_model'].__name__;data=payload(kw)
            if name=='EvidenceRecovery':
                counts['recovery']+=1;u=next(s for s in data['sources'] if s['page']==2)
                return dict(selections=[dict(source_ref=u['ref'],start_line=1,end_line=1,kind='example')],reason='Association erronée injectée.')
            if name=='EvidenceScope':
                counts['scope']+=1;return dict(verdict='other_notion',reason='Ce passage définit un triangle.')
            return fake(**kw)
        with TemporaryDirectory() as folder:
            result=self.prepare([c],[page(1,'La cellule.'),page(2,'Un triangle possède trois côtés.')],reply,folder)
            state=json.loads(CourseRepository(Path(folder)).paths('cours-test').root.joinpath('pedagogy.json').read_text())
        self.assertFalse(result.inventory.concepts);self.assertEqual(len(result.issues),1)
        self.assertEqual(result.issues[0]['status'],'source_insufficient')
        rejected=state['content_reviews']['cellule']['recovery']['rejected']
        self.assertEqual(rejected[0]['verdict'],'other_notion')
        self.assertEqual(counts,dict(recovery=1,scope=1))

    def test_insufficient_source_is_saved_without_regeneration_loop(self):
        text='Théorème : conclusion absente.';c=notion(text=text)
        fake=FakeModel({1:[fact(text)]},{'cellule':('uncertain',None)})
        with TemporaryDirectory() as folder:
            result=self.prepare([c],[page(1,text)],fake,folder)
            count=len(fake.calls);again=self.prepare([c],[page(1,text)],fake,folder)
            self.assertEqual(len(fake.calls),count)
        self.assertEqual(result,again);self.assertEqual(result.issues[0]['status'],'source_insufficient')

    def test_recovery_checkpoint_survives_interruption_before_reassessment(self):
        text='Une mesure utilise deux phases.';extra='On observe, puis on note la durée.';c=notion(text=text)
        fake=FakeModel({1:[fact(text)],2:[]},{'cellule':('uncertain',None)})
        stopped=[False];counts={'recovery':0}
        def reply(**kw):
            data=payload(kw);name=kw['response_model'].__name__
            if name=='EvidenceRecovery':
                counts['recovery']+=1;u=next(s for s in data['sources'] if s['page']==2)
                return dict(selections=[dict(source_ref=u['ref'],start_line=1,end_line=1,kind='steps')],reason='Phases retrouvées.')
            if name=='EvidenceScope':return dict(verdict='about_this_notion',reason='Continuation explicite.')
            if name=='ContentAssessment' and len(data['points'])>1:
                if not stopped[0]:stopped[0]=True;raise KeyboardInterrupt()
                return dict(disposition='developed',concept_type='method',reason='Phases présentes.')
            return fake(**kw)
        with TemporaryDirectory() as folder:
            with self.assertRaises(KeyboardInterrupt):self.prepare([c],[page(1,text),page(2,extra)],reply,folder)
            state=json.loads(CourseRepository(Path(folder)).paths('cours-test').root.joinpath('pedagogy.json').read_text())
            self.assertEqual(state['content_reviews']['cellule']['recovery']['points'][0]['quote'],extra)
            result=self.prepare([c],[page(1,text),page(2,extra)],reply,folder)
        self.assertEqual(counts['recovery'],1);self.assertFalse(result.issues)

    def test_alternatives_mistyped_steps_are_corrected_without_changing_source(self):
        text='Choisir une couleur froide ou une couleur chaude.';c=notion('colors','Choix des couleurs',text,kind='method')
        fake=FakeModel({1:[fact(text,'steps')]})
        def reply(**kw):
            raw=fake(**kw)
            if kw['response_model'].__name__=='ContentAssessment':raw.update(concept_type='concept',point_kinds={'p1':'alternatives'})
            return raw
        with TemporaryDirectory() as folder:result=self.prepare([c],[page(1,text)],reply,folder)
        self.assertFalse(result.issues)
        self.assertEqual(result.inventory.concepts[0].type,'concept')
        self.assertEqual(result.inventory.concepts[0].learning_points[0].kind,'alternatives')
        self.assertEqual(result.inventory.concepts[0].learning_points[0].quote,text)

    def test_local_coverage_issue_only_affects_its_part_in_status_and_ui(self):
        collection=CardCollection(course_id='cours-test',file_hash=SHA,inventory_hash=SHA,model=MODEL,
            quality_version=pedagogy.QUALITY_VERSION,review_issues=[dict(page=2,status='review_pending',
                reason='Lecture locale à reprendre.',affected_part_ids=['p2'])],
            parts=[dict(part_id=p,part_number=str(i),status='complete',cards_generated=0) for i,p in enumerate(['p1','p2'],1)])
        view=publication_view(collection)
        self.assertEqual([p.status for p in view.parts],['complete','partial'])
        with TemporaryDirectory() as folder:
            repo=CourseRepository(Path(folder));repo.save_cards('cours-test',collection.model_dump(mode='json'))
            with patch.object(service,'_repository',return_value=repo):
                self.assertFalse(service.load_part_unavailable(dict(course_id='cours-test',file_hash=SHA),'p1'))
                self.assertEqual(len(service.load_part_unavailable(dict(course_id='cours-test',file_hash=SHA),'p2')),1)
        self.assertEqual([p.status for p in collection.parts],['complete','complete'])

    def test_plain_technical_example_gets_code_rendering_but_formula_is_unchanged(self):
        for text in ['color: red;', 'margin: 0 0 5px 5px;', 'out = lire(fichier)']:
            view=present_card(dict(title='Utilisation',concept_type='property',sections=[dict(title='Exemple du cours',content=text)]))
            self.assertIn('<pre><code>'+text+'</code></pre>',view['content_html'])
        text=r'\(c_n = (a_n - i b_n)/2\)'
        view=present_card(dict(title='Coefficients',concept_type='formula',sections=[dict(title='Expression',content=text)]))
        self.assertNotIn('<pre>',view['content_html']);self.assertIn('/2',view['content_html'])

    def test_grouped_legacy_card_is_archived_only_when_its_target_is_available(self):
        a=notion('a');b=notion('b','Autre libellé')
        inv=inventory(a,b);pages=[page(1,a.evidence[0].excerpt)]
        old_card=StudyCard(card_id='old-b',concept_id='b',title=b.title,concept_type=b.type,primary_part_id='p1',source_pages=[1],
            sections=[dict(key='definition',title='Définition',content=b.evidence[0].excerpt)])
        current=old_card.model_copy(update={'concept_id':'a','card_id':'new-a','title':a.title})
        material=pedagogy.Material(inventory(a),'material',relations=[dict(concept_id='b',target_id='a',action='merge',primary_part_id='p1')])
        with TemporaryDirectory() as folder,ExitStack() as stack:
            repo=CourseRepository(Path(folder));repo.save_inventory('cours-test',inv.model_dump(mode='json'))
            repo.save_cards('cours-test',CardCollection(course_id='cours-test',file_hash=SHA,inventory_hash=SHA,model=MODEL,cards=[old_card]).model_dump(mode='json'))
            for name,value in [('CourseRepository',repo),('load_course',dict(course_id='cours-test',file_hash=SHA,source_filename='x.pdf')),
                               ('load_course_plan',PLAN),('extract_document',dict(file_hash=SHA,pages=pages)),('prepare_material',material)]:
                stack.enter_context(patch.object(cards,name,return_value=value))
            generate=stack.enter_context(patch.object(cards,'_generate_batch',side_effect=ConnectionError('panne')))
            failed=cards.build_cards('cours-test',model=MODEL)
            self.assertEqual(failed.unreviewed_cards,[old_card]);self.assertFalse(failed.archived_cards)
            generate.side_effect=None;generate.return_value=[current]
            complete=cards.build_cards('cours-test',model=MODEL)
            self.assertFalse(complete.unreviewed_cards);self.assertEqual(complete.archived_cards,[old_card])
            self.assertEqual(complete.relations[0]['source_card_id'],'old-b')
            self.assertEqual(complete.cards[0].covered_concept_ids,['b'])

    def test_all_wrong_associations_trigger_recovery_instead_of_stopping(self):
        original='Un triangle possède trois côtés.';correct='La cellule est une unité du vivant.'
        c=notion(text=original);fake=FakeModel({1:[fact(original)],2:[]})
        calls=[]
        def reply(**kw):
            data=payload(kw);name=kw['response_model'].__name__;calls.append(name)
            if name=='ContentAssessment':
                return dict(disposition='developed',concept_type='concept',reason='La définition propre à la cellule est conservée.',
                            excluded_points={'p1':'Description du triangle, autre notion.'})
            if name=='SourceJudgment':return dict(supported=True,reason='La citation ne concerne pas la cellule.')
            if name=='EvidenceRecovery':
                u=next(s for s in data['sources'] if s['page']==2)
                return dict(selections=[dict(source_ref=u['ref'],start_line=1,end_line=1,kind='explanation')],reason='Définition propre retrouvée.')
            if name=='EvidenceScope':return dict(verdict='about_this_notion',reason='Définition de la cellule.')
            return fake(**kw)
        with TemporaryDirectory() as folder:
            result=self.prepare([c],[page(1,original),page(2,correct)],reply,folder)
        self.assertFalse(result.issues)
        self.assertIn('EvidenceRecovery',calls)
        self.assertEqual([p.quote for p in result.inventory.concepts[0].learning_points],[correct])

    def test_rejected_response_is_recorded_without_marking_an_empty_card_valid(self):
        text='La cellule est une unité du vivant.';c=notion(text=text)
        fake=FakeModel({1:[fact(text)]})
        def reply(**kw):
            if kw['response_model'].__name__=='ContentAssessment':
                return {'disposition':'autre_contrat_invalide','reason':'Réponse erronée injectée.'}
            return fake(**kw)
        with TemporaryDirectory() as folder:
            result=self.prepare([c],[page(1,text)],reply,folder)
            state=json.loads(CourseRepository(Path(folder)).paths('cours-test').root.joinpath('pedagogy.json').read_text())
        self.assertFalse(result.inventory.concepts);self.assertTrue(result.issues)
        self.assertEqual(len(state['rejected_attempts']),2)
        self.assertEqual(state['rejected_attempts'][0]['schema'],'ContentAssessment')
        self.assertIn('autre_contrat_invalide',state['rejected_attempts'][0]['response_excerpt'])

    def test_real_v14_cache_shape_keeps_coverage_but_discards_its_cyclic_decision(self):
        c=notion();inv=inventory(c);doc=dict(file_hash=SHA,pages=[page(1,c.evidence[0].excerpt)])
        fake=FakeModel({1:[fact(c.evidence[0].excerpt)]})
        with TemporaryDirectory() as folder:
            self.prepare([c],doc['pages'],fake,folder)
            path=CourseRepository(Path(folder)).paths('cours-test').root/'pedagogy.json'
            old=json.loads(path.read_text())
            for field in ['coverage_hash','content_reviews','group_reviews']:old.pop(field,None)
            old['version']=15;old['decision_protocol']=3
            old['fingerprint']=pedagogy.digest(dict(version=15,coverage_protocol=2,pdf=SHA,
                extraction=pedagogy.source_chunks(doc),inventory=inv.model_dump(mode='json'),plan=PLAN,model=MODEL))
            old['decisions']={'cellule':{'hash':'old','decision':dict(action='merge',target_id='cellule')}}
            path.write_text(json.dumps(old,ensure_ascii=False),encoding='utf-8');original=path.read_bytes()
            fake.calls.clear();result=self.prepare([c],doc['pages'],fake,folder)
            self.assertTrue(any(p.read_bytes()==original for p in path.parent.glob('_backups/pedagogy*.json')))
        self.assertFalse(result.issues);self.assertEqual(result.inventory.concepts[0].concept_id,c.concept_id)
        self.assertFalse(any(name=='CoverageResponse' for name,_ in fake.calls))
        self.assertTrue(any(name=='ContentAssessment' for name,_ in fake.calls))

    def test_group_in_an_earlier_part_waits_for_target_even_after_interruption(self):
        root=notion('a').model_copy(update={'primary_part_id':'p2','source_pages':[2],
            'evidence':[notion(page=2).evidence[0]]})
        inv=inventory(root)
        inv.parts.append(inv.parts[0].model_copy(update={'part_id':'p2','part_number':'2','concepts_found':1}))
        plan={'parts':[dict(id='p1',number='1',page_start=1,page_end=1),dict(id='p2',number='2',page_start=2,page_end=2)]}
        doc=dict(file_hash=SHA,pages=[page(2,root.evidence[0].excerpt)])
        material=pedagogy.Material(inv,'material',relations=[dict(concept_id='b',target_id='a',action='merge',primary_part_id='p1')])
        def stop(done,total,part,state):
            if done==1:raise KeyboardInterrupt()
        with TemporaryDirectory() as folder,ExitStack() as stack:
            repo=CourseRepository(Path(folder));repo.save_inventory('cours-test',inv.model_dump(mode='json'))
            for name,value in [('CourseRepository',repo),('load_course',dict(course_id='cours-test',file_hash=SHA,source_filename='x.pdf')),
                               ('load_course_plan',plan),('extract_document',doc),('prepare_material',material)]:
                stack.enter_context(patch.object(cards,name,return_value=value))
            generate=stack.enter_context(patch.object(cards,'_generate_batch'))
            with self.assertRaises(KeyboardInterrupt):cards.build_cards('cours-test',model=MODEL,progress_callback=stop)
            saved=CardCollection.model_validate(repo.load_cards('cours-test'))
            self.assertEqual([p.status for p in saved.parts],['partial','partial'])
            generate.assert_not_called()
            generated=StudyCard(card_id='root-a',concept_id='a',title=root.title,concept_type=root.type,primary_part_id='p2',
                source_pages=[2],sections=[dict(key='d',title='Définition',content=root.evidence[0].excerpt)])
            generate.return_value=[generated]
            done=cards.build_cards('cours-test',model=MODEL)
            self.assertEqual([p.status for p in done.parts],['complete','complete'])
