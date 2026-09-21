#!/usr/bin/env python3
"""
Synthetic dataset for Continuum, modelled on the Ramraksha Hospital OPD
software schema (Akola). All names, numbers and IDs are fabricated.

Outputs (data/):
    patients.csv          - registration master (UH_ID keyed)
    opd_visits.csv        - OPD register + billing + Follow Up After
    clinical_notes.csv    - history/examination/diagnosis free text
    prescriptions.csv     - one row per drug per visit (Qty + dose pattern)
    uploaded_reports.csv  - scanned report index (UNSTRUCTURED - needs OCR)
    contacts_consent.csv  - kin + escalation consent (NOT in the EMR; we capture it)
    _ground_truth_duplicates.csv  - answer key: same human, two UH_IDs
    _expected_overdue.csv         - answer key: who should be flagged today
"""

import csv, os, random
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUT = str(BASE_DIR / "data")

SEED, TODAY = 42, date(2026, 9, 19)
N_PATIENTS = 500
REFILL_GRACE, FOLLOWUP_GRACE = 7, 7
rng = random.Random(SEED)

# ---------------------------------------------------------------- names
FIRST_M = ["GAJANAN","VINOD","AMOL","SUDHAKAR","MAHENDRA","PAWAN","DNYANESHWAR",
           "PRALHAD","SHRIKANT","NAMDEO","BHAGWAN","ARUN","KISHOR","SANTOSH",
           "RAJESH","MADHUKAR","PURUSHOTTAM","VITTHAL","ANANT","BALKRISHNA"]
FIRST_F = ["SHOBHA","MANGALA","ALKA","VANDANA","NIRMALA","SULOCHANA","CHHAYA",
           "PUSHPA","REKHA","SUNANDA","VAISHALI","ARCHANA","KALPANA","INDUMATI",
           "SAVITA","USHA","MADHURI","LATA","SHAILAJA","KAVITA"]
FIRST_MU_M = ["AYYUB","ABDUL LATIF","MOHD ISMAIL","SHAIKH RAFIQ","IRFAN","JUMMA"]
FIRST_MU_F = ["NASEEM BEE","SHAHANAZ BEGAM","RUKHSANA","FARIDA BEE","ZAINAB"]
MIDDLE = ["DATTATREYA","SITARAMJI","ONKAR","DAMODAR","RAMESH","NARAYAN","TUKARAM",
          "GOVIND","MAROTI","PANDURANG","SHANKARRAO","KESHAV","BABURAO","EKNATH"]
LAST = ["KALAMKAR","GADHAWALE","SHAMASKAR","CHINCHMALATPURE","DAMODAR","OBEROI",
        "NADLIWALE","DESHMUKH","INGLE","WANKHADE","THAKARE","RAUT","KHANDARE",
        "SARAP","BHATKAR","TAYADE","GAWANDE","MAHALLE","DHOTE","BORKAR"]
PLACES = ["AKOLA","TELHARA","SUKODA","AKOT","BALAPUR","MURTIJAPUR","PATUR",
          "BARSHITAKLI","RAILWAY DULGHAT","HIWARKHED","PARAS","ALEGAON"]
CONSULTANTS = ["Dr. Ashwin Sadavarte", "Dr. Ashwin Sadavarte", "Dr. R. Mahalle"]

# ------------------------------------------------- drugs (brand, dose, qty opts)
# (brand, dose_pattern, when, is_diabetes, typical_qty_choices)
DIAB_DRUGS = [
    ("WALAPHAGE G2",      "1-0-1", "BEFORE FOOD", True,  [60, 60, 30]),
    ("ZORYL M2",          "1-0-1", "BEFORE FOOD", True,  [60, 60, 30]),
    ("GLYCIPHAGE SR 1000","1-0-1", "AFTER FOOD",  True,  [60, 60, 30]),
    ("ISTAMET 50/500",    "1-0-1", "AFTER FOOD",  True,  [60, 30]),
    ("ALSITA MP (100/15/500)","1-0-0","BEFORE FOOD",True,[60, 30, 90]),
    ("TRIVOLIB 2",        "1-0-0", "BEFORE FOOD", True,  [60, 30]),
    ("DAPANORM 10",       "1-0-0", "FASTING",     True,  [60, 30, 90]),
    ("GLUCONORM G1",      "1-0-0", "BEFORE FOOD", True,  [60, 30]),
    ("VOGLIBOSE 0.3",     "1-1-1", "BEFORE FOOD", True,  [90, 60]),
]
OTHER_DRUGS = [
    ("ROSUMAC ASP (10/75)","0-0-1","AFTER FOOD",  False, [60, 30]),
    ("THYRONEED 125",     "1-0-0", "FASTING",     False, [60, 30, 90]),
    ("DILNIP M 10/25",    "1-0-0", "AFTER FOOD",  False, [60, 30]),
    ("NEXOVAS T (40/10)", "1-0-0", "AFTER FOOD",  False, [60, 30]),
    ("TELMA 40",          "1-0-0", "AFTER FOOD",  False, [60, 30]),
    ("ECOSPRIN AV 75",    "0-0-1", "AFTER FOOD",  False, [60, 30]),
    ("SHELCAL 500",       "0-0-1", "AFTER FOOD",  False, [60, 30]),
    ("NEUROBION FORTE",   "1-0-0", "AFTER FOOD",  False, [30, 60]),
    ("NEXPRO RD 40",      "1-0-0", "FASTING",     False, [10, 15, 30]),
    ("MACBATE 10 ML",     "1-1-1", "BEFORE FOOD", False, [10]),
]
DOSES_PER_DAY = {"1-0-0":1, "0-1-0":1, "0-0-1":1, "1-0-1":2, "1-1-0":2,
                 "0-1-1":2, "1-1-1":3, "2-0-2":4}

DM_VARIANTS = ["DM","T2DM","DM-2","DM TYPE 2","DIABETES MELLITUS","DM2","K/C/O DM"]
COMORBIDS   = ["HTN","HYPOTHYROIDISM","BHP","DYSLIPIDEMIA","IHD","CKD ST-2","OA KNEE"]
COMPLAINTS  = ["GENERALISED WEAKNESS, POLYURIA","BURNING FEET, NUMBNESS",
               "SWELLING OVER LEGS, INCREASED SWEATING, DRYNESS OF MOUTH",
               "GIDDINESS, EASY FATIGUE","FOR ROUTINE CHECKUP AND MEDICINES",
               "TINGLING IN B/L FEET, DISTURBED SLEEP","BLURRING OF VISION"]
REPORT_TYPES = ["HbA1c","FBS-PPBS","LIPID PROFILE","SERUM CREATININE",
                "URINE ROUTINE","THYROID PROFILE","ECG","2D ECHO","USG ABDOMEN"]
RELATIONS = ["Son","Daughter","Spouse","Brother","Sister","Daughter-in-law"]

def mobile():
    return rng.choice("6789") + "".join(rng.choice("0123456789") for _ in range(9))

def make_name():
    if rng.random() < 0.12:                      # Muslim-name subset, as in clinic
        sex = rng.choice("MF")
        f = rng.choice(FIRST_MU_M if sex == "M" else FIRST_MU_F)
        return f, rng.choice(["AYYUB","ABDUL","MOHD"]), rng.choice(["NADLIWALE","PATHAN","SHAIKH","QURESHI"]), sex
    sex = rng.choice("MF")
    f = rng.choice(FIRST_M if sex == "M" else FIRST_F)
    return f, rng.choice(MIDDLE), rng.choice(LAST), sex

# ---------------------------------------------------------------- patients
def make_patients():
    pts = []
    for i in range(N_PATIENTS):
        f, m, l, sex = make_name()
        age = rng.randint(38, 82)
        is_dm = rng.random() < 0.42
        # engagement profile
        prof = rng.choices(["engaged","lapsed","sporadic","new"],
                           weights=[42, 26, 22, 10])[0]
        pts.append({
            "person": f"H{i+1:04d}",             # true human id (answer key only)
            "uh_id": "", "f": f, "m": m, "l": l, "sex": sex, "age": age,
            "dob": (TODAY - timedelta(days=age*365 + rng.randint(0,364))).isoformat(),
            "mobile": mobile(),
            "place": rng.choice(PLACES),
            "lang": rng.choices(["Marathi","Hindi","English"], weights=[72,22,6])[0],
            "is_dm": is_dm, "prof": prof,
            "comorb": rng.sample(COMORBIDS, rng.randint(0, 3)),
            "consultant": rng.choice(CONSULTANTS),
        })
    return pts

def visit_dates(prof):
    if prof == "new":
        return [TODAY - timedelta(days=rng.randint(5, 70))]
    start = TODAY - timedelta(days=rng.randint(420, 1150))
    cad = rng.choice([30, 60, 60, 90])
    out, d = [], start
    while d <= TODAY:
        out.append(d)
        step = cad + rng.randint(-8, 20)
        if prof == "sporadic" and rng.random() < 0.35:
            step += rng.randint(70, 240)
        d += timedelta(days=step)
    if prof == "lapsed":
        cut = TODAY - timedelta(days=rng.randint(110, 520))
        out = [x for x in out if x <= cut] or [cut]
    return out

# ---------------------------------------------------------------- build
def build():
    people = make_patients()
    patients, visits, notes, rx, reports, contacts = [], [], [], [], [], []
    dup_truth = []
    uh_seq, opd_seq, rx_seq = 20240001, 10001, 1

    for p in people:
        dates = visit_dates(p["prof"])
        if not dates:
            continue

        # ~4% get re-registered as "New" -> second UH_ID for the same human
        dup = rng.random() < 0.04 and len(dates) >= 3
        uh_a = f"{uh_seq}"; uh_seq += 1
        uh_b = None
        if dup:
            uh_b = f"{uh_seq}"; uh_seq += 1
            dup_truth.append({"person": p["person"], "uh_id_1": uh_a,
                              "uh_id_2": uh_b, "reason": "re-registered as New"})
        split_at = rng.randrange(1, len(dates)) if dup else len(dates)

        for idx, uh in enumerate([uh_a] + ([uh_b] if uh_b else [])):
            # name/mobile drift on the duplicate registration
            nf = p["f"] if idx == 0 else (p["f"][0] + "." if rng.random() < .5 else p["f"])
            nm = p["m"] if idx == 0 or rng.random() < .5 else ""
            mob = p["mobile"] if idx == 0 or rng.random() < .6 else mobile()
            patients.append({
                "UH_ID": uh, "F": nf, "M": nm, "L": p["l"],
                "BirthDate": p["dob"], "Age": p["age"], "Sex": p["sex"],
                "CityPlace": p["place"], "District": "AKOLA",
                "Mobile1": mob, "BloodGroup": rng.choice(["","B+","O+","A+","AB+"]),
                "ReferredBy": rng.choices(["SELF","LMP","CAMP"], weights=[85,10,5])[0],
                "Consultant": p["consultant"],
                "PrintLanguage": p["lang"],
                "RegDate": dates[0 if idx == 0 else split_at].isoformat(),
            })

        for vi, vd in enumerate(dates):
            uh = uh_a if vi < split_at else uh_b
            opd_id = f"{opd_seq}"; opd_seq += 1
            is_last = (vi == len(dates) - 1)

            # ---- Follow Up After (present ~85% of the time)
            fu_days, fu_date = "", ""
            if rng.random() < 0.85:
                fu_days = rng.choice([15, 30, 30, 60, 60, 90])
                fu_date = (vd + timedelta(days=fu_days)).isoformat()

            cons = rng.choice([300, 400, 500])
            proc = rng.choice([0, 0, 0, 200, 300])
            paid = cons + proc if rng.random() < 0.9 else rng.choice([0, 100, 200])
            visits.append({
                "OPD_ID": opd_id, "UH_ID": uh,
                "OPDDate": vd.isoformat(),
                "Time": f"{rng.randint(9,13):02d}:{rng.randint(0,59):02d}:{rng.randint(0,59):02d}",
                "NewOld": "New" if vi == 0 or uh == uh_b and vi == split_at else "Old",
                "Consultant": p["consultant"],
                "ConsultationCharges": cons, "ProcedureCharges": proc,
                "Discount": 0, "TotalCharges": cons + proc,
                "CashReceived": paid, "OnlineReceived": 0,
                "FeesBalance": (cons + proc) - paid,
                "FollowUpAfterDays": fu_days, "FollowUpDate": fu_date,
            })

            # ---- clinical note
            dx = []
            if p["is_dm"]:
                dx.append(rng.choice(DM_VARIANTS))
            dx += p["comorb"]
            notes.append({
                "OPD_ID": opd_id, "UH_ID": uh,
                "Complaints": rng.choice(COMPLAINTS),
                "Diagnosis": " ".join(dx) if dx else "GENERALISED WEAKNESS",
                "Weight": round(rng.uniform(48, 98), 2),
                "Height": rng.randint(148, 180),
                "BMI": round(rng.uniform(19, 35), 2),
                "BP": f"{rng.choice([110,120,130,140,150,160])}/{rng.choice([70,80,90,100])}",
                "Pulse": rng.randint(62, 104), "SpO2": rng.randint(94, 100),
                "Reports": rng.choice(["", "ECG-WNL", "FBS 162 PPBS 244", "USG-NAD"]),
                "InvestigationAdvice": rng.choice(["", "HbA1c", "FBS PPBS", "S.CREAT LIPID", "HbA1c S.CREAT"]),
            })

            # ---- prescription lines
            pool = (rng.sample(DIAB_DRUGS, rng.randint(1, 2)) if p["is_dm"] else []) \
                 + rng.sample(OTHER_DRUGS, rng.randint(1, 4))
            # the headline pattern: one twice-daily drug at the same Qty as the rest
            force_short = p["is_dm"] and fu_days in (60, 90) and rng.random() < 0.55
            for (brand, pattern, when, isdm, qtys) in pool:
                qty = rng.choice(qtys)
                if force_short and isdm and pattern == "1-0-1":
                    qty = 60                      # 60 tabs @ 2/day = 30 days
                blank_qty = rng.random() < 0.08   # doctor left Qty empty
                rx.append({
                    "RxLineID": f"X{rx_seq:06d}", "OPD_ID": opd_id, "UH_ID": uh,
                    "RxDate": vd.isoformat(), "DrugName": brand,
                    "Qty": "" if blank_qty else qty,
                    "Dose": pattern, "When": when, "dwm": "Days",
                    "SpecialInstructions": rng.choice(["", "", "TAKE WITH FOOD", "15 ML"]),
                }); rx_seq += 1

            # ---- uploaded scans (unstructured; sometimes unlinked)
            if rng.random() < 0.30:
                rt = rng.choice(REPORT_TYPES)
                reports.append({
                    "FileName": f"{uh}_{vd.strftime('%d%m%Y')}_{rt.replace(' ','')}.jpg",
                    "UH_ID": uh if rng.random() < 0.82 else "",
                    "UploadDate": (vd + timedelta(days=rng.randint(0, 6))).isoformat(),
                    "LabelledAs": rt if rng.random() < 0.7 else "",
                    "Source": rng.choices(["In-house","Outside Lab"], weights=[65,35])[0],
                })

        # ---- kin + consent (captured by OUR system, not the EMR)
        has_kin = rng.random() < 0.72
        contacts.append({
            "UH_ID": uh_a,
            "PreferredLanguage": p["lang"],
            "KinName": (rng.choice(FIRST_M + FIRST_F) + " " + p["l"]) if has_kin else "",
            "KinRelation": rng.choice(RELATIONS) if has_kin else "",
            "KinMobile": mobile() if has_kin else "",
            "EscalationConsent": "YES" if has_kin and rng.random() < 0.85 else "NO",
            "ConsentDate": dates[0].isoformat() if has_kin else "",
            "OptOut": "YES" if rng.random() < 0.03 else "NO",
        })

    # duplicate rows, as real exports contain
    for _ in range(int(len(visits) * 0.015)):
        visits.append(dict(rng.choice(visits)))

    return people, patients, visits, notes, rx, reports, contacts, dup_truth

# ---------------------------------------------------------------- answer key
def expected_overdue(people, visits, rx, contacts):
    by_uh_visits, by_opd_rx = {}, {}
    for v in visits:
        by_uh_visits.setdefault(v["UH_ID"], []).append(v)
    for r in rx:
        by_opd_rx.setdefault(r["OPD_ID"], []).append(r)
    consent = {c["UH_ID"]: c for c in contacts}

    rows = []
    for uh, vs in by_uh_visits.items():
        vs = sorted({v["OPD_ID"]: v for v in vs}.values(), key=lambda x: x["OPDDate"])
        last = vs[-1]
        last_date = date.fromisoformat(last["OPDDate"])

        # follow-up signal
        fu = 0
        if last["FollowUpDate"]:
            fu = max(0, (TODAY - date.fromisoformat(last["FollowUpDate"])).days - FOLLOWUP_GRACE)

        # refill signal: EARLIEST-exhausting drug on the last prescription
        lines = by_opd_rx.get(last["OPD_ID"], [])
        ends = []
        for ln in lines:
            if ln["Qty"] == "":
                continue
            dpd = DOSES_PER_DAY.get(ln["Dose"])
            if not dpd:
                continue
            ends.append((last_date + timedelta(days=int(int(ln["Qty"]) / dpd)), ln["DrugName"]))
        if ends:
            first_end, first_drug = min(ends)
            rf = max(0, (TODAY - first_end).days - REFILL_GRACE)
            computable = "YES"
        else:
            first_end, first_drug, rf, computable = None, "", 0, "NO"

        if fu == 0 and rf == 0:
            continue
        c = consent.get(uh, {})
        rows.append({
            "UH_ID": uh,
            "last_visit": last["OPDDate"],
            "followup_date": last["FollowUpDate"],
            "followup_overdue_days": fu,
            "first_drug_exhausted": first_drug,
            "supply_end_date": first_end.isoformat() if first_end else "",
            "refill_overdue_days": rf,
            "refill_computable": computable,
            "signal_count": sum(1 for x in (fu, rf) if x > 0),
            "max_overdue_days": max(fu, rf),
            "escalation_consent": c.get("EscalationConsent", "NO"),
            "opt_out": c.get("OptOut", "NO"),
        })
    rows.sort(key=lambda r: -r["max_overdue_days"])
    return rows

def write(path, rows):
    if not rows: return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

def main():
    os.makedirs(OUT, exist_ok=True)
    people, patients, visits, notes, rx, reports, contacts, dups = build()
    write(f"{OUT}/patients.csv", patients)
    write(f"{OUT}/opd_visits.csv", visits)
    write(f"{OUT}/clinical_notes.csv", notes)
    write(f"{OUT}/prescriptions.csv", rx)
    write(f"{OUT}/uploaded_reports.csv", reports)
    write(f"{OUT}/contacts_consent.csv", contacts)
    write(f"{OUT}/_ground_truth_duplicates.csv", dups)
    exp = expected_overdue(people, visits, rx, contacts)
    write(f"{OUT}/_expected_overdue.csv", exp)

    dm = sum(1 for p in people if p["is_dm"])
    early = [r for r in exp if r["refill_overdue_days"] > 0 and r["followup_overdue_days"] == 0]
    print(f"TODAY={TODAY}  patients={len(patients)} (humans={len(people)}, dm={dm})")
    print(f"visits={len(visits)}  rx_lines={len(rx)}  scans={len(reports)}")
    print(f"duplicate registrations={len(dups)}")
    print(f"OVERDUE={len(exp)}   of which refill-only (invisible to appointment logic)={len(early)}")
    if exp: print(f"worst case={exp[0]['max_overdue_days']} days")

if __name__ == "__main__":
    main()
