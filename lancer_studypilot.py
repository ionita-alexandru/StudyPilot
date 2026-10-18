"""Démarrer StudyPilot : vraie application, vrai chat IA, import et révision."""
import os
os.environ.setdefault('STUDYPILOT_AI_PROVIDER','gemma')
os.environ.setdefault('STUDYPILOT_MODEL','gemma-4-26b-a4b-it')
os.environ.pop('STUDYPILOT_PRESENTATION',None)
import argparse,threading,webbrowser
from app import app
if __name__=='__main__':
    from src.upload_service import restore_jobs
    restore_jobs()
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=5000);parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    print(f'StudyPilot : http://127.0.0.1:{args.port}\nChat IA : '+os.environ['STUDYPILOT_MODEL'])
    if not os.getenv('GEMINI_API_KEY','').strip():print('Clé API absente : fiches consultables ; le chat et la génération nécessitent GEMINI_API_KEY.')
    if not args.no_browser:threading.Timer(.8,lambda:webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    app.run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)
