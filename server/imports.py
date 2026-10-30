"""Read data only: no shell commands, macros, formulas or external links."""
import csv
import io
import json
import zipfile
from defusedxml import ElementTree as ET
from .domain import SKILLS,number

PLAYER_FIELDS=set(SKILLS+['id','name','age','age_decimal','birthday','weight','height','nationality','dualnationality','aggression','discipline','leadership','experience','energy','form','stars','jersey','pops','reveals','WC','csr','delta_csr','salary','capped_for','injured'])
ALIASES={'player_id':'id','playerid':'id','player_name':'name','scouting_stars_used':'stars'}

def reject_constant(value):
    raise ValueError('Valeur numérique non finie interdite.')

def read_csv(data):
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:text=data.decode('cp1252')
    try:dialect=csv.Sniffer().sniff(text[:8192],delimiters=';,\t')
    except csv.Error:raise ValueError('CSV : colonnes séparées par virgule, point-virgule ou tabulation attendues.')
    return list(csv.DictReader(io.StringIO(text),dialect=dialect))

def normalize_player(row):
    if not isinstance(row,dict): raise ValueError('Chaque joueur doit être un objet.')
    p={ALIASES.get(str(k).strip(),str(k).strip()):v for k,v in row.items()}
    p={k:v for k,v in p.items() if k in PLAYER_FIELDS}
    ident=str(p.get('id','')).strip()
    if not ident.isdigit() or len(ident)>15 or not isinstance(p.get('name'),str) or not p['name'].strip(): raise ValueError('Chaque joueur doit avoir un identifiant numérique et un nom.')
    p['id']=ident;p['name']=str(p['name'])[:120]
    for k in PLAYER_FIELDS-{'id','name','birthday','pops','reveals','nationality','dualnationality','capped_for','injured'}:
        value=p.get(k)
        if value is None or value=='':
            p.pop(k,None);continue
        n=number(value)
        if k in SKILLS:
            if isinstance(value,str) and value in ('Unknown','Low','Medium','High'):continue
            if n is None or not 0<=n<=21:raise ValueError('Compétence '+k+' invalide : nombre de 0 à 21 ou Unknown/Low/Medium/High attendu.')
        elif n is None:
            if not isinstance(value,str) or len(value)>100 or value.strip().lower() in ('nan','inf','infinity','-inf','-infinity'):raise ValueError('Valeur invalide : '+k)
        elif abs(n)>1_000_000_000:raise ValueError('Valeur hors limites : '+k)
        if n is not None:p[k]=int(n) if n.is_integer() else n
    for k in ('birthday','nationality','dualnationality','capped_for','injured'):
        if k in p:
            if isinstance(p[k],(dict,list)):raise ValueError('Valeur invalide : '+k)
            p[k]=str(p[k])[:100] if p[k] is not None else ''
    for k in ['pops','reveals']:
        value=p.get(k,[])
        if isinstance(value,str):
            try:value=json.loads(value)
            except (ValueError,TypeError):value=[]
        p[k]=[x for x in value if x in SKILLS] if isinstance(value,list) else []
    return p

def read_ods(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info=z.getinfo('content.xml')
            if info.file_size>20_000_000:raise ValueError('Classeur décompressé trop volumineux.')
            root=ET.fromstring(z.read(info))
    except Exception as e:raise ValueError('Classeur ODS invalide ou trop volumineux.') from e
    ns='urn:oasis:names:tc:opendocument:xmlns:table:1.0'; tag=lambda k:'{'+ns+'}'+k
    sheets={}
    for table in root.iter(tag('table')):
        rows=[]
        for row in table.findall(tag('table-row')):
            cells=[]
            for cell in row:
                if cell.tag not in (tag('table-cell'),tag('covered-table-cell')):continue
                value=''.join(cell.itertext())
                count=min(int(cell.get(tag('number-columns-repeated'),'1')),100)
                cells.extend([value]*count)
                if len(cells)>=100:break
            if not any(cells):continue
            repeat=min(int(row.get(tag('number-rows-repeated'),'1')),100)
            rows.extend([cells]*repeat)
            if len(rows)>4000:raise ValueError('Maximum 4 000 lignes par feuille.')
        sheets[table.get(tag('name'),'')]=rows
    return sheets

def row_dicts(rows):
    if not rows:return []
    return [dict(zip(rows[0],r)) for r in rows[1:] if r and str(r[0]).isdigit()]

def parse_import(data,filename):
    if len(data)>8_000_000:raise ValueError('Fichier limité à 8 Mo.')
    name=filename.lower();result={'players':[],'datasets':[],'game_date':None,'team':{},'training':[],'plans':{}}
    try:
        if name.endswith('.ods'):
            sheets=read_ods(data)
            for sheet,rows in sheets.items():
                # Derived sheets deliberately ignored: preserve original observations.
                if sheet not in ('players','latouff_players','moeskroen_ya','latouff_academy'):continue
                players=[normalize_player(r) for r in row_dicts(rows)]
                if players:result['datasets'].append({'team_hint':'latouff' if sheet.startswith('latouff') else 'moeskroen','youth':sheet.endswith(('_ya','_academy')),'players':players,'sheet':sheet})
            if 'team' in sheets and len(sheets['team'])>1:result['team']=dict(zip(sheets['team'][0],sheets['team'][1]))
            for sheet in ['youth_training','latouff_yatt']:
                if sheet in sheets:
                    result['training'] += [{**r,'team_hint':'latouff' if sheet.startswith('latouff') else 'moeskroen'} for r in row_dicts(sheets[sheet])]
            rows=sheets.get('Academy',[])
            mapping={'END':'stamina','DEX':'handling','ATT':'attack','DEF':'defense','TEC':'technique','FOR':'strength','SAU':'jumping','VIT':'speed','AGI':'agility','KIK':'kicking'}
            for i,row in enumerate(rows):
                for offset in (0,18):
                    if len(row)>offset and str(row[offset]).isdigit() and 1<int(row[offset])<200 and len(row)>offset+1 and str(row[offset+1]).startswith('S'):
                        grid=[]
                        for slot in rows[i+1:i+5]:grid.append([mapping.get(v,'') for v in slot[offset+1:offset+17]])
                        if len(grid)==4 and all(len(slot)==16 for slot in grid):result['plans'][str(row[offset])]=grid
            result['players']=result['datasets'][0]['players'] if result['datasets'] else []
        elif name.endswith('.json'):
            doc=json.loads(data.decode('utf-8-sig'),parse_constant=reject_constant)
            if isinstance(doc,list):players=doc
            elif isinstance(doc,dict):
                source=doc.get('players',[])
                players=[{**v,'id':str(k)} for k,v in source.items()] if isinstance(source,dict) else source
                date=doc.get('gameDate',doc.get('game_date'))
                if isinstance(date,dict) and all(number(date.get(k)) is not None for k in ('season','round','day')):result['game_date']={k:int(date[k]) for k in ('season','round','day')}
            else:raise ValueError('Objet JSON ou liste de joueurs attendu.')
            result['players']=[normalize_player(p) for p in players]
        elif name.endswith('.csv'):
            result['players']=[normalize_player(r) for r in read_csv(data)]
        else:raise ValueError('Formats acceptés : ODS, CSV, JSON.')
    except (ValueError,KeyError,TypeError,csv.Error,UnicodeError) as e:
        raise ValueError('Import refusé : '+str(e)[:180]) from e
    if not result['players'] or len(result['players'])>4000:raise ValueError('Le fichier doit contenir entre 1 et 4 000 joueurs.')
    return result
