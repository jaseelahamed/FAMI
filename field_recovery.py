"""Targeted second-pass OCR for missing stamp/manufacturer fields.

Uses a separate PP-OCRv6 medium engine on small crops only. Original OCR remains
in the report; recovered values retain crop readings and coordinates as evidence.
"""
import os
import re
import threading
from pathlib import Path
from difflib import SequenceMatcher
import cv2
from label_fields import extract_fields

_ENGINE=None
_LOCK=threading.Lock()


def _engine():
    global _ENGINE
    with _LOCK:
        if _ENGINE is None:
            from paddleocr import PaddleOCR
            kwargs=dict(use_doc_orientation_classify=False,use_doc_unwarping=False,
                        use_textline_orientation=False,enable_mkldnn=False,
                        cpu_threads=int(os.environ.get('PADDLE_CPU_THREADS','4')))
            cache=Path(os.environ.get('PADDLE_PDX_CACHE_HOME',str(Path.home()/'.paddlex')))
            for kind,suffix in [('detection','det'),('recognition','rec')]:
                name='PP-OCRv6_medium_'+suffix
                kwargs['text_'+kind+'_model_name']=name
                local=cache/'official_models'/name
                if (local/'inference.yml').exists():kwargs['text_'+kind+'_model_dir']=str(local)
            _ENGINE=PaddleOCR(**kwargs)
    return _ENGINE


def stamp_region(image):
    """Locate a dense group of blue ink characters when primary OCR missed it."""
    import numpy as np
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,(95,70,25),(145,255,255))
    n,labels,stats,_=cv2.connectedComponentsWithStats(mask)
    valid=[i for i in range(1,n) if stats[i,4]>=15 and stats[i,3]>=4]
    clean=np.isin(labels,valid).astype('uint8')*255
    size=max(image.shape[:2])
    joined=cv2.morphologyEx(clean,cv2.MORPH_CLOSE,np.ones((max(9,int(size*.025)),max(5,int(size*.012))),np.uint8))
    contours,_=cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        ink=cv2.countNonZero(clean[y:y+h,x:x+w])
        if ink>300 and max(w,h)>size*.12 and w*h<image.shape[0]*image.shape[1]*.5:
            candidates.append((ink,[x,y,w,h]))
    if not candidates:return None
    x,y,w,h=max(candidates,key=lambda item:item[0])[1]
    return [x,y,w,h]


def recover_fields(image,rows):
    if os.environ.get('OCR_FIELD_RECOVERY','1')=='0':return [],[]
    initial=extract_fields('\n'.join(r['text'] for r in rows),rows)
    missing={k for k in ('mfg_date','exp_date','manufacturer','batch') if k not in initial}
    if not missing:return [],[]
    regions=[]
    if missing & {'mfg_date','exp_date','batch'}:
        anchors=[r for r in rows if r.get('source')=='paddle_rotated'
                 and r['box'][3]>r['box'][2]*2
                 and re.search(r'B\.?No|MFG|EXP|20\d\d|M\.?R\.?P',r['text'],re.I)
                 and not re.search(r'lic|uic|no:',r['text'],re.I)]
        if anchors:
            x=min(r['box'][0] for r in anchors);y=min(r['box'][1] for r in anchors)
            right=max(r['box'][0]+r['box'][2] for r in anchors)
            bottom=max(r['box'][1]+r['box'][3] for r in anchors)
            regions.append(('stamp',[x,y,right-x,bottom-y],True))
        # A stamp may be only partly detected; color geometry supplies its full extent.
        box=stamp_region(image)
        if box:
            x,y,w,h=box
            rotate=h>w
            if rotate:
                pad=int(image.shape[1]*.12)
                left=max(0,x-pad);right=min(image.shape[1],x+w+pad)
                top=max(0,y-int(h*.25));bottom=min(image.shape[0],y+h+int(h*.25))
                box=[left,top,right-left,bottom-top]
            regions=[r for r in regions if r[0]!='stamp']
            regions.append(('stamp',box,rotate))
    if 'manufacturer' in missing:
        for r in rows:
            text=r['text'];first=re.match(r'[A-Za-z]+',text)
            if (r.get('source')=='paddle' and first and ' in ' in text.lower()
                and SequenceMatcher(None,first[0].lower(),'manufactured').ratio()>=.55):
                x,y,w,h=r['box']
                regions.append(('manufacturer',[x,y,max(w*2,h*12),h*6],False))
                break
    if 'manufacturer' in missing and not any(r[0]=='manufacturer' for r in regions):
        # When the header itself was missed, re-read body columns rather than
        # assuming a manufacturer name from a logo or marketing statement.
        body=[r for r in rows if r.get('source')=='paddle' and r['box'][2]<image.shape[1]*.6]
        groups=[]
        for r in sorted(body,key=lambda r:r['box'][0]):
            if not groups or r['box'][0]-groups[-1][0]['box'][0]>image.shape[1]*.12:
                groups.append([r])
            else:groups[-1].append(r)
        for group in sorted(groups,key=len,reverse=True)[:2]:
            if len(group)<3:continue
            x=min(r['box'][0] for r in group);y=min(r['box'][1] for r in group)
            right=max(r['box'][0]+r['box'][2] for r in group)
            bottom=max(r['box'][1]+r['box'][3] for r in group)
            regions.append(('manufacturer',[x,y,right-x,bottom-y],False))
    recovered={};warnings=[]
    recovered={};warnings=[]
    for kind,box,rotate in regions:
        x,y,w,h=map(int,box);pad=25 if rotate else 15
        left,top=max(0,x-pad),max(0,y-pad)
        crop=image[top:min(image.shape[0],y+h+pad),left:min(image.shape[1],x+w+pad)]
        if not crop.size:continue
        if rotate:crop=cv2.rotate(crop,cv2.ROTATE_90_CLOCKWISE)
        variants=[('original',crop)]
        if rotate:
            b,g,r=cv2.split(crop)
            blue=255-cv2.normalize(cv2.subtract(b,cv2.min(g,r)),None,0,255,cv2.NORM_MINMAX)
            variants.append(('blue_ink',cv2.cvtColor(blue,cv2.COLOR_GRAY2BGR)))
        for variant,im in variants:
            try:
                from ocr_paddle import _run
                items=_run(_engine(),im)
                # Detection order can interleave stamp rows: order in crop coordinates.
                items.sort(key=lambda item:(item[2][1],item[2][0]))
                text='\n'.join(t for t,c,_ in items if c>=.5)
                parsed=extract_fields(text)
                allowed={'manufacturer'} if kind=='manufacturer' else {'batch','mfg_date','exp_date'}
                for key in allowed:
                    if key in recovered or key not in parsed:continue
                    # A readable explicit batch label can replace an inferred bare ID.
                    replace_batch=(key=='batch' and initial.get(key,{}).get('uncertain')
                                   and re.search(r'B\.?\s*No|Batch|Lot',parsed[key]['value'],re.I))
                    if key not in missing and not replace_batch:continue
                    evidence=[c for t,c,_ in items if t.strip(' |—_~') in parsed[key]['lines']]
                    confidence=min(evidence or [0])
                    if confidence<.65:continue
                    recovered[key]={'text':parsed[key]['value'],'confidence':round(confidence*100,1),
                        'box':[left,top,min(image.shape[1],x+w+pad)-left,min(image.shape[0],y+h+pad)-top],
                        'source':'paddle_field_recovery','words':[],'alternatives':[],
                        'recovered_field':key,'recovery_model':'PP-OCRv6_medium',
                        'crop_rotation':90 if rotate else 0,'preprocessing':variant,'crop_ocr_text':text}
            except Exception as exc:
                warnings.append(f'{kind} crop recovery unavailable: {exc}')
                break
    return list(recovered.values()),warnings
