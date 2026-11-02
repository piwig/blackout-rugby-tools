from server.imports import normalize_player


def test_complete_observed_characteristics_and_large_scouting_stars_are_preserved():
    player=normalize_player({'id':'1','name':'Synthetic Junior','scouting_stars_used':'600',
                             'hand':'Left','foot':'Right','nat':'FR','u20':'IE',
                             'handling':'High','energy':0})
    assert player['stars']==600 and player['energy']==0 and player['handling']=='High'
    assert {k:player[k] for k in ('hand','foot','nat','u20')}=={'hand':'Left','foot':'Right','nat':'FR','u20':'IE'}
