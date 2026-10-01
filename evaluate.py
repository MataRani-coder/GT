#!/usr/bin/env python3
"""Ghost Trail evaluation harness.

Computes reproducible metrics from user-supplied ground truth and prediction JSON/CSV files.
No performance numbers are hard-coded or fabricated.
"""
import argparse, csv, json, math, statistics, time
from pathlib import Path


def safe_div(a,b): return a/b if b else 0.0

def detection_metrics(gt, pred, iou_threshold=0.5):
    """gt/pred: list of {frame_id, class_id, bbox:[x1,y1,x2,y2]}.
    Greedy IoU matching per frame/class."""
    def iou(a,b):
        ax1,ay1,ax2,ay2=a; bx1,by1,bx2,by2=b
        ix1,iy1=max(ax1,bx1),max(ay1,by1); ix2,iy2=min(ax2,bx2),min(ay2,by2)
        iw,ih=max(0,ix2-ix1),max(0,iy2-iy1)
        inter=iw*ih
        area_a=max(0,ax2-ax1)*max(0,ay2-ay1); area_b=max(0,bx2-bx1)*max(0,by2-by1)
        return safe_div(inter, area_a+area_b-inter)
    used=set(); tp=0
    for g in gt:
        candidates=[(iou(g['bbox'],p['bbox']),i,p) for i,p in enumerate(pred)
                    if i not in used and p.get('frame_id')==g.get('frame_id') and p.get('class_id')==g.get('class_id')]
        if candidates:
            score,i,_=max(candidates)
            if score >= iou_threshold:
                used.add(i); tp += 1
    fp=len(pred)-tp; fn=len(gt)-tp
    precision=safe_div(tp,tp+fp); recall=safe_div(tp,tp+fn)
    return {'tp':tp,'fp':fp,'fn':fn,'precision':precision,'recall':recall,'f1':safe_div(2*precision*recall,precision+recall)}


def binary_metrics(rows, truth_key='ground_truth', pred_key='prediction'):
    tp=fp=tn=fn=0
    for r in rows:
        t=bool(r[truth_key]); p=bool(r[pred_key])
        if t and p: tp+=1
        elif not t and p: fp+=1
        elif t and not p: fn+=1
        else: tn+=1
    precision=safe_div(tp,tp+fp); recall=safe_div(tp,tp+fn)
    specificity=safe_div(tn,tn+fp); f1=safe_div(2*precision*recall,precision+recall)
    return {'tp':tp,'fp':fp,'tn':tn,'fn':fn,'precision':precision,'recall':recall,'specificity':specificity,'f1':f1}


def risk_metrics(rows, threshold=60):
    converted=[]
    for r in rows:
        converted.append({'ground_truth': bool(r['ground_truth_risky']),
                          'prediction': float(r['risk_score']) >= threshold})
    return binary_metrics(converted)


def reid_metrics(rows):
    # Pairwise cross-camera identity verification: ground_truth_same_identity/predicted_same_identity.
    return binary_metrics(rows, 'ground_truth_same_identity', 'predicted_same_identity')


def latency_metrics(samples):
    vals=[float(x) for x in samples if float(x) >= 0]
    if not vals: return {}
    vals.sort()
    def pct(p): return vals[min(len(vals)-1, max(0, math.ceil(p*len(vals))-1))]
    return {'n':len(vals),'mean_ms':statistics.mean(vals),'median_ms':statistics.median(vals),
            'p95_ms':pct(.95),'p99_ms':pct(.99),'min_ms':min(vals),'max_ms':max(vals)}


def load_json(path):
    with open(path,encoding='utf-8') as f: return json.load(f)

def run_self_test():
    # Deliberately tiny synthetic sanity fixture. NOT a system-performance benchmark.
    det_gt=[{'frame_id':1,'class_id':0,'bbox':[0,0,100,100]},{'frame_id':1,'class_id':0,'bbox':[200,200,260,300]}]
    det_pr=[{'frame_id':1,'class_id':0,'bbox':[0,0,100,100]},{'frame_id':1,'class_id':0,'bbox':[300,300,350,350]}]
    reid=[{'ground_truth_same_identity':1,'predicted_same_identity':1}, {'ground_truth_same_identity':1,'predicted_same_identity':0}, {'ground_truth_same_identity':0,'predicted_same_identity':1}, {'ground_truth_same_identity':0,'predicted_same_identity':0}]
    risk=[{'ground_truth_risky':1,'risk_score':75},{'ground_truth_risky':1,'risk_score':55},{'ground_truth_risky':0,'risk_score':70},{'ground_truth_risky':0,'risk_score':20}]
    return {'note':'synthetic sanity test only; not a real-world performance result',
            'detection':detection_metrics(det_gt,det_pr), 'reid':reid_metrics(reid), 'risk':risk_metrics(risk)}


def main():
    ap=argparse.ArgumentParser(description='Ghost Trail evaluation harness')
    ap.add_argument('--detections', help='JSON object/list with gt and predictions, or use --gt-detections/--pred-detections')
    ap.add_argument('--gt-detections'); ap.add_argument('--pred-detections'); ap.add_argument('--iou',type=float,default=.5)
    ap.add_argument('--reid', help='JSON/CSV rows with ground_truth_same_identity,predicted_same_identity')
    ap.add_argument('--risk', help='JSON/CSV rows with ground_truth_risky,risk_score')
    ap.add_argument('--latency', help='CSV/TXT with one latency_ms value per line')
    ap.add_argument('--threshold',type=float,default=60)
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--out',help='Write JSON report to this path')
    args=ap.parse_args()
    report={'timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'configuration':{'iou_threshold':args.iou,'risk_threshold':args.threshold}}
    if args.self_test: report['self_test']=run_self_test()
    if args.gt_detections and args.pred_detections:
        report['detection']=detection_metrics(load_json(args.gt_detections),load_json(args.pred_detections),args.iou)
    if args.reid: report['reid']=reid_metrics(load_json(args.reid))
    if args.risk: report['risk']=risk_metrics(load_json(args.risk),args.threshold)
    if args.latency:
        vals=[]
        with open(args.latency,encoding='utf-8') as f:
            for row in csv.reader(f):
                if row and row[0].strip().lower() not in ('latency_ms','latency'): vals.append(float(row[0]))
        report['latency']=latency_metrics(vals)
    if len(report)==2 and not args.self_test:
        ap.error('provide at least one benchmark input or --self-test')
    out=json.dumps(report,indent=2)
    print(out)
    if args.out: Path(args.out).write_text(out+'\n',encoding='utf-8')

if __name__=='__main__': main()
