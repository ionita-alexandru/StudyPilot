"""Reprise bornée de TOUS les cours : vrais contrôles, checkpoints, bilan exact."""
from __future__ import annotations
import os
os.environ.setdefault('STUDYPILOT_AI_PROVIDER','gemma')
os.environ.setdefault('STUDYPILOT_MODEL','gemma-4-26b-a4b-it')
import argparse,json,hashlib,subprocess,sys,time,threading,queue,shutil
from datetime import datetime
from pathlib import Path
from src.storage.course_repository import CourseRepository
from src.storage.repository import read_json,StorageError
from src.models.card import CardCollection
from src.courses.card_presentation import publication_view
from src.courses.pedagogy import QUALITY_VERSION
from reprendre_cours import collect_diagnostic


def state(repository,cid):
    root=repository.paths(cid).root
    try:p=read_json(root/'pedagogy.json')
    except StorageError:p={}
    try:
        c=publication_view(CardCollection.model_validate(repository.load_cards(cid)))
        complete=bool(c.parts) and all(x.status=='complete' for x in c.parts) and not (c.blocked or c.failures or c.review_issues or c.unreviewed_cards) and c.quality_version==QUALITY_VERSION and p.get('stage')=='prepared' and p.get('fingerprint')==c.quality_hash
        report=dict(course_id=cid,complete=complete,cards=len(c.cards),parts_complete=sum(x.status=='complete' for x in c.parts),parts=len(c.parts),blocked=len(c.blocked),failed=len(c.failures),reviews=len(c.review_issues),unreviewed=len(c.unreviewed_cards))
        published=[x.card_id for x in c.cards]
    except (StorageError,ValueError):report=dict(course_id=cid,complete=False,cards=0,reason='Fiches absentes ou invalides');published=[]
    # Seulement les étapes validées : des messages d'erreur différents ne sont pas un progrès.
    progress={'chunks':p.get('chunks',{}),'cards':published,'content':{},'groups':{}}
    for cid2,v in p.get('content_reviews',{}).items():
        progress['content'][cid2]={k:v[k] for k in ('candidate_checks','assessment','recovery','reassessment','visual_assessment','recovery_batches') if k in v}
    for cid2,v in p.get('group_reviews',{}).items():
        if 'result' in v:progress['groups'][cid2]=v['result']
    return report,hashlib.sha256(json.dumps(progress,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def run(command,project,log,deadline):
    log.write('\n>>> '+' '.join(command)+'\n');log.flush()
    child=subprocess.Popen([sys.executable,'-u',*command],cwd=project,env={**os.environ,'PYTHONUTF8':'1'},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='backslashreplace')
    output=queue.Queue()
    def drain():
        for line in child.stdout:output.put(line)
        output.put(None)
    threading.Thread(target=drain,daemon=True).start()
    try:
        while True:
            if time.monotonic()>=deadline:raise TimeoutError('Budget de temps atteint ; checkpoints conservés.')
            try:line=output.get(timeout=.25)
            except queue.Empty:continue
            if line is None:return child.wait()
            print(line,end='',flush=True);log.write(line);log.flush()
    finally:
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        child.stdout.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--minutes',type=int,default=45);parser.add_argument('--course-minutes',type=int,default=10,help='Temps maximum par cours et par passe, avant de passer au suivant.');parser.add_argument('--status-only',action='store_true');args=parser.parse_args(argv)
    if not 1<=args.minutes<=180:parser.error('--minutes doit être compris entre 1 et 180')
    if not 1<=args.course_minutes<=args.minutes:parser.error('--course-minutes doit être compris entre 1 et --minutes')
    root=Path(__file__).resolve().parent;repo=CourseRepository();ids=repo.list_course_ids();stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f');log_path=root/('resultats-v15_6-'+stamp+'.txt');deadline=time.monotonic()+args.minutes*60;code=0
    with log_path.open('x',encoding='utf-8') as log:
        try:
            if not args.status_only:
                if not os.getenv('GEMINI_API_KEY','').strip():raise ValueError('GEMINI_API_KEY absent dans ce terminal. Aucune génération lancée.')
                from src.config import AI_PROVIDER
                if AI_PROVIDER!='gemma':raise ValueError('Activer le fournisseur gemma. Aucune génération lancée.')
                code=run(['verifier_gemma.py'],root,log,deadline)
                if code:raise ValueError('Vérification API échouée. Aucune génération lancée.')
                for cid in ids:
                    folder=repo.paths(cid).root;backup=folder/'_backups'/('before_full_'+stamp);backup.mkdir(parents=True)
                    for name in ('course.json','plan.json','inventory.json','pedagogy.json','cards.json'):
                        if (folder/name).is_file():shutil.copy2(folder/name,backup/name)
                idle=0
                for cycle in range(1,5):
                    before={cid:state(repo,cid)[1] for cid in ids};pending=[cid for cid in ids if not state(repo,cid)[0]['complete']]
                    if not pending:break
                    print(f'Passe {cycle}/4 : {len(pending)} cours à terminer.',flush=True)
                    fatal=False
                    for cid in pending:
                        if time.monotonic()>=deadline:raise TimeoutError('Budget total atteint ; checkpoints conservés.')
                        course_deadline=min(deadline,time.monotonic()+args.course_minutes*60)
                        try:
                            code=run(['manage.py','cards','build','--course',cid],root,log,course_deadline)
                        except TimeoutError:
                            if time.monotonic()>=deadline:raise
                            message=f'Cours {cid} : créneau terminé, checkpoints conservés ; passage au cours suivant.'
                            print(message,flush=True);log.write(message+'\n');log.flush();code=2
                        if code == 4:
                            message=f'Cours {cid} : panne temporaire, checkpoints conservés ; passage au cours suivant.'
                            print(message,flush=True);log.write(message+'\n');log.flush()
                        if code not in (0,2,4):fatal=True;break
                    if fatal:break
                    changed=any(state(repo,cid)[1]!=before[cid] for cid in ids)
                    idle=0 if changed else idle+1
                    if idle>=2:
                        print('Arrêt : deux passes sans nouvelle étape validée. Examiner le diagnostic, sans boucle de relances.');break
        except (ValueError,TimeoutError,KeyboardInterrupt) as e:
            code=1;message='ARRÊT : '+str(e);print(message);log.write(message+'\n')
        reports=[state(repo,cid)[0] for cid in ids];done=bool(reports) and all(r['complete'] for r in reports)
        bilan=json.dumps({'all_complete':done,'courses':reports},ensure_ascii=False,indent=2);print(bilan);log.write('\nBILAN FINAL\n'+bilan+'\n');log.flush()
        report_path=root/('bilan-v15_6-'+stamp+'.json');report_path.write_text(bilan,encoding='utf-8')
    archive=collect_diagnostic(root,repo,log_path,stamp)
    print('Diagnostic :',archive);print('Bilan :',report_path)
    if not done:print('Les cours ne sont PAS tous terminés. Les checkpoints restent disponibles.')
    return 0 if done else (code or 2)

if __name__=='__main__':raise SystemExit(main())
