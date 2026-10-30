"""Restricted, read-only API adapter. Never log request URLs (keys in query)."""
import asyncio
import json
import logging
import time
import httpx
from defusedxml import ElementTree as ET

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
BASE='https://classic-api.blackoutrugby.com/'

class ClassicError(ValueError):pass

class ClassicClient:
    def __init__(self,credentials):
        self.credentials={k:str(v) for k,v in credentials.items() if k in ['d','dk','m','mk']}
    async def request(self,resource,**params):
        if not self.credentials.get('d') or not self.credentials.get('dk'):raise ClassicError('Ajoutez vos identifiants développeur Classic dans Connexion & données.')
        if resource not in ['p','t','f','ls','me']:raise ClassicError('Ressource non autorisée.')
        query={**self.credentials,'r':resource,'json':'1',**params}
        if resource=='me':query.pop('json')
        try:
            async with httpx.AsyncClient(timeout=25,follow_redirects=False) as client:
                async with client.stream('GET',BASE,params=query) as response:
                    if response.status_code!=200:raise ClassicError('API Classic indisponible. Réessayez plus tard.')
                    chunks=[];size=0
                    async for chunk in response.aiter_bytes():
                        size+=len(chunk)
                        if size>8_000_000:raise ClassicError('Réponse Classic trop volumineuse.')
                        chunks.append(chunk)
            data=b''.join(chunks)
        except httpx.HTTPError as e:raise ClassicError('Impossible de joindre l’API Classic. Les données précédentes sont conservées.') from None
        if resource=='me':
            try:
                root=ET.fromstring(data)
                if any(e.tag.lower().endswith('error') for e in root.iter()):raise ClassicError('Classic refuse cette requête : vérifiez les clés et les droits du manager.')
                return {'events':parse_commentary(root)}
            except ClassicError:raise
            except Exception:raise ClassicError('Commentaire XML Classic non reconnu.') from None
        try:doc=json.loads(data)
        except ValueError:raise ClassicError('Réponse Classic non JSON. Vérifiez les clés et les droits du manager.') from None
        if not isinstance(doc,dict) or doc.get('error') or doc.get('errors'):raise ClassicError('Classic refuse cette requête : vérifiez les clés et les droits du manager.')
        return doc

def parse_commentary(root):
    """Accept explicit structured fields; do not infer tactical categories from prose."""
    events=[]
    for element in root.iter():
        fields=dict(element.attrib)
        fields.update({child.tag.rsplit('}',1)[-1]:(child.text or '').strip() for child in element if not list(child)})
        if ('field' in fields or 'possession' in fields) and any(k in fields for k in ['text','commentary','comment','att']):
            events.append({k:fields[k] for k in ['field','possession','att','time','minute','text','commentary','comment'] if k in fields})
    if not events:
        # Preserve readable evidence even when this engine schema has no mapped fields.
        for element in root.iter():
            if element.tag.rsplit('}',1)[-1].lower() in ['comment','commentary','event','text'] and element.text and len(element.text.strip())>5:
                events.append({'text':element.text.strip()[:2000]})
    return events[:20000]
