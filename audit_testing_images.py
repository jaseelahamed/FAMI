"""Run all TestingMedicineLabels photos, saving one complete report per image.
Usage: python audit_testing_images.py [output-directory]
Never infer accuracy from PASS counts alone; compare with visual_reference.json.
"""
import sys,json,time,os
from pathlib import Path
sys.path.insert(0,os.getcwd())
from app import MedicineLabelValidator
out=Path(sys.argv[1] if len(sys.argv)>1 else "testing_results/latest");out.mkdir(parents=True,exist_ok=True)
for p in sorted(Path('static/uploads/TestingMedicineLabels').glob('*.jpeg')):
 start=time.monotonic()
 try:
  v=MedicineLabelValidator(str(p));r=v.run_full_pipeline();r['elapsed_seconds']=round(time.monotonic()-start,2)
  (out/(p.stem+'.json')).write_text(json.dumps(r,indent=2,ensure_ascii=False))
  print('DONE',p.name,r['ocr_engine'],r['elapsed_seconds'],[(k,x['status'],x['extracted_value']) for k,x in r['regulatory_validation']['field_checks'].items()],flush=True)
 except Exception as e:
  (out/(p.stem+'.json')).write_text(json.dumps({'image_path':str(p),'error':repr(e)},indent=2))
  print('ERROR',p.name,repr(e),flush=True)
