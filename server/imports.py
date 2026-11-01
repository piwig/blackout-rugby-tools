"""Read data only: no shell commands, macros, formulas or external links."""
import csv
import io
import json
import zipfile
from defusedxml import ElementTree as ET
from .domain import SKILLS,number

PLAYER_FIELDS=set(SKILLS+['id','name','age','age_decimal','birthday','weight','height','nationality','dualnationality','aggression','discipline','leadership','experience','energy','form','stars','jersey','pops','reveals','WC','csr','delta_csr','salary','capped_for','injured'])
ALIASES={'player_id':'id','playerid':'id','player_name':'name','scouting_stars_used':'stars'}
MAX_PLAYERS=4000
MAX_XML_DEPTH=48
MAX_XML_NODES=500_000
MAX_CELL_CHARS=4096
MAX_EXPANDED_CELLS=300_000
MAX_EXPANDED_TEXT=8_000_000
PLAYER_SHEETS={'players','latouff_players','moeskroen_ya','latouff_academy'}
ODS_SHEETS=PLAYER_SHEETS|{'team','youth_training','latouff_yatt','Academy'}

class ImportLimitError(ValueError):
    """Safe validation messages which never contain raw input."""

def reject_constant(value):
    raise ValueError('Valeur numérique non finie interdite.')

def read_csv(data, *, max_rows=MAX_PLAYERS):
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:text=data.decode('cp1252')
    try:dialect=csv.Sniffer().sniff(text[:8192],delimiters=';,\t')
    except csv.Error:raise ValueError('CSV : colonnes séparées par virgule, point-virgule ou tabulation attendues.')
    reader=csv.DictReader(io.StringIO(text),dialect=dialect)
    if len(reader.fieldnames or [])>100:raise ValueError('Maximum 100 colonnes CSV.')
    rows=[]
    for row in reader:
        if len(rows)>=max_rows:raise ValueError('Maximum 4 000 joueurs par fichier.' if max_rows==MAX_PLAYERS else 'Maximum 20 000 événements par fichier.')
        rows.append(row)
    return rows

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
            if len(value)>1024:raise ValueError('Liste '+k+' trop volumineuse.')
            try:value=json.loads(value)
            except (ValueError,TypeError):value=[]
        if isinstance(value,list) and len(value)>100:raise ValueError('Liste '+k+' trop volumineuse.')
        p[k]=list(dict.fromkeys(x for x in value if isinstance(x,str) and x in SKILLS)) if isinstance(value,list) else []
    return p

def read_ods(data):
    """Stream a bounded XML tree; expand only supported sheets within explicit budgets."""
    ns='urn:oasis:names:tc:opendocument:xmlns:table:1.0'; tag=lambda k:'{'+ns+'}'+k
    sheets={}; stack=[]; nodes=0; table_depth=None; active=None
    cells=None; cell_depth=None; row_depth=None; rows=[]
    expanded_cells=expanded_text=player_count=0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info=z.getinfo('content.xml')
            if info.file_size>20_000_000:raise ImportLimitError('Classeur décompressé trop volumineux.')
            with z.open(info) as stream:
                for event,element in ET.iterparse(stream,events=('start','end')):
                    if event=='start':
                        stack.append(element);nodes+=1;depth=len(stack)
                        if depth>MAX_XML_DEPTH or nodes>MAX_XML_NODES:raise ImportLimitError('Structure XML trop volumineuse.')
                        if element.tag==tag('table'):
                            if table_depth is not None:raise ImportLimitError('Tables ODS imbriquées interdites.')
                            table_depth=depth
                            name=element.get(tag('name'),'')
                            active=name if name in ODS_SHEETS else None
                            if active in sheets:raise ImportLimitError('Feuille ODS en double.')
                            rows=[]
                        elif active and element.tag==tag('table-row'):
                            if row_depth is not None:raise ImportLimitError('Lignes ODS imbriquées interdites.')
                            row_depth=depth;cells=[]
                        elif active and cells is not None and element.tag in (tag('table-cell'),tag('covered-table-cell')):
                            if cell_depth is not None:raise ImportLimitError('Cellules ODS imbriquées interdites.')
                            cell_depth=depth
                        continue
                    depth=len(stack)
                    if cell_depth==depth:
                        # Check text before joining or multiplying it. XML nodes stay only
                        # until this cell ends, never for the entire spreadsheet.
                        parts=[];size=0
                        for part in element.itertext():
                            size+=len(part)
                            if size>MAX_CELL_CHARS:raise ImportLimitError('Cellule ODS trop volumineuse.')
                            parts.append(part)
                        value=''.join(parts)
                        repeat=int(element.get(tag('number-columns-repeated'),'1'))
                        if repeat<1:raise ImportLimitError('Répétition ODS invalide.')
                        count=min(repeat,max(0,100-len(cells)))
                        cells.extend([value]*count)
                        cell_depth=None
                    elif row_depth==depth:
                        if any(cells):
                            repeat=int(element.get(tag('number-rows-repeated'),'1'))
                            if repeat<1:raise ImportLimitError('Répétition ODS invalide.')
                            repeat=min(repeat,100)
                            next_cells=expanded_cells+len(cells)*repeat
                            next_text=expanded_text+sum(len(value.encode('utf-8')) for value in cells)*repeat
                            if next_cells>MAX_EXPANDED_CELLS or next_text>MAX_EXPANDED_TEXT:
                                raise ImportLimitError('Budget de dépliage ODS dépassé : classeur trop volumineux.')
                            if len(rows)+repeat>4001:raise ImportLimitError('Maximum 4 000 lignes de données par feuille.')
                            if active in PLAYER_SHEETS and str(cells[0]).isdigit():
                                player_count+=repeat
                                if player_count>MAX_PLAYERS:raise ImportLimitError('Maximum 4 000 joueurs par fichier.')
                            rows.extend([cells]*repeat)
                            expanded_cells,expanded_text=next_cells,next_text
                        cells=None;row_depth=None
                    elif table_depth==depth:
                        if active:sheets[active]=rows
                        active=None;table_depth=None;rows=[]
                    # Removing completed nodes bounds both live elements and sibling lists.
                    # Descendants of the current cell must survive until its text is read.
                    if cell_depth is None:
                        element.clear()
                        if len(stack)>1:stack[-2].remove(element)
                    stack.pop()
    except ImportLimitError:raise
    except Exception as e:raise ValueError('Classeur ODS invalide ou trop volumineux.') from e
    return sheets

def row_dicts(rows):
    if not rows:return []
    return [dict(zip(rows[0],r)) for r in rows[1:] if r and str(r[0]).isdigit()]

def parse_import(data,filename,*,allow_empty=False):
    if len(data)>8_000_000:raise ValueError('Fichier limité à 8 Mo.')
    empty_roster=False
    name=filename.lower();result={'players':[],'datasets':[],'game_date':None,'team':{},'training':[],'plans':{}}
    try:
        if name.endswith('.ods'):
            sheets=read_ods(data)
            for sheet,rows in sheets.items():
                # Derived sheets deliberately ignored: preserve original observations.
                if sheet not in PLAYER_SHEETS:continue
                players=[normalize_player(r) for r in row_dicts(rows)]
                if players:result['datasets'].append({'team_hint':'latouff' if sheet.startswith('latouff') else 'moeskroen' if sheet.startswith('moeskroen') else None,'youth':sheet.endswith(('_ya','_academy')),'players':players,'sheet':sheet})
            if 'team' in sheets and len(sheets['team'])>1:result['team']=dict(zip(sheets['team'][0],sheets['team'][1]))
            for sheet in ['youth_training','latouff_yatt']:
                if sheet in sheets:
                    result['training'] += [{**r,'team_hint':'latouff' if sheet.startswith('latouff') else 'moeskroen' if sheet.startswith('moeskroen') else None} for r in row_dicts(sheets[sheet])]
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
                if not isinstance(source,(dict,list)) or len(source)>MAX_PLAYERS:raise ValueError('Maximum 4 000 joueurs par fichier.')
                empty_roster='players' in doc and not source
                players=[{**v,'id':str(k)} for k,v in source.items()] if isinstance(source,dict) else source
                date=doc.get('gameDate',doc.get('game_date'))
                if isinstance(date,dict) and all(number(date.get(k)) is not None for k in ('season','round','day')):result['game_date']={k:int(date[k]) for k in ('season','round','day')}
            else:raise ValueError('Objet JSON ou liste de joueurs attendu.')
            if len(players)>MAX_PLAYERS:raise ValueError('Maximum 4 000 joueurs par fichier.')
            result['players']=[normalize_player(p) for p in players]
        elif name.endswith('.csv'):
            result['players']=[normalize_player(r) for r in read_csv(data)]
        else:raise ValueError('Formats acceptés : ODS, CSV, JSON.')
    except (ValueError,KeyError,TypeError,csv.Error,UnicodeError) as e:
        raise ValueError('Import refusé : '+str(e)[:180]) from e
    if (not result['players'] and not (allow_empty and empty_roster)) or len(result['players'])>MAX_PLAYERS:raise ValueError('Le fichier doit contenir entre 1 et 4 000 joueurs.')
    for dataset in result['datasets'] or [{'players':result['players']}]:
        ids=[player['id'] for player in dataset['players']]
        if len(set(ids))!=len(ids):raise ValueError('Le fichier contient plusieurs joueurs avec le même identifiant dans un effectif.')
    return result
