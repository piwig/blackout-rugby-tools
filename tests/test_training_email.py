"""Offline Classic training import tests with a wholly synthetic message."""
import re
from email import policy
from email.feedparser import FeedParser
from email.message import EmailMessage
from pathlib import Path

import pytest

from server.training_email import TrainingEmailError, parse_training_email


@pytest.fixture
def training_html():
    return (Path(__file__).parent / 'fixtures' / 'training-report.html').read_text(encoding='utf-8')


def parse(html, filename='training.html'):
    return parse_training_email(html.encode() if isinstance(html, str) else html, filename)


def test_two_phase_report_keeps_csr_player_links_sessions_and_trainer(training_html):
    result = parse(training_html)
    assert (result['schema_version'], result['report_id'], result['club_id']) == (2, None, None)
    assert (result['club_name'], result['season'], result['round']) == ('Example Club', 61, 8)
    assert result['provenance']['source'] == 'Classic email'
    assert result['provenance']['source_format'] == 'html'
    assert result['team']['skills'] == ['stamina', 'defense']
    player = result['team']['players'][0]
    assert (player['player_id'], player['player_name'], player['csr_before'], player['csr_after']) == ('101', 'Camille Démo', 10000, 10100)
    assert player['pops'] == [{'skill': 'defense', 'before': 7, 'after': 8}]
    assert result['team']['players'][1]['pops'] == []
    trained = result['individual']['players'][0]
    assert (trained['player_id'], trained['csr_before'], trained['csr_after']) == ('101', 10100, 10150)
    assert trained['skills'] == [{'skill': 'defense', 'sessions': 2, 'pops': [],
                                  'trainer': {'name': 'Coach Émile', 'level': 5, 'type': None}}]
    assert trained['energy'] == {'kind': 'label', 'before': 'Excellent', 'after': 'Good'}
    assert trained['energy_before'] is None and trained['energy_after'] is None


def test_text_skill_levels_are_preserved_without_an_inferred_scale(training_html):
    trained = parse(training_html)['individual']['players'][1]
    assert trained['skills'] == [{'skill': 'handling', 'sessions': 1, 'trainer': None,
                                  'pops': [{'skill': 'handling', 'before': None, 'after': None,
                                            'before_label': 'Fair', 'after_label': 'Good'}]}]
    assert trained.get('energy') is None


def test_missing_changes_are_unknown_and_explicit_no_pops_are_empty(training_html):
    result = parse(training_html.replace('<span>No pops</span>', '', 1))
    assert result['team']['players'][1]['pops'] is None
    assert result['individual']['players'][0]['skills'][0]['pops'] == []


def test_only_explicit_club_id_is_used(training_html):
    result = parse(training_html.replace('?page=training', '?page=training&amp;teamid=123'))
    assert result['club_id'] == '123'


@pytest.mark.parametrize('encoding,charset', [('quoted-printable', 'iso-8859-1'), ('base64', 'utf-8')])
def test_multipart_export_preserves_the_same_report(training_html, encoding, charset):
    msg = EmailMessage(policy=policy.SMTP)
    msg['Subject'] = 'Synthetic mailbox envelope'
    msg.set_content('This text is not the report.')
    msg.add_alternative(training_html, subtype='html', cte=encoding, charset=charset)
    msg.add_attachment(b'synthetic incidental data', maintype='application', subtype='octet-stream', filename='note.bin')
    eml = parse(msg.as_bytes(), 'mail.EML')
    html = parse(training_html)
    assert eml['provenance']['source_format'] == 'eml'
    assert [eml[k] for k in ('club_name', 'club_id', 'team', 'individual')] == [html[k] for k in ('club_name', 'club_id', 'team', 'individual')]


def test_unrelated_html_attachment_does_not_hide_report(training_html):
    msg = EmailMessage(policy=policy.SMTP)
    msg.set_content(training_html, subtype='html')
    msg.add_attachment('<html><body><script>Team Training</script><p>Plain attachment</p></body></html>', subtype='html', filename='notes.html')
    assert parse(msg.as_bytes(), 'mail.eml')['season'] == 61


def test_two_mime_reports_are_ambiguous_even_if_they_are_equal(training_html):
    msg = EmailMessage(policy=policy.SMTP)
    msg.set_content(training_html, subtype='html')
    msg.add_attachment(training_html, subtype='html', filename='report.html')
    with pytest.raises(TrainingEmailError, match='plusieurs'):
        parse(msg.as_bytes(), 'mail.eml')


def test_unknown_mime_transfer_encoding_cannot_pass_unencoded_html(training_html):
    msg = EmailMessage(policy=policy.SMTP)
    msg.set_content(training_html, subtype='html', cte='8bit')
    msg.replace_header('Content-Transfer-Encoding', 'x-unknown-training')
    with pytest.raises(TrainingEmailError):
        parse(msg.as_bytes(), 'mail.eml')


@pytest.mark.parametrize('encoding', ['7bit', '8bit', 'binary'])
def test_ordinary_mime_transfer_encodings_are_supported(training_html, encoding):
    msg = EmailMessage(policy=policy.SMTP)
    html = training_html.encode('ascii', 'xmlcharrefreplace').decode('ascii') if encoding == '7bit' else training_html
    if encoding == 'binary':
        msg.set_content(html.encode(), maintype='text', subtype='html', cte='binary', params={'charset': 'utf-8'})
    else:
        msg.set_content(html, subtype='html', cte=encoding)
    assert parse(msg.as_bytes(), 'mail.eml')['individual']['players'][0]['player_name'] == 'Camille Démo'


def without_player_cards(html, phase, marker):
    heading = f'<tr><td><span><b>{phase}</b></span></td></tr>'
    start, section = html.split(heading, maxsplit=1)
    following = ('<tr><td><span><b>Individual Training' if phase == 'Team Training'
                 else '<tr><td><a href="https://example.invalid/settings">')
    cards, boundary, end = section.partition(following)
    return start + heading + f'<tr><td>{marker}</td></tr>' + re.sub(r'<table>.*?</table>', '', cards, flags=re.S) + boundary + end


@pytest.mark.parametrize('phase,marker,field', [
    ('Team Training', 'No players', 'team'),
    ('Individual Training', 'No individual training', 'individual'),
])
def test_explicit_empty_phase_is_preserved(training_html, phase, marker, field):
    result = parse(without_player_cards(training_html, phase, marker))
    assert result[field]['players'] == []
    assert result['team']['skills'] == ['stamina', 'defense']


def test_empty_individual_marker_in_team_phase_is_rejected(training_html):
    with pytest.raises(TrainingEmailError):
        parse(without_player_cards(training_html, 'Team Training', 'No individual training'))


@pytest.mark.parametrize('phase,marker', [
    ('Team Training', 'No players'),
    ('Individual Training', 'No individual training'),
])
def test_empty_marker_with_player_cards_is_contradictory(training_html, phase, marker):
    heading = f'<tr><td><span><b>{phase}</b></span></td></tr>\n    <tr><td>'
    contradictory = training_html.replace(heading, heading + f'<span>{marker}</span>')
    assert contradictory != training_html
    with pytest.raises(TrainingEmailError):
        parse(contradictory)


@pytest.mark.parametrize('marker', ['No players<br>', '<em>No</em> <strong>players</strong><br/>'])
def test_empty_team_marker_on_its_own_html_line_conflicts_with_cards(training_html, marker):
    heading = '<span><b>Skills Trained</b></span>'
    contradictory = training_html.replace(heading, marker + heading, 1)
    assert contradictory != training_html
    with pytest.raises(TrainingEmailError):
        parse(contradictory)


def test_empty_marker_inside_player_card_does_not_empty_the_phase(training_html):
    player = 'Camille D&#xE9;mo</a>'
    report = parse(training_html.replace(player, player + '<br>No players', 1))
    assert [row['player_id'] for row in report['team']['players']] == ['101', '102']


def test_empty_team_marker_before_block_on_its_own_line_conflicts_with_cards(training_html):
    heading = '<span><b>Skills Trained</b></span>'
    contradictory = training_html.replace(heading, f'No players<div>{heading}</div>', 1)
    with pytest.raises(TrainingEmailError):
        parse(contradictory)


@pytest.mark.parametrize('mutation', [
    lambda s: s.replace('Individual Training', 'Unknown Phase'),
    lambda s: s.replace('Team Training', 'Individual Training'),
    lambda s: s.replace('round 8', 'round 17'),
    lambda s: s.replace('#player=101', '#page=player', 1),
    lambda s: s.replace('?player=102', '?player=101', 1),
    lambda s: s.replace('#player=101', '?player=102#player=101', 1),
    lambda s: s.replace('?page=training', '?teamid=123&amp;clubid=124'),
    lambda s: s.replace('popped from <b>7</b> to <b>8</b>', 'popped from <b>8</b> to <b>7</b>'),
    lambda s: s.replace('popped from <b>7</b> to <b>8</b>', 'popped from <b>7</b> to <b>8</b><br>No pops'),
    lambda s: s.replace('10,000</b>', '10,00</b>', 1),
    lambda s: s.replace('10,000</b>', '10,000.3</b>', 1),
    lambda s: s.replace('Camille Démo', 'Other Name', 1),
    lambda s: s.replace('</body></html>', ''),
    lambda s: s.replace('Your team (', 'Other report ('),
])
def test_incomplete_or_contradictory_report_is_rejected(training_html, mutation):
    with pytest.raises(TrainingEmailError):
        parse(mutation(training_html))


def test_csr_phase_discontinuity_is_available_to_the_summary(training_html):
    result = parse(training_html.replace('10,100</b>', '10,110</b>', 1))
    assert result['team']['players'][0]['csr_after'] == 10110
    assert result['individual']['players'][0]['csr_before'] == 10100


def test_hostile_elements_do_not_supply_markers_links_or_values(training_html):
    modified = training_html.replace('<body>', '<body><script>Individual Training</script><iframe src="https://example.invalid/frame"></iframe><style>Team Training</style><img src="https://example.invalid/trace">')
    assert parse(modified)['team'] == parse(training_html)['team']


def test_other_formats_and_text_only_mail_are_rejected(training_html):
    with pytest.raises(TrainingEmailError, match=r'HTML.*EML'):
        parse(training_html, 'opaque.txt')
    msg = EmailMessage(policy=policy.SMTP)
    msg.set_content('Your team (Fake) has completed weekly training.')
    with pytest.raises(TrainingEmailError):
        parse(msg.as_bytes(), 'mail.eml')


def test_raw_file_size_is_bounded():
    with pytest.raises(TrainingEmailError, match='taille'):
        parse(b'x' * (2 * 1024 * 1024 + 1))


def test_decoded_and_normalized_sizes_are_bounded(training_html, monkeypatch):
    latin = training_html.replace('utf-8', 'iso-8859-1').replace('<body>', '<body>' + ('é' * 1_100_000)).encode('iso-8859-1')
    with pytest.raises(TrainingEmailError, match='taille'):
        parse(latin)
    monkeypatch.setattr('server.training_email.MAX_DOCUMENT_BYTES', 200)
    with pytest.raises(TrainingEmailError, match='taille'):
        parse(training_html)


def test_mime_part_count_includes_irrelevant_parts(training_html):
    msg = EmailMessage(policy=policy.SMTP)
    msg.set_content(training_html, subtype='html')
    for _ in range(49):
        msg.add_attachment('Incidental')
    with pytest.raises(TrainingEmailError, match='limite'):
        parse(msg.as_bytes(), 'mail.eml')


def test_mime_depth_is_bounded(training_html):
    msg = EmailMessage(policy=policy.SMTP)
    msg.set_content(training_html, subtype='html')
    for _ in range(9):
        outer = EmailMessage(policy=policy.SMTP)
        outer.make_mixed()
        outer.attach(msg)
        msg = outer
    with pytest.raises(TrainingEmailError, match='limite'):
        parse(msg.as_bytes(), 'mail.eml')


@pytest.mark.parametrize('limit,allocated_limit', [('parts', 50), ('depth', 8)])
def test_mime_parser_stops_at_first_excess_object(training_html, monkeypatch, limit, allocated_limit):
    msg = EmailMessage(policy=policy.SMTP)
    msg.set_content(training_html, subtype='html')
    if limit == 'parts':
        for _ in range(60):
            msg.add_attachment('Incidental')
    else:
        for _ in range(15):
            outer = EmailMessage(policy=policy.SMTP)
            outer.make_mixed()
            outer.attach(msg)
            msg = outer
    raw = msg.as_bytes()
    original = FeedParser._new_message
    allocated = 0

    def observe_allocation(parser):
        nonlocal allocated
        original(parser)
        allocated += 1

    monkeypatch.setattr(FeedParser, '_new_message', observe_allocation)
    with pytest.raises(TrainingEmailError, match='limite'):
        parse(raw, 'mail.eml')
    assert allocated == allocated_limit


def test_player_and_skill_row_limits(training_html):
    card = training_html.split('<table>')[3].split('</table>')[0]
    bulk = ''.join('<table>' + card.replace('player=101', f'player={i}') + '</table>' for i in range(300, 500))
    with pytest.raises(TrainingEmailError, match='limite'):
        parse(training_html.replace('<ul><li>Stamina</li><li>Defense</li></ul>', '<ul><li>Stamina</li><li>Defense</li></ul>' + bulk))
    with pytest.raises(TrainingEmailError):
        parse(training_html.replace('<li><b>Handling</b><br><span>1 session</span></li>', '<li><b>Handling</b><br><span>1 session</span></li>' * 11))
