"""Detect a red panel containing multiple printed text rows, not its wording."""
import cv2
import numpy as np


def detect_warning_panel(image):
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    red=cv2.inRange(hsv,(0,60,30),(13,255,255))|cv2.inRange(hsv,(165,60,30),(180,255,255))
    joined=cv2.morphologyEx(red,cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))
    contours,_=cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    panels=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if min(w,h)<20 or not 2<max(w,h)/min(w,h)<6 or w*h<image.shape[0]*image.shape[1]*.001:continue
        if cv2.countNonZero(red[y:y+h,x:x+w])/(w*h)<.3:continue
        tile=hsv[y:y+h,x:x+w]
        if h>w:tile=cv2.rotate(tile,cv2.ROTATE_90_CLOCKWISE)
        th,tw=tile.shape[:2]
        ink=(tile[:,:,2]<np.median(tile[:,:,2])*.65)|((tile[:,:,1]<45)&(tile[:,:,2]>190))
        ink[:2,:]=False;ink[-2:,:]=False;ink[:,:2]=False;ink[:,-2:]=False
        _,_,stats,_=cv2.connectedComponentsWithStats(ink.astype('uint8')*255)
        chars=[(xx,yy,cw,ch) for xx,yy,cw,ch,area in stats[1:]
               if 3<=ch<th*.45 and 1<=cw<tw*.2 and area>=5]
        groups=[]
        for xx,yy,cw,ch in sorted(chars,key=lambda c:c[1]+c[3]/2):
            cy=yy+ch/2
            group=next((g for g in groups if abs(g[0]-cy)<max(ch,g[1])*.55),None)
            if group is None:groups.append([cy,ch,[(xx,yy,cw,ch)]])
            else:group[2].append((xx,yy,cw,ch))
        lines=[g for g in groups if len(g[2])>=5 and max(c[0]+c[2] for c in g[2])-min(c[0] for c in g[2])>tw*.35]
        if len(lines)>=2:panels.append({'box':[x,y,w,h],'text_rows':len(lines)})
    return {'detected':bool(panels),'panels':panels,'wording_verified':False}
