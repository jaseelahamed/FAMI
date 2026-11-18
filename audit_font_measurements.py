"""Audit fresh font measurements using saved Paddle evidence for nine photos.
Run: python audit_font_measurements.py
The reference file supplies report labels only, never model inputs.
"""
import json,time
from pathlib import Path
from app import MedicineLabelValidator
out=Path('testing_results/font_heading_audit');out.mkdir(exist_ok=True)
refs=json.loads(Path('testing_results/visual_reference.json').read_text())['images']
summary=[]
for ref in refs:
 saved=json.loads((Path('testing_results/final')/(Path(ref['image']).stem+'.json')).read_text())
 v=MedicineLabelValidator(str(Path('static/uploads/TestingMedicineLabels')/ref['image']))
 v.ocr_lines=saved['ocr_lines'];v.ocr_engine='paddle'
 v.barcode_results=saved['barcode_detection'];v.redline_results=saved['redline_detection']
 text=saved['ocr_text_full']
 before=v.validate_regulatory_fields(text)
 start=time.monotonic();v.measure_font_words();after=v.validate_regulatory_fields(text)
 font='Generic Font Size >= Brand (Rule 96(1)(i))'
 changed=[k for k in before['field_checks'] if k!=font and before['field_checks'][k]!=after['field_checks'][k]]
 assert not changed, f'Non-font criteria changed: {changed}'
 r={'image':ref['image'],'brand':ref['brand'],'font':v.font_ratio_results,'other_criteria_changed':changed,'overall_status':after['overall_status'],'font_seconds':round(time.monotonic()-start,2),'method':'Fresh Tesseract font pass on image; existing Paddle text and detections replayed unchanged.','font_recognized_names':getattr(v,'font_ocr_names',{}),'field_checks':after['field_checks']}
 (out/(Path(ref['image']).stem+'.json')).write_text(json.dumps(r,indent=2))
 summary.append({k:r[k] for k in ('image','brand','font','other_criteria_changed','overall_status','font_recognized_names')})
 print(ref['brand'], v.font_ratio_results['status'], v.font_ratio_results['ratio'], 'other criteria changed:', changed, flush=True)
(out/'summary.json').write_text(json.dumps(summary,indent=2))
