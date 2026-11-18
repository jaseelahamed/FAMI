"""Compare saved OCR reports to the manually inspected test-photo reference.
This evaluator never feeds expected values back into the application.
"""
import json
import re
from pathlib import Path

ROOT=Path('testing_results')

def norm(value):
    return re.sub(r'[^a-z0-9]', '', value.lower())

def month_values(value):
    months='jan feb mar apr may jun jul aug sep oct nov dec'.split()
    for number,month in enumerate(months,1):
        value=re.sub(month+r'[a-z]*[ ./:\-]*',str(number)+'/',value,flags=re.I)
    return re.findall(r'(?:0?[1-9]|1[0-2])[ ./:\-]+20\d{2}',value)

def date_norm(value):
    vals=month_values(value)
    return [re.sub(r'\D','',v).lstrip('0') for v in vals]

def compare(reference,report):
    checks=report['regulatory_validation']['field_checks']; results={}
    expected={
      'Generic Name':reference['expected_generic_terms'],
      'Dosage Form and Strength':reference['expected_strengths'],
      'Active Ingredients in Metric Units':reference['expected_generic_terms']+reference['expected_strengths'],
      'Name and Address of Manufacturer':[reference['expected_manufacturer']],
      'Batch / Lot Number':[reference['expected_batch']],
      'Mfg License Number':[reference['expected_primary_licence']],
    }
    for name,visible in reference['presence'].items():
        item=checks[name]; value=item['extracted_value'];status=item['status']
        missed=value.startswith('Not Detected') or value.startswith('Not detected')
        if visible=='requires_measurement':
            verdict='MEASUREMENT REVIEW'
        elif visible=='activity_units_only':
            verdict='UNIT REVIEW (activity units, not metric mass)'
        elif visible=='not_visible':
            verdict='FALSE POSITIVE' if status=='PASS' else 'NO VISIBLE FIELD; correctly not passed'
        elif missed:
            verdict='MISSED VISIBLE FIELD'
        elif name in expected and not all(norm(x) in norm(value) for x in expected[name]):
            verdict='INCORRECT / INCOMPLETE VALUE'
        elif name=='Mfg Date / Expiry Date' and not all(date_norm(x) and date_norm(x)[0] in date_norm(value) for x in reference['expected_dates']):
            verdict='INCORRECT / INCOMPLETE VALUE'
        elif status=='REVIEW':
            verdict='EXTRACTED; REVIEW REQUIRED'
        else:
            verdict='EXTRACTED (reference terms matched)' if name in expected or name=='Mfg Date / Expiry Date' else 'DETECTED (presence only; full text not scored)'
        results[name]={'finding':verdict,'status':status,'value':value,'notes':item.get('review_notes',[])}
    return results

def main():
    refs=json.loads((ROOT/'visual_reference.json').read_text())['images']
    output=[]
    for ref in refs:
        row={'image':ref['image'],'brand':ref['brand'],'reference_notes':ref['notes']}
        for run in ('baseline','final'):
            p=ROOT/run/(Path(ref['image']).stem+'.json')
            if p.exists():
                report=json.loads(p.read_text())
                if 'error' not in report:
                    row[run]={'engine':report['ocr_engine'],'seconds':report['elapsed_seconds'],'fields':compare(ref,report)}
        output.append(row)
    (ROOT/'comparison.json').write_text(json.dumps(output,indent=2,ensure_ascii=False))
    lines=['MEDICINE LABEL PHOTO AUDIT','',
      'Nine supplied photos. Visual reference concerns only the photographed face.',
      'This is an extraction audit, not regulatory certification or a general accuracy benchmark.',
      'Reference-term matches do not establish that every word of a field is correct.',
      'Font measurements and activity-unit interpretation remain manual review items.','']
    from collections import Counter
    for stage in ('baseline','final'):
        counts=Counter(item['finding'] for row in output if stage in row for item in row[stage]['fields'].values())
        lines += [stage.upper()+': '+', '.join(str(counts[k])+' '+k.lower() for k in ('MISSED VISIBLE FIELD','INCORRECT / INCOMPLETE VALUE','FALSE POSITIVE'))]
    lines += ['', 'Remaining common limitations:',
      '- Font-size compliance is unmeasured on all nine images.',
      '- High OCR confidence still permits character errors; detected does not mean exact transcription.',
      '- Rx glyphs, sideways stamps, small manufacturer print and warning text remain difficult.',
      '- Some fields have only reference terms checked, not full verbatim text (especially warnings and addresses).',
      '- Larger v6 models were trialled on two photos only; they were slower and still made errors. Default remains v5 mobile.',
      '- Final field parsing was revalidated from unchanged saved OCR regions after parser fixes.', '']
    for row in output:
        lines += [row['brand']+' — '+row['image'],row['reference_notes']]
        if 'final' not in row:
            lines += ['Final run not available',''];continue
        lines += [f"Engine: {row['final']['engine']}; processing: {row['final']['seconds']} seconds"]
        for i,(name,result) in enumerate(row['final']['fields'].items(),1):
            old=row.get('baseline',{}).get('fields',{}).get(name,{})
            lines += [f"{i}. {name}: {result['finding']}",f"   Output [{result['status']}]: {result['value']}",f"   Baseline: {old.get('finding','unavailable')}"]
            lines.extend('   Note: '+note for note in result['notes'])
        lines += ['']
    (ROOT/'audit_report.txt').write_text('\n'.join(lines))
    for row in output:
        if 'final' in row:
            issues=[name for name,item in row['final']['fields'].items() if item['finding'] in ('MISSED VISIBLE FIELD','INCORRECT / INCOMPLETE VALUE','FALSE POSITIVE')]
            print(row['brand'],':', '; '.join(issues) or 'No scored field mismatches')

def revalidate_saved_reports():
    """Re-run only field validation against the saved, unchanged OCR evidence."""
    from app import MedicineLabelValidator
    for p in (ROOT/'final').glob('*.json'):
        report=json.loads(p.read_text())
        validator=MedicineLabelValidator.__new__(MedicineLabelValidator)
        validator.ocr_lines=report['ocr_lines']
        validator.ocr_data=None  # Paddle did not supply individual word metrics.
        validator.barcode_results=report['barcode_detection']
        validator.redline_results=report['redline_detection']
        report['regulatory_validation']=validator.validate_regulatory_fields(report['ocr_text_full'])
        report['font_ratio_analysis']=validator.font_ratio_results
        report['audit_note']='Field parsing revalidated against unchanged saved PaddleOCR text and coordinates; elapsed_seconds is the original full scan time.'
        p.write_text(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__':
    import sys
    if '--revalidate' in sys.argv:
        revalidate_saved_reports()
    main()
