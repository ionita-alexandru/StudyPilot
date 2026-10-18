"""Vérifie Gemma et reprend les fiches des cours sélectionnés, avec journal UTF-8 et diagnostic local.

Usage : python reprendre_cours.py (vérification seule)
Reprise : python reprendre_cours.py --course IDENTIFIANT
Tous : python reprendre_cours.py --all
Lecture seule, sans IA : python reprendre_cours.py --diagnostic-only
Aucun fichier de cours n'est modifié par la collecte du diagnostic.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import os
import shutil
from pathlib import Path
import subprocess
import sys
import zipfile

from src.console import configure_console
from src.storage.course_repository import CourseRepository


def run_logged(project, arguments, log):
    command = [sys.executable, '-u', str(project / 'manage.py'), *arguments]
    header = '\n>>> python manage.py ' + ' '.join(arguments) + '\n'
    print(header, end='', flush=True); log.write(header); log.flush()
    child = subprocess.Popen(command, cwd=project, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='backslashreplace', env={**os.environ, 'PYTHONUTF8':'1'})
    try:
        for line in child.stdout:
            print(line, end='', flush=True); log.write(line); log.flush()
        return child.wait()
    except BaseException:
        # Les checkpoints de manage.py sont déjà écrits avant les lots.
        # Ne pas laisser le traitement enfant travailler après notre sortie.
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait()
        raise
    finally:
        child.stdout.close()


def collect_diagnostic(project, repository, log_path, timestamp):
    target=project / ('diagnostic-v15_4-' + timestamp + '.zip')
    # Liste positive : pas de PDF, configuration, secrets, ni anciennes archives.
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(log_path, log_path.name)
        ai_diagnostic = project / 'data' / '_ai' / 'gemma_failures.json'
        if ai_diagnostic.is_file(): archive.write(ai_diagnostic, 'ai/gemma_failures.json')
        for cid in repository.list_course_ids():
            for name in ('course.json','plan.json','inventory.json','pedagogy.json','cards.json'):
                path=repository.paths(cid).root/name
                if path.is_file(): archive.write(path, 'courses/' + cid + '/' + name)
    return target


def main(argv=None):
    configure_console()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic-only',action='store_true',help='Statuts et ZIP uniquement, sans génération ni tests.')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--course',help='Identifiant exact : reprendre les fiches de ce cours.')
    mode.add_argument('--all',action='store_true',help='Reprendre les fiches de tous les cours après validation sur un cours.')
    args=parser.parse_args(argv)
    project=Path(__file__).resolve().parent
    if not (project/'manage.py').is_file(): parser.error('Placer ce script à côté de manage.py.')
    repository=CourseRepository()
    timestamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    log_path=project / ('resultats-v15_4-' + timestamp + '.txt')
    code=0
    try:
        with log_path.open('x',encoding='utf-8',newline='\n') as log:
            from src.config import AI_PROVIDER, STUDY_MODEL
            print(f'Fournisseur : {AI_PROVIDER} ; modèle : {STUDY_MODEL}',file=log,flush=True)
            ids=repository.list_course_ids()
            if args.course and args.course not in ids:
                raise ValueError('Identifiant inconnu. Identifiants disponibles : '+', '.join(ids))
            if not args.diagnostic_only:
                if AI_PROVIDER != 'gemma':
                    raise ValueError('Activer le fournisseur gemma dans ce terminal.')
                code=run_logged(project,['doctor'],log)
                if not code:
                    # Préflight indépendant : aucune écriture dans les cours.
                    command=[sys.executable,'-u',str(project/'verifier_gemma.py')]
                    child=subprocess.run(command,cwd=project,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                        text=True,encoding='utf-8',errors='backslashreplace')
                    print(child.stdout,end='');log.write(child.stdout);log.flush();code=child.returncode
                if not code:
                    selected=ids if args.all else ([args.course] if args.course else [])
                    deferred_code = 0
                    for cid in selected:
                        root=repository.paths(cid).root
                        backup=root/'_backups'/('before_gemma_'+timestamp)
                        backup.mkdir(parents=True,exist_ok=False)
                        for name in ('course.json','plan.json','inventory.json','pedagogy.json','cards.json'):
                            if (root/name).is_file():shutil.copy2(root/name,backup/name)
                        print('Sauvegarde préalable : '+str(backup),file=log,flush=True)
                        # Inventaires existants réutilisés : ne pas reconstruire leurs identifiants.
                        code=run_logged(project,['cards','build','--course',cid],log)
                        if code and not (args.all and code in (2,4)):break
                        deferred_code = max(deferred_code, code)
                    code = code or deferred_code
                    if not selected:
                        print('Vérification seule. Identifiants disponibles : '+', '.join(ids),file=log,flush=True)
            for cid in repository.list_course_ids():
                status=run_logged(project,['cards','status','--course',cid],log)
                if status: code=code or status
    except (ValueError, OSError) as error:
        code=1
        print('ERREUR : '+str(error))
    except KeyboardInterrupt:
        code=130
        print('\nInterruption : les checkpoints permettront la reprise.')
    finally:
        archive=collect_diagnostic(project,repository,log_path,timestamp)
        print('Journal UTF-8 : ' + str(log_path))
        print('Diagnostic local : ' + str(archive))
    if code==3: print('Arrêt IA : consulter le refus de quota, la configuration ou l’erreur fournisseur dans le journal. Aucune autre génération lancée.')
    if code==2: print('Traitement partiel : consulter les diagnostics, aucune réussite complète annoncée.')
    if code==4: print('Panne temporaire : checkpoints conservés, traitement à reprendre.')
    return code


if __name__=='__main__': raise SystemExit(main())
