"""Restricted, read-only API adapter. Never log request URLs (keys in query)."""
import asyncio
import json
import logging
import re
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

def classify_attack(text):
    """Conservative, versioned EN commentary heuristics, never official tactics."""
    text=re.sub(r'\[[^\]]+\]','',text).lower()
    rules=[
      ('png',r'pick(?:s|ing)?\s*(?:and|&|n|[’\x27]n[’\x27])\s*go|picks? (?:it|the ball) up (?:and|then) (?:drives|goes)'),
      ('crea',r'something creative|creative (?:move|play|attack)|(?:triple |double )?scissors|switch move|loop move|dummy runner|decoy runner'),
      ('large',r'out wide|go(?:es|ing)? wide|expansive (?:move|play|attack)|spread(?:s|ing)? the ball|through the hands'),
      ('percu',r'on the drive|crash ball|crash-ball|takes? the ball up|hits? it up|charges? (?:straight )?at (?:the )?(?:defence|defense)'),
      ('kick',r'grubber|up.and.under|box kick|chip kick|punts? (?:the ball )?(?:downfield|upfield|into touch)|hoists? (?:the ball )?high')]
    for category,pattern in rules:
        if re.search(pattern,text):return category
    return None

def parse_commentary(root):
    """Preserve raw fields and label every inferred tactical classification."""
    events=[]
    previous=None
    for element in root.iter():
        fields=dict(element.attrib)
        fields.update({child.tag.rsplit('}',1)[-1]:(child.text or '').strip() for child in element if not list(child)})
        if ('field' in fields or 'possession' in fields) and any(k in fields for k in ['text','commentary','comment','att']):
            event={k:fields[k] for k in ['id','field','possession','att','time','minute','text','commentary','comment','gametime','half','homescore','guestscore'] if k in fields}
            raw=event.get('commentary',event.get('text',event.get('comment','')))
            event['text']=re.sub(r'\[[^\]]+\]','',raw)
            if event.get('gametime','').isdigit():
                seconds=int(event['gametime']);event['time']=f'{seconds//60}:{seconds%60:02d}'
            if not event.get('att'):
                attack=classify_attack(raw)
                if attack:
                    event['att']=attack;event['att_origin']='commentary-rule';event['rule_version']='1'
                    # Engine possession is post-action: use prior possession on a turnover.
                    if previous in ['0','1'] and previous!=event.get('possession'):
                        event['possession_reported']=event.get('possession');event['possession']=previous
            previous=fields.get('possession',previous)
            events.append(event)
    if not events:
        # Preserve readable evidence even when this engine schema has no mapped fields.
        for element in root.iter():
            if element.tag.rsplit('}',1)[-1].lower() in ['comment','commentary','event','text'] and element.text and len(element.text.strip())>5:
                events.append({'text':element.text.strip()[:2000]})
    return events[:20000]
