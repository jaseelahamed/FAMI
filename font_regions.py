"""Font-only heading localization and measured Tesseract word crops.

No reference labels or known brand dictionary are used. Coordinates are scaled
back to the display image; OCR region height is never used as a word height.
"""
import re
from difflib import SequenceMatcher
from statistics import median
import cv2

FORM = re.compile(r'tablets?|capsules?|syrup|injection|suspension|ointment', re.I)
BODY = re.compile(r'\b(each|contains?|composition|dosage|store|storage|keep|warning|caution|schedule|manufactured|marketed|mfg|mfd|lic|excipients|colour|email|healthcare|certified|plot|road|practitioner)\b', re.I)
IGNORE = {'rx','ip','usp','bp','sr','tablets','tablet','capsules','capsule','sustained','release','mg','ml','mcg'}


def tokens(text):
    return [w.lower() for w in re.findall(r'[A-Za-z]+',text) if len(w)>2 and w.lower() not in IGNORE]


def compact_brand(text):
    text=FORM.sub('',text)
    text=re.sub(r'^\s*(?:Rx|℞)\s*','',text,flags=re.I).strip(' .,:|')
    return text if (not BODY.search(text) and re.fullmatch(r'[A-Za-z][A-Za-z0-9®™]*(?:[- ][A-Za-z0-9®™]+){0,2}', text)
                    and not re.search(r'\d{5}', text) and tokens(text)) else ''


def ink_height(image, box, region_height):
    """Trim OCR padding/trademarks using multiple character-sized components."""
    import numpy as np
    x,y,w,h=map(int,box)
    tile=image[max(0,y):y+h,max(0,x):x+w]
    if not tile.size:return None
    hsv=cv2.cvtColor(tile,cv2.COLOR_BGR2HSV)
    red=cv2.inRange(hsv,(0,65,25),(15,255,255)) | cv2.inRange(hsv,(165,65,25),(180,255,255))
    fraction=cv2.countNonZero(red)/red.size
    if fraction>.04:
        mask=255-red if fraction>.45 else red
    else:
        gray=cv2.cvtColor(tile,cv2.COLOR_BGR2GRAY)
        mask=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
    _,_,stats,_=cv2.connectedComponentsWithStats(mask)
    sizes=[float(ch) for xx,yy,cw,ch,area in stats[1:]
           if region_height*.25<ch<region_height*1.15 and cw>w*.005 and cw<w*.7
           and area>region_height**2*.008 and not (xx==0 and yy==0 and cw==w and ch==h)]
    if len(sizes)<3:return None
    mid=float(np.median(sizes))
    return max(v for v in sizes if v<=mid*1.8)


def read_region(image, box, name, backend, display_scale, pixel_scale=None):
    x,y,w,h=box
    pad=max(4,round(h*.18))
    left,top=max(0,int(x)-pad),max(0,int(y)-pad)
    crop=image[top:min(image.shape[0],int(y+h)+pad),left:min(image.shape[1],int(x+w)+pad)]
    if not crop.size:return None
    scale=pixel_scale or min(3.,max(.6,120/max(h,1)))
    gray=cv2.cvtColor(cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC),cv2.COLOR_BGR2GRAY)
    expected=tokens(name)
    best=None
    for variant, psm in [(v, p) for v in (gray,cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]) for p in (6, 7, 13)]:
        data=backend.image_to_data(variant,config=f'--oem 3 --psm {psm}',output_type=backend.Output.DICT,timeout=15)
        matches=[]
        for i,text in enumerate(data['text']):
            actual=tokens(text)
            if not actual or float(data['conf'][i])<40:continue
            similarity=max((SequenceMatcher(None,a,b).ratio() for a in actual for b in expected),default=0)
            if similarity<.72:continue
            height=float(data['height'][i])/scale
            word_box=[left+data['left'][i]/scale,top+data['top'][i]/scale,data['width'][i]/scale,height]
            ink=ink_height(image,word_box,h)
            if ink is None:continue
            matches.append({'text':text,'height_px':ink*display_scale,'confidence':float(data['conf'][i]),
                'box':word_box,'height_method':'character_components_in_recognized_word'})
        if matches:
            score=sum(m['confidence'] for m in matches)/len(matches)
            if best is None or score>best['confidence']:
                best={'name':name,'height_px':max(m['height_px'] for m in matches),'confidence':score,'words':matches,'region':box}
    if pixel_scale is None and (best is None or best['confidence'] < 80):
        retry=read_region(image,box,name,backend,display_scale,pixel_scale=.6)
        if retry and (best is None or retry['confidence']>best['confidence']):
            best=retry
    return best


def color_brand_candidates(image, heading, backend):
    """Recover missed colored brand text directly below a product heading."""
    import numpy as np
    x,y,w,h=heading['box']
    left,top=max(0,int(x)),max(0,int(y+h*.8))
    right,bottom=min(image.shape[1],int(x+w*.65)),min(image.shape[0],int(y+h*3))
    crop=image[top:bottom,left:right]
    if not crop.size:return []
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,(0,65,25),(15,255,255)) | cv2.inRange(hsv,(165,65,25),(180,255,255))
    joined=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,max(5,int(h*.08))),np.uint8))
    contours,_=cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for contour in contours:
        xx,yy,ww,hh=cv2.boundingRect(contour)
        if not (.18*h<hh<1.2*h and ww>hh*1.2 and ww< w*.65):continue
        fill=cv2.countNonZero(mask[yy:yy+hh,xx:xx+ww])/(ww*hh)
        if not .08<fill<.7:continue
        pad=max(5,int(hh*.2))
        extension=max(pad,int(ww*.6))
        tile=crop[max(0,yy-pad):yy+hh+pad,max(0,xx-pad):xx+ww+extension]
        data=backend.image_to_data(tile,config='--psm 7',output_type=backend.Output.DICT,timeout=15)
        words=[t for t,c in zip(data['text'],data['conf']) if t.strip() and float(c)>=40]
        name=compact_brand(' '.join(words))
        if name:
            box=[left+xx,top+yy,min(ww+extension,crop.shape[1]-xx),hh]
            measured=[]
            for i,text in enumerate(data['text']):
                if text not in words or not tokens(text):continue
                wb=[left+max(0,xx-pad)+data['left'][i],top+max(0,yy-pad)+data['top'][i],
                    data['width'][i],data['height'][i]]
                height=ink_height(image,wb,hh)
                if height:
                    measured.append({'text':text,'height_px':height,'confidence':float(data['conf'][i]),
                        'box':wb,'height_method':'character_components_in_recognized_word'})
            if measured:
                measurement={'name':name,'height_px':max(m['height_px'] for m in measured),
                    'confidence':min(m['confidence'] for m in measured),'words':measured,'region':box}
                candidates.append((box[1],name,{'text':name,'box':box,'measurement':measurement}))
    return candidates


def measure_heading_pair(image, lines, backend, display_scale):
    rows=[r for r in lines if r.get('source')=='paddle' and 'box' in r and r['box'][2]>r['box'][3]*1.5]
    if not rows:return None
    body_height=median(r['box'][3] for r in rows)
    headings=[r for r in rows if FORM.search(r['text']) and not BODY.search(r['text']) and r['box'][3]>body_height*1.15]
    pairs=[]
    for heading in headings:
        x,y,w,h=heading['box']
        # Generic names may sit immediately above a separate "Tablets" line.
        generic_rows=[heading] if tokens(FORM.sub('',heading['text'])) else []
        previous=[r for r in rows if r is not heading and not BODY.search(r['text'])
                  and 0<y-r['box'][1]<h*2.8 and r['box'][3]>=h*.60
                  and abs(r['box'][0]-x)<=max(w*.5,h*3) and not re.search(r'\d',r['text'])]
        if previous:
            generic_rows=sorted(previous,key=lambda r:r['box'][1])[-2:]+generic_rows
        if not generic_rows:continue
        # A brand is a short heading in the same panel, close to the generic.
        gx=min(r['box'][0] for r in generic_rows)
        gr=max(r['box'][0]+r['box'][2] for r in generic_rows)
        candidates=[]
        for row in rows:
            bx,by,bw,bh=row['box']
            name=compact_brand(row['text'])
            if not name or row in generic_rows or row is heading:continue
            if not (y+h*.6 <= by <= y+h*3.2 and gx-h <= bx <= gr):continue
            if bh < body_height*.85 or bh > h*1.5:continue
            if set(tokens(name)) & set(tokens(' '.join(r['text'] for r in generic_rows))):continue
            # Stop at the composition in this panel, not text in another column.
            if any(BODY.search(r['text']) and abs(r['box'][0]-bx)<max(bw*.5,h)
                   and y+h*.6 < r['box'][1] < by for r in rows):continue
            candidates.append((by,name,row))
        if not candidates:
            candidates = color_brand_candidates(image, heading, backend)
        for _,name,brand in sorted(candidates,key=lambda item:item[0])[:1]:
            measured_brand=read_region(image,brand['box'],name,backend,display_scale)
            if not measured_brand and brand.get('measurement'):
                from copy import deepcopy
                measured_brand=deepcopy(brand['measurement'])
                measured_brand['height_px']*=display_scale
                for word in measured_brand['words']:word['height_px']*=display_scale
            measured_generic=[read_region(image,r['box'],r['text'],backend,display_scale) for r in generic_rows]
            measured_generic=[r for r in measured_generic if r]
            if measured_brand and measured_generic:
                gen=max(measured_generic,key=lambda r:r['height_px'])
                pairs.append({'generic':gen,'brand':measured_brand,'source':'tesseract_heading_crops'})
    return max(pairs,key=lambda p:min(p['generic']['confidence'],p['brand']['confidence'])) if pairs else None
