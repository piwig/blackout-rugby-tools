import pytest
from server import domain

def test_wc_projection_observes_birthday_and_frank_cohort_rule():
    date = {'season':62,'round':9,'day':6}
    assert domain.wc_projection({'age':16,'birthday':'01:5'}, date) == 66
    assert domain.wc_projection({'age':17,'birthday':'01:5'}, date) is None
    assert domain.wc_projection({'age':16,'birthday':'08:1'}, date) is None
    assert domain.wc_projection({'age':21,'birthday':'01:5'}, date) is None
    assert domain.wc_projection({'age':16,'birthday':'07:5'}, {'season':63,'round':1,'day':1}) == 66
    assert domain.wc_projection({'age':16,'birthday':'bad'}, date) is None

def test_unknown_skills_are_not_zero_or_exact_ratings():
    p={'stamina':'Unknown','handling':'Medium','attack':'12','defense':10}
    m=domain.player_metrics(p)
    assert m['known_skills']==2
    assert m['skill_total']==22
    assert m['estimated_csr'] is None
    assert domain.player_metrics({k:10 for k in domain.SKILLS})['estimated_csr']==42000

def test_attack_zones_are_relative_and_unknowns_stay_unknown():
    result=domain.attack_summary([
      {'field':1,'possession':0,'att':'percu'},
      {'field':1,'possession':1,'att':'large'},
      {'field':3,'possession':0,'att':'crea'},
      {'field':4,'possession':1,'att':'pick and go'},
      {'field':2,'possession':0,'text':'Un commentaire sans classification'},
      {'field':99,'possession':0,'att':'percu'}])
    assert result['home']['zones']['22']['Percussion']==1
    assert result['away']['zones']['22A']['Large']==1
    assert result['home']['zones']['40A']['Créatif']==1
    assert result['away']['zones']['22']['Pick and go']==1
    assert result['unclassified']==2
    assert result['classified']==4

def test_stadium_ratios_and_no_negative_construction():
    r=domain.stadium_plan(1000,{'standing':2300,'uncovered':3000,'covered':3000,'members':800,'corporate':100},10)
    assert [x['target'] for x in r['sections']]==[2200,3900,3000,800,100]
    assert r['to_add']==900
    with pytest.raises(ValueError): domain.stadium_plan(-2,{},9)

def test_csv_export_neutralizes_formulas():
    result=domain.csv_export([{'name':'=HYPERLINK("evil")','age':16,'note':'+SUM(A1)'}])
    assert "'=HYPERLINK" in result
    assert "'+SUM" in result
