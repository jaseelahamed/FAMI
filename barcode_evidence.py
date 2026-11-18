"""Conservative QR presence evidence: three nested finder patterns, not a quad."""
import itertools
import cv2
import numpy as np


def qr_candidates(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Finder topology survives illumination changes better than a generic quad.
    binaries = [cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1],
                cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,41,9)]
    found=[]
    for binary in binaries:
        contours,hierarchy=cv2.findContours(binary,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None:
            continue
        centers=[]
        for i,c in enumerate(contours):
            x,y,w,h=cv2.boundingRect(c)
            if min(w,h)<12 or not .65 < w/max(h,1) < 1.5:
                continue
            child=hierarchy[0][i][2];depth=0
            while child>=0:
                depth+=1;child=hierarchy[0][child][2]
            if depth>=2:
                expected=np.ones((7,7),dtype=bool)
                expected[1:6,1:6]=False
                expected[2:5,2:5]=True
                scores=[]
                for pad in (0, int(min(w,h)*.2)):
                    patch=binary[max(0,y-pad):y+h+pad,max(0,x-pad):x+w+pad]
                    sample=cv2.resize(patch,(70,70),interpolation=cv2.INTER_AREA)
                    cells=np.array([[sample[r*10+3:r*10+7,c*10+3:c*10+7].mean()>127 for c in range(7)] for r in range(7)])
                    scores.append(np.mean(cells==expected))
                if max(scores)<.84:
                    continue
                center=np.array([x+w/2,y+h/2])
                if not any(np.linalg.norm(center-v[0])<max(w,h)*.5 for v in centers):
                    centers.append((center,max(w,h)))
        for group in itertools.combinations(centers,3):
            sizes=[v[1] for v in group]
            if max(sizes)>min(sizes)*1.8:
                continue
            pts=np.array([v[0] for v in group])
            distances=sorted(np.linalg.norm(pts[a]-pts[b]) for a,b in ((0,1),(0,2),(1,2)))
            a,b,c=distances
            if a<max(sizes)*1.1 or c>max(sizes)*10 or b/a>1.5 or abs(c*c-a*a-b*b)/(c*c)>.3:
                continue
            pad=max(sizes)*.8
            left,top=np.maximum(0,pts.min(axis=0)-pad).astype(int)
            right,bottom=np.minimum([gray.shape[1],gray.shape[0]],pts.max(axis=0)+pad).astype(int)
            rect=(int(left),int(top),int(right-left),int(bottom-top))
            if not any(abs(rect[0]-r[0])+abs(rect[1]-r[1])<max(sizes)*2 for r in found):
                found.append(rect)
    return found
