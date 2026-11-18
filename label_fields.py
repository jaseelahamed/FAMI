"""Extract bounded label fields, preserving OCR evidence and line boundaries."""
import re
from difflib import SequenceMatcher


def normalize_composition(value, generic_name):
    """Correct close OCR spellings; preserve every numeric quantity and unit."""
    value = re.sub(r"\bgeiatin\b", "gelatin", value, flags=re.I)
    value = re.sub(r"\bcapsuie\b", "capsule", value, flags=re.I)
    value = re.sub(r"\beguivalent\b", "equivalent", value, flags=re.I)
    value = re.sub(r"(?<!\w)[|1]\.P\.", "I.P.", value)
    if re.fullmatch(r"[A-Za-z-]{6,}", generic_name):
        # The ingredient can be split into two OCR tokens, e.g. Cli ivamycin.
        pattern = r"\b([A-Za-z]+(?:[ .]+[A-Za-z]+)?)\s+(?=Hydrochloride\b)"
        def correct(match):
            candidate = re.sub(r"[^a-z]", "", match.group(1).lower())
            if SequenceMatcher(None, candidate, generic_name.lower()).ratio() >= 0.78:
                return generic_name + " "
            return match.group(0)
        value = re.sub(pattern, correct, value, flags=re.I)
        # Dot leaders between the repeated ingredient name and its amount are
        # sometimes read as "wu...". Remove that filler without changing digits.
        value = re.sub(
            r"(\b" + re.escape(generic_name) + r")\s+(?:[wuv]+\s*)?\.{2,}\s*(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu)\b)(?:\s+SO)?",
            r"\1 \2", value, flags=re.I)
    return value


def extract_fields(text, ocr_lines=None):
    lines = [re.sub(r"\s+", " ", line).strip(" |—_~") for line in text.splitlines() if line.strip()]
    fields = {}
    measured = {}
    for r in ocr_lines or []:
        if "box" not in r or "source" not in r:
            continue
        measured.setdefault(re.sub(r"\s+", " ", r['text']).strip(" |—_~"), r)
    def normalized(line):
        line = re.sub(r"(?<=IP)(?=\d)", " ", line)
        line = re.sub(r"(?<=[a-z])(?=Tablets?\b|Capsules?\b)", " ", line)
        line = re.sub(r"(?i)(?<=\w)(tablets?|capsules?)(?=I[ .]?P\b)", r" \1 ", line)
        line = re.sub(r"(?i)(?<=\w)(?=MFG[ .:]|EXP[ .:]|MRP[ .:])", " ", line)
        line = re.sub(r"-\s*-", "-", line)
        line = re.sub(r"(?i)retall", "retail", line)
        # Correct bounded header/label OCR confusions, never numeric values.
        header = re.match(r"([A-Za-z]+)(\s+in\s+(?:India|Indla)\s+by\b)", line, re.I)
        if header and SequenceMatcher(None, header[1].lower(), 'manufactured').ratio() >= .68:
            line = 'Manufactured in India by' + line[header.end():]
        line = re.sub(r"(?i)\b(?:MHG|MEG)(?=[ .:]*(?:DATE[ .:]*)?[A-Z]{3}[ .:]*20\d{2})", "MFG", line)
        line = re.sub(r"(?i)(MFG[ .:]*)FE8(?=[ .:]*20\d{2})", r"\1FEB", line)
        line = re.sub(r"(?i)(EXP[ .:]*)ARR(?=[ .:]*20\d{2})", r"\1APR", line)
        return line


    def put(name, value, ids):
        fields[name] = {"value": value.strip(), "lines": [lines[i] for i in ids]}

    def first(name, pattern):
        for i, line in enumerate(lines):
            match = re.search(pattern, normalized(line), re.I)
            if match:
                put(name, match.group(0), [i])
                return match
        return None

    def section(name, start, stop, limit):
        for i, line in enumerate(lines):
            match = re.search(start, normalized(line), re.I)
            if not match:
                continue
            ids = [i]
            candidates = list(range(i + 1, len(lines)))
            anchor = measured.get(line)
            if anchor and anchor.get('recovered_field') == name:
                put(name, line, [i])
                return
            if anchor and anchor['source'] != 'paddle_rotated':
                x,y,w,h = anchor['box']
                candidates = [j for j in candidates if lines[j] in measured
                              and (measured[lines[j]]['source'] != 'paddle_rotated' or measured[lines[j]]['box'][2] > measured[lines[j]]['box'][3])
                              and measured[lines[j]]['box'][1] > y + h*.4
                              and (abs(measured[lines[j]]['box'][0]-x) < max(h*3,w*.4) or (name == "active" and measured[lines[j]]['box'][0] < x+w*3 and re.fullmatch(r"(?:I\.?P\.?|B\.?P\.?|USP)?\s*"+strength+r"\.?",lines[j],re.I)))
                              and measured[lines[j]]['box'][1]-y < h*22]
            for j in candidates[:limit-1]:
                if anchor and lines[j] in measured:
                    current=measured[lines[j]]['box']
                    previous=measured.get(lines[ids[-1]],anchor)['box']
                    if current[1]-(previous[1]+previous[3]) > anchor['box'][3]*2.5 or current[3]>anchor['box'][3]*1.8:
                        break
                if re.search(stop, lines[j], re.I) and not (name == "active" and re.match(r"each\b", lines[j], re.I)):
                    break
                ids.append(j)
            put(name, " ".join([line[match.start():]] + [lines[j] for j in ids[1:]]), ids)
            return

    form = r"tablets?|capsules?|syrup|injection|suspension|ointment|gel|drops?"
    strength = r"\b\d+(?:\.\d+)?\.?\s*(?:mg|mcg|µg|g|ml|iu|%)(?!\w)"
    heights=sorted(r['box'][3] for r in measured.values() if r['source']!='paddle_rotated')
    body_height=heights[len(heights)//2] if heights else 0
    generic = None
    # Names may span several large heading lines. Never infer a generic name
    # from dosage prose, colour ingredients, or a brand-only tablet line.
    excluded = r"\b(each|hard|film|coated|per|of|for|contains|shell|use|colou?rs?|excipients|dosage)\b"
    candidates = []
    for i, raw in enumerate(lines):
        line = normalized(raw)
        match = re.search(rf"\b({form})(?![a-z])", line, re.I)
        if not match:
            continue
        prefix = line[:match.start()].strip(' .,:')
        ids = [i]
        if not prefix or prefix.startswith('&') or re.fullmatch(r'Hydrochloride|Sustained Release',prefix,re.I):
            anchor = measured.get(raw)
            previous = list(range(max(0,i-3),i))
            if anchor:
                x,y,w,h=anchor['box']
                previous=[j for j in range(i) if lines[j] in measured
                          and measured[lines[j]]['source'] != 'paddle_rotated'
                          and 0 < y-measured[lines[j]]['box'][1] < h*3.5
                          and measured[lines[j]]['box'][3] >= h*.65
                          and min(abs(measured[lines[j]]['box'][0]-x), abs(measured[lines[j]]['box'][0]+measured[lines[j]]['box'][2]/2-x-w/2)) < max(w*.3,h*2)]
            # At most two preceding title lines; don't walk back into body text.
            chosen=[]
            for j in reversed(previous[-2:]):
                if re.search(excluded,lines[j],re.I) or re.search(r"[:@®™]|\d",lines[j]):
                    break
                chosen.insert(0,j)
            if chosen:
                prefix=' '.join(lines[j] for j in chosen)+' '+prefix
                ids=chosen+ids
        prefix=re.sub(r"^(?:Rx|℞)\s*",'',prefix).strip()
        if prefix and not re.search(excluded,prefix,re.I) and not re.search(r"\d|[®™@]",prefix):
            # Brand headings generally lack a pharmacopoeia suffix and have no
            # matching ingredient occurrence elsewhere on the label.
            has_standard=bool(re.search(r"\b(?:I\.?P|USP|BP)\b",line[match.end():],re.I))
            repeated=any(prefix.lower() in other.lower() for j,other in enumerate(lines) if j not in ids)
            parts=[part for part in re.split(r"[ &,()-]+",prefix.lower()) if part]
            if len(parts)>=2 and all(len(part)>3 for part in parts):
                repeated = repeated or all(any(re.search(r"\b"+re.escape(part)+r"\b",other,re.I)
                    for j,other in enumerate(lines) if j not in ids) for part in parts)
            large_title = bool(body_height and measured.get(raw,{}).get('box',[0,0,0,0])[3] > body_height*1.7 and not prefix.isupper())
            if large_title or has_standard or (repeated and not (prefix.isupper() and "-" in prefix)) or '&' in prefix or ',' in prefix:
                height=measured.get(raw,{}).get('box',[0,0,0,1])[3]
                candidates.append((height, prefix,match.group(),ids))
        if 'form' not in fields:
            put('form',match.group(),[i])
    if candidates:
        _,name,dosage_form,ids=max(candidates,key=lambda c:c[0])
        put('generic',name,ids)
        put('form',dosage_form,ids)

    for i, line in enumerate(lines):
        if re.search(rf"\b({form}|schedule|lot|exp|mfg)\b", line, re.I):
            continue
        match = re.search(r"^([A-Z][A-Z0-9-]*(?:\s+[A-Z][A-Z-]*){0,3})\s*[®™]?\s*[- ]?\s*\d{2,4}\b", line)
        if match:
            put("brand", match.group(1), [i])
            dose = re.search(strength, line, re.I)
            if dose and "strength" not in fields:
                put("strength", dose.group(), [i])
            break

    stop = r"\b(?:store|keep|dosage|directions|each|composition|manufactured|imported|marketed|licen[cs]e|excipients?|colou?rs?|colo\w{1,3}\s+used|schedule|maximum|trademark|licensed user)\b"
    section("active", r"\b(?:each\b.*?contains?\s*:?|composition\s*:?$|contains?\s*:)", stop, 16)
    if "active" in fields and not re.search(strength, fields["active"]["value"], re.I):
        fields["active"]["uncertain"] = True
    if "active" in fields:
        raw = fields["active"]["value"]
        fields["active"]["raw_value"] = raw
        fields["active"]["value"] = normalize_composition(raw, fields.get("generic", {}).get("value", ""))
    section("manufacturer", r"\b(?:manufactured(?:\s+in\s+india)?|mf[gd][ .:]*)\s*by\s*:?[ ]*", r"\b(?:imported|marketed|maximum|licensed|licen[cs]e|lic|storage|store|batch|mf[gdt]|exp|manufactured\s+in\s+india|manuf\w*inn)\b", 7)
    first("licence", r"\b(?:(?:mfg\.?|manufacturing|import)\s*)?(?:licen[cs]e|lic\.?)\s*(?:no\.?)?\s*[:.,-]*\s*[A-Z0-9][A-Z0-9/-]{3,30}")
    if 'licence' in fields and not re.search(r"\d",fields['licence']['value']):
        fields['licence']['uncertain']=True
    first("batch", r"\b(?:b\.?\s*no\.?|batch\s*(?:no\.?|number)?|lot\s*(?:no\.?|number)?)\s*[:.-]?\s*(?=[A-Z0-9/-]*\d)[A-Z0-9][A-Z0-9/-]{3,20}")
    if 'batch' not in fields:
        candidate = first('batch', r"^[A-Z][A-Z0-9/-]{4,24}(?=\s+M\.?\s*R\.?\s*P\b)")
        if candidate:
            fields['batch']['uncertain'] = True
    month = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    if 'batch' not in fields:
        candidate=first('batch',r"^(?:\.?NO\.)?[A-Z0-9][A-Z0-9/-]{4,24}(?=\s+MFG)")
        if candidate:
            fields['batch']['uncertain']=True
    date = rf"(?:(?:0?[1-9]|1[0-2])[/.-](?:20\d{{2}}|\d{{2}})|{month}[ ./:-]*(?:20\d{{2}}|\d{{2}}))(?!\d)"
    first("mfg_date", rf"(?<![A-Z])(?:mfg\.?\s*(?:date)?|mfd\.?)\s*[:.-]?\s*{date}")
    first("exp_date", rf"(?<![A-Z])(?:exp\.?\s*(?:date)?|expiry\s*(?:date)?|use\s*before|best\s*before)\s*[:.-]?\s*{date}")
    storage_ids = []
    storage = []
    for i, line in enumerate(lines):
        match = re.search(r"\bstorage\s*(?:instructions)?\s*:|\b(?:store\s+(?:below|at|in|between|protected)|protect\s+from|keep\s+out\s+of\s+reach|do\s+not\s+freeze)\b", line, re.I)
        if match:
            value = line[match.start():]
            end = re.search(r"children\b|\d+\s*°?\s*C\b|moisture\b|(?<!\d)\.(?!\d)", value, re.I)
            storage.append(value[:end.end()] if end else value)
            storage_ids.append(i)
            for j in range(i+1,min(len(lines),i+4)):
                if not re.match(r"(?:below|at a|temperature|not exceeding|moisture|heat|dry place|place|protected|protect|and moisture)\b",lines[j],re.I):
                    break
                if line in measured and lines[j] in measured:
                    a,b=measured[line]['box'],measured[lines[j]]['box']
                    if abs(a[0]-b[0])>max(a[3]*3,a[2]*.4):
                        break
                storage.append(lines[j]);storage_ids.append(j)
    if storage:
        put("storage", "; ".join(dict.fromkeys(storage)), list(dict.fromkeys(storage_ids)))
    section("dosage", r"\b(?:for\s+dosages?|dosage\s*:|directions?\s+for\s+use|as\s+directed\s+by|for\s+(?:oral|external)\s+use)\b", stop, 2)
    if "dosage" in fields and re.search(r"as\s*directed", fields['dosage']['lines'][0], re.I):
        fields['dosage']['value']=fields['dosage']['lines'][0]
        fields['dosage']['lines']=fields['dosage']['lines'][:1]
    first("rx", r"(?<!\w)(?:N\s*Rx|X\s*Rx|R\s*x|℞)(?!\w)")
    section("warning", r"\bprescription\s+(?:drug|dhug)\s*[- ]*caution|\bcaut(?:i|l)?on\s*:?|\bschedule\s*[\'\"]?(?:h1?|x|g)\b|\bnot\s+to\s+be\s+sold\s+by\s+retail\s+without", r"\b(?:for\s+dosage|store|keep|each|composition|manufactured|b\.?no|batch|lot|mfg|exp)\b", 3)
    if 'warning' in fields and not re.search(r"schedule|prescri|prescrp",fields['warning']['value'],re.I):
        fields['warning']['uncertain']=True
    if 'rx' not in fields:
        possible=first('rx',r"^R\$$")
        if possible:
            fields['rx']['uncertain']=True
    # A composition names the generic ingredients even if a folded heading was
    # unreadable. Keep the exact source lines; do not substitute a drug dictionary.
    if 'active' in fields and ('generic' not in fields or fields['generic']['value'].lower() == 'hydrochloride'):
        ingredient_names=[]
        for line in fields['active']['lines'][1:]:
            if re.match(r"(?:each|\(|I\.?P|composition|excipients|colou?r|eq|eg|\d)",line,re.I):
                continue
            name=re.split(r"\s+(?:I\.?P\.?|B\.?P\.?|USP)\b|\s+\d",line,maxsplit=1,flags=re.I)[0].strip()
            if re.fullmatch(r"[A-Z][A-Za-z -]{3,70}",name) and len(name.split())<=4:
                ingredient_names.append(name)
        if ingredient_names:
            fields['generic']={'value':' + '.join(dict.fromkeys(ingredient_names)), 'lines':fields['active']['lines']}
    # Only use explicit product-heading quantities for this display field.
    # Composition quantities stay in active ingredients, even when they describe
    # amounts per tablet. Never overwrite a heading strength with those amounts.
    composition_lines = set(fields.get('active', {}).get('lines', []))
    if 'strength' in fields and any(line in composition_lines for line in fields['strength']['lines']):
        del fields['strength']
    if 'strength' not in fields:
        for i, line in enumerate(lines):
            if line in composition_lines or re.search(
                    r"\b(?:each|contains?|composition|dosage|directions|excipients?|per)\b", line, re.I):
                continue
            if re.search(rf"\b(?:{form})\b", normalized(line), re.I):
                doses = re.findall(strength, normalized(line), re.I)
                if doses:
                    put('strength', ' + '.join(dict.fromkeys(doses)), [i])
                    break
    return fields
