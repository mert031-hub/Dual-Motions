"""Conservative Turkish rule routing; engineering heuristics, not clinical assessment.

Context changes a keyword-only emergency into a guided present-needs check, never
into a declaration of safety. Every clause/match is considered independently.
"""
import re

from red_flags import RED_FLAG_RULES, _fold

ROUTING_VERSION = 'tr-context-rules.v1'
# Separate affirmative clauses: a denial/history must not suppress the next claim.
_BOUNDARY = re.compile(r'[.!?;,\n]+|\s+\b(?=ve\b|ama\b|fakat\b|ancak\b|simdi\b|bugun\b|su an\b|artik\b)')
_REMOTE_PAST = re.compile(r'\b(?:gecen yil|gecen ay|eskiden|gecmiste|yillar once|cocukken)\b')
_FICTION = re.compile(r'\b(?:romandaki|kitaptaki|filmdeki|romanda|kitapta|filmde|karakter|karakterin|alinti)\b')
_EDUCATION = re.compile(r'\b(?:kelimesi|cumlesi|ifadesi|terimi|cevirisi|nasil cevrilir)\b|\b(?:halusinasyon|dehidratasyon|intihar|malnutrisyon) (?:nedir|ne demek)\b')
_OTHER = re.compile(r'\b(?:arkadasim|annem|babam|kardesim|esim|komsum|hastam|birisi)\b')
_SELF_RESET = re.compile(r'^\s*(?:ama\s+|fakat\s+|ancak\s+)?(?:ben\b|simdi\b|bugun\b|su an\b|artik\b)')
_REPORTED_NOW = re.compile(r'\b(?:diyor|soyluyor|mesaj atti|az once|simdi|su an)\b')
_TECH = re.compile(r'\b(?:program|oyun|uygulama|bilgisayar|sunucu|yazilim|kod|tarayici)\w*\b')
_SUBSTANCE = re.compile(r'\b(?:kokain|madde|uyusturucu|alkol)\w*\b')
_EPISODIC = re.compile(r'\b(?:her seferinde|her defasinda|oldugunda|olunca|cikarsam|gidersem|kalksam|onceki hafta)\b')

# These are source-informed linguistic examples, NOT guideline diagnostic criteria.
# (category, expression, action override, evidence reference)
PATTERNS = [
    ('active_self_harm', r'\b(?:kendimi oldurecegim|kendime zarar verecegim|intihar edecegim)(?:den|i)?\b', None, 'NG222:1.2.8-9'),
    ('active_self_harm', r'\b(?:kendimi oldurmek|kendime zarar vermek|intihar etmek) (?:istiyorum|istiyordum|istemiyorum|istemiyordum|uzereyim|niyetindeyim|planliyorum)\b', None, 'NG222:1.2.8-9'),
    ('active_self_harm', r'\b(?:kendimi oldurmeye|kendime zarar vermeye|intihar etmeye) karar verdim\b', None, 'NG222:1.2.8-9'),
    ('active_self_harm', r'\b(?:kendimi oldurmeyecegim|kendime zarar vermeyecegim|intihar etmeyecegim)\b', 'uncertain_check_in', 'NG225:1.6.5-6'),
    ('active_self_harm', r'\bkendime zarar verme dusuncesi\b|\bkendimi oldurme (?:istegi|istegim)\b', 'ask_safety_question', 'NG222:1.2.8'),
    ('violence_risk', r'\b(?:ona|birine|bebegime|cocuguma|esime|arkadasima|baskasina) zarar (?:verecegim|vermek (?:istiyorum|istemiyorum|istiyordum))\b', None, 'CG31:1.4.1.2-3'),
    ('violence_risk', r'\b(?:onu|bebegimi|cocugumu|esimi|birini) (?:oldurecegim|oldurmek istiyorum|bicaklamak istiyorum)\b', None, 'CG31:1.4.1.2-3'),
    ('violence_risk', r'\bya (?:\w+ ){0,6}(?:bicaklarsam|oldurursem|zarar verirsem|atarsam)\b', 'uncertain_check_in', 'CG31:1.4.1.3'),
    ('passive_death_wish', r'\bsabah(?: bir daha)?(?: hic)? uyanmasam\b|\bolsem(?: de)? kurtulsam\b|\bsonsuza kadar uyumak\b', 'ask_safety_question', 'NG222:1.2.8'),
    ('psychosis', r'\b(?:ic )?organlarim(?:in)? curu(?:dugunu|du|mus)\b', None, 'NG222:1.12.1'),
    ('active_self_harm', r'\bkendimi (?:yaraladim|kestim)\b|\bkendime zarar verdim\b', 'injury_check_in', 'NG225:1.7.2-4'),
    ('active_self_harm', r'\bkendini (?:yaraladi|kesti)\b', 'injury_check_in', 'NG225:1.7.2-4'),
    ('severe_functional_decline', r'\b(?:ise gidemiyorum|yataktan cikamiyorum|dukkani acamiyorum|gunluk islerimi yurutemiyorum)\b', 'urgent_human_support', 'NG222:1.2.6-7'),
    ('acute_physical_need', r'\bkanama(?:m|si|miz)? (?:durmuyor|devam ediyor)\b', 'immediate_medical', 'NG225:1.7.2-4'),
    ('acute_physical_need', r'\b(?:cok fazla|fazla|bir suru|bir avuc|asiri miktarda) (?:ilac|hap) (?:aldim|ictim|yuttum)\b', 'immediate_medical', 'NG225:definition;1.7.2-4'),
    ('acute_physical_need', r'\bnefes (?:alamiyorum|alamiyor|almakta zorlaniyorum|almakta zorlaniyor)\b', 'immediate_medical', 'CG113:1.3.6'),
    ('acute_physical_need', r'\bbayilacak gibi(?: oluyorum| hissediyorum)?\b', 'physical_check_in', 'NG69:1.10.3'),
    ('acute_physical_need', r'\b(?:sivi alamiyorum|su icemiyorum|sivi icemiyorum|gogsum agriyor)\b', 'physical_check_in', 'CG113:1.3.6;NG69:1.10.3'),
]
_COMPILED = [(name, re.compile(pattern), action, ref) for name, pattern, action, ref in PATTERNS]
_COMPILED += [(name, re.compile(r'(?<!\w)' + re.escape(_fold(keyword)) + r'(?!\w)'), None, 'legacy_keyword_unvalidated')
              for name, rule in RED_FLAG_RULES.items() for keyword in rule['keywords']]
_QUOTES = re.compile(r'"[^"]*"|(?<!\w)\'[^\']+\'(?!\w)')


def _clauses(text):
    # Punctuation and conjunctions INSIDE a quotation must retain the speaker frame.
    spans = [m.span() for m in _QUOTES.finditer(text)]
    last = 0
    for boundary in _BOUNDARY.finditer(text):
        if any(start <= boundary.start() < end for start, end in spans):
            continue
        yield text[last:boundary.start()], last
        last = boundary.end()
    yield text[last:], last



def _context(clause, match, inherited_other=False):
    before, after = clause[:match.start()], clause[match.end():]
    # Negative intent is tied to this matched assertion, not any 'yok' in the message.
    negative = bool(re.search(r'\b(?:istemiyorum|istemiyordum|etmeyecegim|vermeyecegim|oldurmeyecegim)\b', match.group())
                    or re.match(r'\s*(?:diye\s+)?(?:demiyorum|demedim|soylemiyorum|istemiyorum|istemiyordum|gormuyorum|duymuyorum|yasamiyorum|yok|degil)\b', after))
    hypothetical = bool(match.group().startswith('ya ')
                        or re.search(r'\bvarsayalim(?: ki)?\s*$', before)
                        or re.match(r'\s+diye kork(?:uyorum|ardim)\b', after)
                        or re.match(r'\s+istemeden\b', after)
                        or (match.group().endswith('den') and re.match(r'\s+korkuyorum\b', after))
                        or re.search(r'\b(?:istemeden|istemedigim)\b', before))
    quoted = any(m.start() <= match.start() < m.end() for m in _QUOTES.finditer(clause))
    educational = bool((_EDUCATION.search(clause) and quoted)
                       or (_FICTION.search(before) and (quoted or re.search(r'\b(?:diyor|dedi|demis|soyluyor)\b', after)))
                       or (match.group() in {'halusinasyon', 'dehidratasyon', 'intihar', 'malnutrisyon'}
                           and re.match(r'\s+(?:nedir|ne demek)\b', after)))
    # An unrelated past event earlier in the message does not date this assertion.
    historical = bool(re.fullmatch(r'\s*(?:ve\s+)?(?:gecen yil|gecen hafta|gecen ay|gecen gece|eskiden|gecmiste|yillar once|cocukken|dun)(?:\s+ben)?\s*', before)
                      or re.match(r'\s*(?:diye\s+)?(?:dedim|demistim|demisti|demis|diyordum|dusunuyordum|derdim|istiyordum|duyuyordum)\b', after.strip(' \"\''))
                      or re.search(r'\b(?:istiyordum|istemiyordum)\b', match.group()))
    reported = quoted or bool(re.search(r'\b(?:diyor|soyluyor|dedi|demis|demisti|yazdi|yaziyor)\b', after))
    third_person_form = bool(re.search(r'\b(?:kendini|kanamasi|alamiyor|zorlaniyor)\b', match.group()))
    other = bool((_OTHER.search(before) and (reported or third_person_form)) or
                 (inherited_other and (quoted or third_person_form)))
    # Bare quotation marks alone never disarm a direct present threat.
    if educational:
        status = 'quoted_or_educational'
    elif negative:
        status = 'negated_assertion'
    elif hypothetical:
        status = 'hypothetical_or_intrusive'
    elif historical:
        status = 'historical_report'
    elif other:
        status = 'other_person'
    else:
        status = 'current_or_unspecified'
    return status, other


def _fold_with_offsets(message):
    normalized, offsets = [], []
    for index, char in enumerate(message):
        if char.isspace():
            if normalized and normalized[-1] != ' ':
                normalized.append(' ')
                offsets.append([index, index + 1])
            elif offsets and normalized[-1] == ' ':
                offsets[-1][1] = index + 1
            continue
        folded = _fold(char)
        if not folded and offsets:
            offsets[-1][1] = index + 1
        for token in folded:
            normalized.append(token)
            offsets.append([index, index + 1])
    if normalized and normalized[-1] == ' ':
        normalized.pop()
        offsets.pop()
    return ''.join(normalized), offsets


def observe_rule_matches(message):
    """All matches + exact original-text evidence, before same-category selection.

    Retain only in memory unless text-enabled storage is explicitly intended.
    """
    message = message or ''
    normalized, offsets = _fold_with_offsets(message)
    observations = []
    inherited_other = False
    other_origin = None
    episodic_frame = False
    episode_origin = None
    episode_other = False
    for clause, clause_offset in _clauses(normalized):
        if not clause.strip():
            continue
        if _SELF_RESET.search(clause):
            inherited_other = False
            other_origin = None
            episodic_frame = False
            episode_origin = None
        if _EPISODIC.search(clause) and not (_FICTION.search(clause) or _EDUCATION.search(clause)):
            quoted_spans = [m.span() for m in _QUOTES.finditer(clause)]
            if any(not any(start <= m.start() < end for start, end in quoted_spans)
                   for m in _EPISODIC.finditer(clause)):
                episodic_frame = True
                episode_origin = (clause_offset, len(clause))
                episode_other = bool(_OTHER.search(clause))
        for rule_index, (name, regex, action, reference) in enumerate(_COMPILED):
            for match in regex.finditer(clause):
                if name == 'substance_withdrawal' and match.group() == 'crash' and _TECH.search(clause) and not _SUBSTANCE.search(clause):
                    continue
                rule = RED_FLAG_RULES[name]
                chosen = action or rule['action']
                status, other = _context(clause, match, inherited_other)
                if status == 'quoted_or_educational':
                    chosen = 'contextual_information'
                elif status == 'negated_assertion':
                    chosen = 'uncertain_check_in'
                elif status == 'hypothetical_or_intrusive':
                    # Fear ABOUT a stated physical symptom does not cancel that symptom.
                    if chosen != 'immediate_medical' or re.search(r'\bvarsayalim\b', clause):
                        chosen = 'uncertain_check_in'
                elif status == 'historical_report':
                    # Recent/unspecified poisoning or physical symptoms are not ruled out by 'yesterday'.
                    if chosen != 'immediate_medical' or _REMOTE_PAST.search(clause):
                        chosen = 'uncertain_check_in'
                elif other:
                    if chosen == 'crisis_escalation':
                        chosen = 'urgent_other_safety' if _REPORTED_NOW.search(clause) else 'uncertain_check_in'
                    elif chosen not in {'immediate_medical', 'injury_check_in', 'physical_check_in'}:
                        chosen = 'uncertain_check_in'
                if (name == 'acute_physical_need' and status in {'current_or_unspecified', 'other_person'}
                        and episodic_frame and episode_other == other
                        and (match.group().startswith('nefes ') or match.group().startswith('bayilacak'))):
                    # A conditional/recurrent description needs current-symptom clarification;
                    # it must not be assumed to be happening at this moment.
                    chosen = 'physical_check_in'
                    status = 'episodic_or_temporally_qualified'
                # Past behavior/anger terms do not by themselves establish present violent intent.
                if name == 'violence_risk' and match.group() in {'masayi devirdim', 'kitaplari firlattim', 'ofke patlamalari'}:
                    chosen = 'uncertain_check_in'
                if match.group() == 'yogun intihar dusunceleri' and status == 'current_or_unspecified':
                    chosen = 'ask_safety_question'
                if match.group() == 'crash' and not _SUBSTANCE.search(clause):
                    chosen = 'uncertain_check_in'
                item = {'name': name, 'description': rule['description'], 'risk_level': rule['risk_level'],
                        'action': chosen, 'matched_keyword': match.group(), 'routing_version': ROUTING_VERSION,
                        'context_status': status, 'routing_reference': reference}
                start = offsets[clause_offset + match.start()][0]
                end = offsets[clause_offset + match.end() - 1][1]
                context_start = offsets[clause_offset][0]
                context_end = offsets[clause_offset + len(clause) - 1][1]
                context_evidence = [{'quote': message[context_start:context_end],
                                     'start': context_start, 'end': context_end}]
                antecedents = []
                if other and inherited_other and other_origin:
                    antecedents.append(other_origin)
                if status == 'episodic_or_temporally_qualified' and episode_origin:
                    antecedents.append(episode_origin)
                for origin, length in antecedents:
                    start_frame, end_frame = offsets[origin][0], offsets[origin + length - 1][1]
                    evidence = {'quote': message[start_frame:end_frame], 'start': start_frame, 'end': end_frame}
                    if evidence not in context_evidence:
                        context_evidence.append(evidence)
                item.update(rule_id=f'{ROUTING_VERSION}:{rule_index}',
                            evidence=[{'quote': message[start:end], 'start': start, 'end': end}],
                            context_evidence=context_evidence)
                observations.append(item)
        # Retain a concrete third-person subject across a sentence; explicit self/current reset releases it.
        if _OTHER.search(clause) and not _FICTION.search(clause):
            inherited_other = True
            other_origin = (clause_offset, len(clause))
    # Faintness alone is not a validated threshold for emergency classification.
    # Concurrent inability to take fluids and faintness warrant conservative urgent
    # medical help, without claiming dehydration or inferring suicidal intent.
    current_physical = [o for o in observations if o['name'] == 'acute_physical_need'
                        and o['context_status'] == 'current_or_unspecified']
    fluid = next((o for o in current_physical if o['matched_keyword'] in
                  {'sivi alamiyorum', 'su icemiyorum', 'sivi icemiyorum'}), None)
    faint = next((o for o in current_physical if o['matched_keyword'].startswith('bayilacak')), None)
    if fluid and faint:
        faint['action'] = 'immediate_medical'
        faint['context_status'] = 'combined_current_physical_need'
        faint['routing_reference'] = 'NG69:1.10.3;engineering_precaution_not_a_validated_threshold'
        faint['context_evidence'] += [e for e in fluid['context_evidence'] if e not in faint['context_evidence']]
    return observations


def detect_contextual_flags(message):
    # One source of action priorities: the same schema used by the actual router.
    from triage import _schema_for
    found = {}
    for item in observe_rule_matches(message):
        name = item['name']
        if name not in found or _schema_for(item)['priority'] > _schema_for(found[name])['priority']:
            found[name] = item
    return list(found.values())
