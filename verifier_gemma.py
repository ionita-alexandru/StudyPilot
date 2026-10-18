"""Deux appels réels, sans modification des cours ni des caches pédagogiques."""
from __future__ import annotations
import argparse
import base64
from typing import Literal

import pymupdf
from pydantic import BaseModel, ConfigDict
from src.ai.client import AIUnavailableError, AIUsageLimitError, chat_json
from src.config import AI_PROVIDER, STUDY_MODEL

class TextCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    condition: Literal['x > 0']
    conclusion: Literal['f(x) = 1/x']
    example_present: Literal[False]

class ImageCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    marker: Literal['SOURCE 7319']
    condition: Literal['x > 0']


def verify():
    if AI_PROVIDER != 'gemma':
        raise AIUnavailableError('Activer STUDYPILOT_AI_PROVIDER=gemma dans ce terminal.')
    result = chat_json(response_model=TextCheck, messages=[
        {'role':'system','content':'Recopie exactement condition et conclusion depuis la source unique. '
         'example_present indique si la source donne un exemple. N’ajoute aucune connaissance.'},
        {'role':'user','content':'Source unique : Pour x > 0, on définit f(x) = 1/x. Aucun exemple n’est donné.'}],
        options={'temperature':0,'num_predict':800})
    # Le marqueur n’apparaît pas dans le prompt : il faut lire les pixels.
    document=pymupdf.open(); page=document.new_page(width=400,height=150)
    page.insert_text((25,50),'SOURCE 7319',fontsize=24)
    page.insert_text((25,100),'x > 0',fontsize=24)
    png=page.get_pixmap().tobytes('png');document.close()
    image = chat_json(response_model=ImageCheck, messages=[
        {'role':'user','content':'Lis l’image. Recopie exactement son marqueur SOURCE et sa condition mathématique.',
         'images':[base64.b64encode(png).decode('ascii')]}],options={'temperature':0,'num_predict':800})
    print('OK : accès réel, contrat JSON validé, condition/conclusion et absence d’exemple respectées.')
    print('OK : marqueur et condition lus dans une image réelle.')
    print('Modèle : '+STUDY_MODEL)
    print('Ces essais techniques ne valident pas encore la qualité des fiches de cours.')
    return result, image


def main():
    try:
        verify();return 0
    except (AIUnavailableError,AIUsageLimitError,ValueError) as error:
        print(f'ÉCHEC : {type(error).__name__}: {error}');return 3

if __name__=='__main__':raise SystemExit(main())
