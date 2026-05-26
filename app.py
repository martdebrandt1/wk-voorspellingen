#!/usr/bin/env python3
"""
WK 2026 Voorspellingstool - Web App (48 teams, 12 groepen)
"""

from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, Response
import json
import os
import sqlite3
import io
import base64
from datetime import datetime
from functools import wraps
import qrcode

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'wk2026-geheim-sleutel-verander-dit!')

DB_FILE = os.environ.get('DB_PATH', 'wk2026.db')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin2026')
IBAN = "BE72 0358 4616 7316"
IBAN_CLEAN = IBAN.replace(" ", "")
BEGUNSTIGDE = "AZ St Blasius WK Poule"
INLEG = 5  # euro

GROEPEN = {
    "A": ["Mexico", "Zuid-Afrika", "Zuid-Korea", "Tsjechië"],
    "B": ["Canada", "Bosnië & Herz.", "Qatar", "Zwitserland"],
    "C": ["Brazilie", "Marokko", "Haiti", "Schotland"],
    "D": ["Verenigde Staten", "Paraguay", "Australie", "Turkije"],
    "E": ["Duitsland", "Curacao", "Ivoorkust", "Ecuador"],
    "F": ["Nederland", "Japan", "Zweden", "Tunesie"],
    "G": ["Belgie", "Egypte", "Iran", "Nieuw-Zeeland"],
    "H": ["Spanje", "Kaapverdie", "Saudi-Arabie", "Uruguay"],
    "I": ["Frankrijk", "Senegal", "Irak", "Noorwegen"],
    "J": ["Argentinie", "Algerije", "Oostenrijk", "Jordanie"],
    "K": ["Portugal", "Congo-Kinshasa", "Oezbekistan", "Colombia"],
    "L": ["Engeland", "Kroatie", "Ghana", "Panama"],
}

PUNTEN = {
    "groep_juiste_positie": 3,
    "r32_juist": 10,
    "r16_juist": 20,
    "qf_juist": 30,
    "sf_juist": 50,
    "winnaar_juist": 100,
}

R32_STRUCTURE = [
    {"slot1": {"type": "winner", "group": "E"},   "slot2": {"type": "third", "allowed": ["A", "B", "C", "D", "F"]}},
    {"slot1": {"type": "winner", "group": "I"},   "slot2": {"type": "third", "allowed": ["C", "D", "F", "G", "H"]}},
    {"slot1": {"type": "winner", "group": "F"},   "slot2": {"type": "third", "allowed": ["A", "B", "C"]}},
    {"slot1": {"type": "winner", "group": "D"},   "slot2": {"type": "third", "allowed": ["B", "E", "F", "I", "J"]}},
    {"slot1": {"type": "winner", "group": "G"},   "slot2": {"type": "third", "allowed": ["A", "E", "H", "I", "J"]}},
    {"slot1": {"type": "winner", "group": "C"},   "slot2": {"type": "third", "allowed": ["E", "H", "I", "J", "K"]}},
    {"slot1": {"type": "winner", "group": "A"},   "slot2": {"type": "third", "allowed": ["C", "E", "F", "H", "I"]}},
    {"slot1": {"type": "winner", "group": "L"},   "slot2": {"type": "third", "allowed": ["E", "H", "I", "J", "K"]}},
    {"slot1": {"type": "runnerup", "group": "A"}, "slot2": {"type": "runnerup", "group": "B"}},
    {"slot1": {"type": "runnerup", "group": "K"}, "slot2": {"type": "runnerup", "group": "L"}},
    {"slot1": {"type": "runnerup", "group": "C"}, "slot2": {"type": "runnerup", "group": "F"}},
    {"slot1": {"type": "runnerup", "group": "J"}, "slot2": {"type": "runnerup", "group": "H"}},
    {"slot1": {"type": "winner", "group": "H"},   "slot2": {"type": "runnerup", "group": "J"}},
    {"slot1": {"type": "winner", "group": "B"},   "slot2": {"type": "runnerup", "group": "E"}},
    {"slot1": {"type": "winner", "group": "J"},   "slot2": {"type": "runnerup", "group": "I"}},
    {"slot1": {"type": "winner", "group": "K"},   "slot2": {"type": "runnerup", "group": "D"}},
]


# ============================================================
# SEPA EPC QR-CODE
# ============================================================
def generate_epc_payload(name, iban, amount_eur, communication):
    name = name[:70]
    communication = communication[:140]
    amount_str = "EUR{:.2f}".format(amount_eur)
    lines = ["BCD", "002", "1", "SCT", "", name, iban, amount_str, "", "", communication, ""]
    return "\n".join(lines)


def generate_qr_image_base64(payload):
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('ascii')


# ============================================================
# DATABASE
# ============================================================
DATABASE_URL = os.environ.get('DATABASE_URL', '')
USE_POSTGRES = DATABASE_URL.startswith('postgres')

if USE_POSTGRES:
    import psycopg2
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)


def get_conn():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    else:
        return sqlite3.connect(DB_FILE)


def _q(sql):
    return sql.replace('?', '%s') if USE_POSTGRES else sql


def init_db():
    conn = get_conn()
    c = conn.cursor()
    if USE_POSTGRES:
        c.execute("""CREATE TABLE IF NOT EXISTS voorspellingen (
            naam TEXT PRIMARY KEY, data TEXT NOT NULL, datum TEXT NOT NULL, betaald INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS echte_resultaten (
            id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL, datum TEXT NOT NULL
        )""")
    else:
        c.execute("CREATE TABLE IF NOT EXISTS voorspellingen (naam TEXT PRIMARY KEY, data TEXT NOT NULL, datum TEXT NOT NULL, betaald INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS echte_resultaten (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL, datum TEXT NOT NULL)")
        try:
            c.execute("ALTER TABLE voorspellingen ADD COLUMN betaald INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def load_data():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT naam, data, betaald FROM voorspellingen")
    rows = c.fetchall()
    conn.close()
    result = {}
    for naam, data, betaald in rows:
        d = json.loads(data)
        d['betaald'] = bool(betaald)
        result[naam] = d
    return result


def save_prediction(naam, data):
    conn = get_conn()
    c = conn.cursor()
    datum = datetime.now().strftime("%Y-%m-%d %H:%M")
    data['datum'] = datum
    c.execute(_q("SELECT betaald FROM voorspellingen WHERE naam = ?"), (naam,))
    row = c.fetchone()
    betaald = row[0] if row else 0
    if USE_POSTGRES:
        c.execute("""INSERT INTO voorspellingen (naam, data, datum, betaald)
                     VALUES (%s, %s, %s, %s)
                     ON CONFLICT (naam) DO UPDATE SET
                     data = EXCLUDED.data, datum = EXCLUDED.datum""",
                  (naam, json.dumps(data, ensure_ascii=False), datum, betaald))
    else:
        c.execute("INSERT OR REPLACE INTO voorspellingen (naam, data, datum, betaald) VALUES (?, ?, ?, ?)",
                  (naam, json.dumps(data, ensure_ascii=False), datum, betaald))
    conn.commit()
    conn.close()


def set_paid_status(naam, betaald):
    conn = get_conn()
    c = conn.cursor()
    c.execute(_q("UPDATE voorspellingen SET betaald = ? WHERE naam = ?"),
              (1 if betaald else 0, naam))
    conn.commit()
    conn.close()


def delete_prediction(naam):
    conn = get_conn()
    c = conn.cursor()
    c.execute(_q("DELETE FROM voorspellingen WHERE naam = ?"), (naam,))
    conn.commit()
    conn.close()


def load_results():
    conn = get_conn()
    c = conn.cursor()
    c.execute(_q("SELECT data FROM echte_resultaten WHERE id = ?"), (1,))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else {}


def save_results(data):
    conn = get_conn()
    c = conn.cursor()
    datum = datetime.now().strftime("%Y-%m-%d %H:%M")
    if USE_POSTGRES:
        c.execute("""INSERT INTO echte_resultaten (id, data, datum)
                     VALUES (1, %s, %s)
                     ON CONFLICT (id) DO UPDATE SET
                     data = EXCLUDED.data, datum = EXCLUDED.datum""",
                  (json.dumps(data, ensure_ascii=False), datum))
    else:
        c.execute("INSERT OR REPLACE INTO echte_resultaten (id, data, datum) VALUES (1, ?, ?)",
                  (json.dumps(data, ensure_ascii=False), datum))
    conn.commit()
    conn.close()


def update_results_partial(partial_data):
    current = load_results()
    if not current:
        current = {}
    for key, value in partial_data.items():
        if key == 'knockout':
            if 'knockout' not in current:
                current['knockout'] = {}
            for ko_key, ko_val in value.items():
                current['knockout'][ko_key] = ko_val
        else:
            current[key] = value
    save_results(current)
    return current


def clear_results_section(section):
    current = load_results()
    if not current:
        return {}
    if section == 'groepsfase':
        current.pop('groepsfase', None)
    elif section == 'totaal_doelpunten':
        current.pop('totaal_doelpunten', None)
    elif section in ('ronde_van_32', 'ronde_van_16', 'kwartfinales', 'halve_finales', 'finale'):
        if 'knockout' in current:
            current['knockout'].pop(section, None)
            if not current['knockout']:
                current.pop('knockout', None)
    save_results(current)
    return current


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


def calculate_points(prediction, real_results):
    points = {"groep_positie":0,"r32":0,"r16":0,"qf":0,"sf":0,"winnaar":0,"totaal":0,"schifting_diff":None}
    if not real_results:
        return points
    real_groups = real_results.get("groepsfase", {})
    pred_groups = prediction.get("groepsfase", {})
    for group in pred_groups:
        if group not in real_groups:
            continue
        real_order = real_groups[group]
        pred_order = pred_groups[group]
        for i, team in enumerate(pred_order):
            if i < len(real_order) and real_order[i] == team:
                points["groep_positie"] += PUNTEN["groep_juiste_positie"]
    real_ko = real_results.get("knockout", {})
    pred_ko = prediction.get("knockout", {})
    for key, pk, pp in [("ronde_van_32","r32",PUNTEN["r32_juist"]),
                         ("ronde_van_16","r16",PUNTEN["r16_juist"]),
                         ("kwartfinales","qf",PUNTEN["qf_juist"]),
                         ("halve_finales","sf",PUNTEN["sf_juist"])]:
        rr = real_ko.get(key, {})
        pr = pred_ko.get(key, {})
        if rr and pr:
            rw = set(rr.values()) if isinstance(rr,dict) else set()
            pw = set(pr.values()) if isinstance(pr,dict) else set()
            points[pk] = len(rw & pw) * pp
    if real_ko.get("finale") and pred_ko.get("finale") == real_ko.get("finale"):
        points["winnaar"] = PUNTEN["winnaar_juist"]
    points["totaal"] = sum(points[k] for k in ["groep_positie","r32","r16","qf","sf","winnaar"])
    real_goals = real_results.get("totaal_doelpunten")
    pred_goals = prediction.get("totaal_doelpunten")
    if real_goals is not None and pred_goals is not None:
        try:
            points["schifting_diff"] = abs(int(real_goals) - int(pred_goals))
        except (ValueError, TypeError):
            points["schifting_diff"] = None
    return points


# ============================================================
# MAIN PAGE
# ============================================================
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="nl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AZ St Blasius - WK 2026</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',sans-serif; background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460); min-height:100vh; color:#fff; padding:20px; }
.container { max-width:900px; margin:0 auto; }
h1 { text-align:center; font-size:2.5em; margin-bottom:10px; }
.subtitle { text-align:center; color:#aaa; margin-bottom:30px; }
.nav-links { text-align:center; margin-bottom:20px; }
.nav-links a { color:#aaa; text-decoration:none; margin:0 10px; padding:8px 16px; border-radius:8px; background:rgba(255,255,255,0.05); }
.nav-links a:hover { color:#fff; background:rgba(255,255,255,0.15); }
.step-indicator { display:flex; justify-content:center; gap:8px; margin-bottom:30px; flex-wrap:wrap; }
.step { padding:8px 14px; border-radius:20px; background:rgba(255,255,255,0.1); font-size:0.8em; }
.step.active { background:#e94560; font-weight:bold; }
.step.done { background:#2ecc71; }
.card { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:24px; margin-bottom:20px; }
.card h2 { color:#e94560; margin-bottom:16px; }
.card h3 { color:#f0a500; margin-bottom:12px; }
.intro-box { background:linear-gradient(135deg,rgba(255,215,0,0.08),rgba(46,204,113,0.05)); border:1px solid rgba(255,215,0,0.2); border-radius:14px; padding:20px; margin-bottom:20px; line-height:1.7; }
.intro-box p { margin-bottom:12px; color:#e8e8e8; }
.intro-box p:last-child { margin-bottom:0; }
.intro-box strong { color:#ffd700; }
.intro-highlight { background:rgba(46,204,113,0.12); border-left:4px solid #2ecc71; padding:12px 16px; margin:16px 0; border-radius:8px; }
.intro-highlight strong { color:#2ecc71; }
.form-group { margin-bottom:16px; }
.form-group label { display:block; margin-bottom:6px; color:#ddd; font-size:0.95em; font-weight:500; }
.form-group label .req { color:#e94560; margin-left:3px; }
.form-group .help { color:#888; font-size:0.85em; margin-top:4px; }
.name-input, .form-input, .form-select, .form-number { width:100%; padding:14px 20px; font-size:1.05em; border:2px solid rgba(255,255,255,0.2); border-radius:10px; background:rgba(255,255,255,0.05); color:#fff; outline:none; }
.form-select option { background:#1a1a2e; color:#fff; }
.name-input:focus, .form-input:focus, .form-select:focus, .form-number:focus { border-color:#e94560; }
.schifting-box { background:linear-gradient(135deg,rgba(155,89,182,0.15),rgba(52,152,219,0.08)); border:2px solid rgba(155,89,182,0.4); border-radius:12px; padding:16px; margin-top:8px; }
.schifting-box h4 { color:#bb8fce; margin-bottom:8px; font-size:1em; }
.schifting-box p { color:#ccc; font-size:0.85em; margin-bottom:10px; line-height:1.5; }
.group-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:16px; margin-bottom:20px; }
.group-card { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:16px; }
.group-card h3 { font-size:1.1em; color:#f0a500; }
.sortable-list { list-style:none; padding:0; }
.sortable-list li { display:flex; align-items:center; gap:10px; padding:10px 14px; margin-bottom:6px; background:rgba(255,255,255,0.08); border-radius:8px; cursor:grab; user-select:none; }
.sortable-list li:hover { background:rgba(255,255,255,0.15); }
.sortable-list li.dragging { opacity:0.5; background:rgba(233,69,96,0.3); }
.sortable-list li .move-buttons { margin-left:auto; display:flex; gap:4px; }
.sortable-list li .move-btn { width:28px; height:28px; border-radius:50%; border:1px solid rgba(255,255,255,0.3); background:rgba(255,255,255,0.1); color:#fff; cursor:pointer; }
.position-badge { width:24px; height:24px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:0.8em; font-weight:bold; }
.pos-1 { background:#ffd700; color:#000; } .pos-2 { background:#c0c0c0; color:#000; }
.pos-3 { background:#cd7f32; color:#fff; } .pos-4 { background:#555; color:#fff; }
.match-card { display:flex; align-items:center; justify-content:space-between; padding:12px 16px; margin-bottom:10px; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:10px; gap:10px; }
.match-team { flex:1; text-align:center; padding:10px; border-radius:8px; cursor:pointer; border:2px solid transparent; }
.match-team:hover { background:rgba(255,255,255,0.1); }
.match-team.selected { background:rgba(46,204,113,0.2); border-color:#2ecc71; }
.match-vs { font-weight:bold; color:#e94560; font-size:0.9em; }
.knockout-round { margin-bottom:24px; }
.knockout-round h3 { margin-bottom:12px; padding-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.1); }
.btn { display:inline-block; padding:14px 32px; font-size:1.1em; font-weight:bold; border:none; border-radius:10px; cursor:pointer; text-transform:uppercase; }
.btn-primary { background:#e94560; color:#fff; }
.btn-primary:hover { background:#d63851; }
.btn-secondary { background:rgba(255,255,255,0.1); color:#fff; border:1px solid rgba(255,255,255,0.2); }
.btn:disabled { opacity:0.5; cursor:not-allowed; }
.btn-group { display:flex; gap:12px; justify-content:center; margin-top:24px; flex-wrap:wrap; }
.hidden { display:none; }
.success-screen { text-align:center; padding:40px 20px; }
.success-screen h2 { color:#2ecc71; font-size:2em; margin-bottom:16px; }
.trophy { font-size:4em; margin-bottom:20px; }
.champion-name { font-size:1.5em; color:#ffd700; margin:16px 0; }
.drag-hint { color:#888; font-size:0.85em; margin-bottom:12px; font-style:italic; }
.error-msg { color:#e94560; font-size:0.9em; margin-top:8px; display:none; }
.error-msg.show { display:block; }
.third-assign-select { width:100%; padding:10px; border-radius:8px; background:rgba(0,0,0,0.4); color:#fff; border:2px solid rgba(255,255,255,0.2); font-size:1em; }
.third-assign-select option { background:#1a1a2e; color:#fff; }
.payment-card { background:linear-gradient(135deg,rgba(255,215,0,0.15),rgba(233,69,96,0.1)); border:2px solid #ffd700; border-radius:16px; padding:24px; text-align:center; margin-bottom:20px; }
.payment-icon { font-size:3em; margin-bottom:8px; }
.payment-amount { font-size:2.5em; font-weight:bold; color:#ffd700; margin:8px 0; }
.payment-detail { background:rgba(0,0,0,0.3); border-radius:12px; padding:16px; margin:16px 0; }
.payment-detail-row { display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.08); flex-wrap:wrap; gap:8px; align-items:center; }
.payment-detail-row:last-child { border-bottom:none; }
.payment-detail-row .label { color:#aaa; font-size:0.9em; text-align:left; }
.payment-detail-row .value { color:#fff; font-weight:bold; font-family:'Courier New',monospace; font-size:1em; text-align:right; word-break:break-all; }
.copy-btn { padding:5px 10px; font-size:0.8em; background:rgba(46,204,113,0.2); border:1px solid #2ecc71; color:#2ecc71; border-radius:6px; cursor:pointer; margin-left:6px; }
.copy-btn:hover { background:#2ecc71; color:#fff; }
.copy-btn.copied { background:#2ecc71; color:#fff; }
.payment-warning { background:rgba(233,69,96,0.12); border:1px solid rgba(233,69,96,0.4); border-radius:10px; padding:12px; margin:16px 0; font-size:0.9em; }
.payment-checkbox-row { background:rgba(255,255,255,0.05); border:2px solid rgba(255,255,255,0.1); border-radius:10px; padding:14px; margin:20px 0; cursor:pointer; transition:all 0.2s; }
.payment-checkbox-row:hover { border-color:#2ecc71; background:rgba(46,204,113,0.05); }
.payment-checkbox-row.checked { border-color:#2ecc71; background:rgba(46,204,113,0.1); }
.payment-checkbox-row input[type=checkbox] { margin-right:10px; transform:scale(1.4); accent-color:#2ecc71; }
.payment-checkbox-row label { cursor:pointer; user-select:none; font-size:0.95em; }
@media (max-width:600px) { .match-card { flex-direction:column; } .match-team { width:100%; } .payment-amount { font-size:2em; } }
</style></head><body>
<div class="container">
<h1>&#9917; AZ St Blasius - WK 2026</h1>
<p class="subtitle">De wereldbeker-poule van het ziekenhuis</p>
<div class="nav-links"><a href="/scoreboard">&#127942; Scoreboard</a><a href="/admin">&#128272; Admin</a></div>

<div class="step-indicator">
<div class="step active" id="step-ind-1">1. Wie ben je?</div>
<div class="step" id="step-ind-2">2. Groepsfase</div>
<div class="step" id="step-ind-3">3. Knock-out</div>
<div class="step" id="step-ind-4">4. Betaling</div>
<div class="step" id="step-ind-5">5. Klaar!</div>
</div>

<div id="step-1" class="card">
<h2>&#127947; Welkom bij de WK 2026 poule!</h2>

<div class="intro-box">
<p>&#127881; <strong>Het is weer zover!</strong> Onze 2-jaarlijkse traditie is terug: de grote AZ St Blasius voetbalpoule!</p>
<p>&#127918; <strong>Je hoeft GEEN voetbalkenner te zijn!</strong> Wie weet zit jij straks bovenaan met je &laquo;buikgevoel-tactiek&raquo;.</p>
<p>&#129309; <strong>Meedoen is belangrijker dan winnen.</strong> Het draait om het plezier en de discussies aan de koffieautomaat.</p>
<div class="intro-highlight">
&#10084;&#65039; <strong>De helft van de inleg gaat naar het goede doel.</strong> De andere helft naar de top-voorspellers.
</div>
<p>&#9917; Klaar? Vul hieronder je gegevens in!</p>
</div>

<h3 style="margin-top:24px;">&#128100; Vertel ons wie je bent</h3>

<div class="form-group">
<label for="player-name">Naam <span class="req">*</span></label>
<input type="text" class="name-input" id="player-name" placeholder="Voornaam Achternaam" autocomplete="name">
</div>

<div class="form-group">
<label for="player-email">E-mailadres <span class="req">*</span></label>
<input type="email" class="form-input" id="player-email" placeholder="jouw.naam@azsintblasius.be" autocomplete="email">
</div>

<div class="form-group">
<label for="player-relation">Relatie met het ziekenhuis <span class="req">*</span></label>
<input type="text" class="form-input" id="player-relation" placeholder="Bijv. Verpleegkundige spoed, Stagiair, Familie van...">
<p class="help">Vul vrij in: dienst, functie, of hoe je verbonden bent met het ziekenhuis</p>
</div>

<div class="form-group">
<label for="player-goals">Schiftingsvraag: Hoeveel doelpunten op het hele WK? <span class="req">*</span></label>
<div class="schifting-box">
<h4>&#127943; Tiebreaker</h4>
<p>Tel <strong>alle doelpunten</strong> die er gemaakt zullen worden tijdens het volledige WK 2026. Bij gelijke punten wint wie het dichtst bij het echte aantal zit! <strong>Jouw antwoord blijft geheim</strong> voor andere deelnemers.</p>
<input type="number" class="form-number" id="player-goals" placeholder="Bijv. 165" min="0" max="500">
</div>
</div>

<p class="error-msg" id="form-error">&#9888; Vul alle velden in!</p>
<div class="btn-group"><button class="btn btn-primary" id="btn-next-1">Volgende &#8594;</button></div>
</div>

<div id="step-2" class="card hidden">
<h2>&#128202; Groepsfase</h2>
<p class="drag-hint">Gebruik de pijltjes om landen te verplaatsen.</p>
<div class="group-grid" id="groups-container"></div>
<div class="btn-group">
<button class="btn btn-secondary" id="btn-back-2">&#8592; Terug</button>
<button class="btn btn-primary" id="btn-next-2">Volgende &#8594;</button>
</div>
</div>

<div id="step-3" class="card hidden">
<h2>&#127942; Knock-outfase</h2>
<div id="knockout-container"></div>
<div class="btn-group">
<button class="btn btn-secondary" id="btn-back-3">&#8592; Terug</button>
<button class="btn btn-primary" id="btn-next-3">Volgende &#8594;</button>
</div>
</div>

<div id="step-4" class="card hidden">
<div class="payment-card">
<div class="payment-icon">&#128241;</div>
<h2 style="color:#ffd700;border:none;">Scan & Betaal</h2>
<div class="payment-amount">&euro;%INLEG%</div>
<div id="qr-container" style="background:rgba(255,255,255,0.1);padding:30px;border-radius:16px;min-height:280px;display:flex;align-items:center;justify-content:center;color:#aaa;margin:16px 0;">
&#9203; QR-code wordt gegenereerd...
</div>
<div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:12px;padding:16px;margin:16px 0;text-align:left;">
<h4 style="color:#2ecc71;margin-bottom:10px;font-size:1em;">&#128241; Hoe betalen?</h4>
<ol style="margin-left:20px;color:#ccc;font-size:0.9em;line-height:1.7;">
<li>Open je <strong style="color:#fff;">bankapp</strong> (KBC, Belfius, ING, BNP, Argenta, ...)</li>
<li>Kies <strong style="color:#fff;">"Overschrijven"</strong> &rarr; <strong style="color:#fff;">"QR-code scannen"</strong></li>
<li>Scan de QR-code &rarr; alles wordt automatisch ingevuld</li>
<li>Bevestig de betaling met je app</li>
</ol>
</div>
<a id="manual-toggle" style="color:#aaa;cursor:pointer;text-decoration:underline;font-size:0.9em;display:inline-block;">&#9881; Liever handmatig overschrijven? Klik hier</a>
</div>

<div class="payment-detail hidden" id="manual-details">
<div class="payment-detail-row">
<span class="label">IBAN</span>
<span class="value" id="iban-text">%IBAN%<button class="copy-btn" data-copy="iban-text">&#128203; Kopieer</button></span>
</div>
<div class="payment-detail-row">
<span class="label">Bedrag</span>
<span class="value">&euro; %INLEG%,00</span>
</div>
<div class="payment-detail-row">
<span class="label">Mededeling</span>
<span class="value" id="mededeling-text">WK2026 - <span id="mededeling-naam">jouw naam</span><button class="copy-btn" data-copy="mededeling-text">&#128203; Kopieer</button></span>
</div>
</div>

<div class="payment-warning">
&#9888; <strong>Belangrijk:</strong> De QR-code bevat <strong>automatisch jouw naam</strong> in de mededeling.
</div>

<div class="payment-checkbox-row" id="payment-confirm-row">
<label style="display:flex;align-items:center;">
<input type="checkbox" id="payment-confirm">
<span>Ik heb de betaling uitgevoerd</span>
</label>
</div>

<div class="btn-group">
<button class="btn btn-secondary" id="btn-back-4">&#8592; Terug</button>
<button class="btn btn-primary" id="btn-submit" disabled>&#9989; Voorspelling Indienen</button>
</div>
</div>

<div id="step-5" class="card hidden">
<div class="success-screen">
<div class="trophy">&#127942;</div>
<h2>Voorspelling Ingediend!</h2>
<p>Bedankt <strong id="confirm-name"></strong>!</p>
<p class="champion-name">Jouw kampioen: <span id="confirm-champion"></span></p>
<p style="color:#aaa;margin:20px 0;">Veel succes! Hou het scoreboard in de gaten. &#9917;</p>
<div class="btn-group">
<button class="btn btn-secondary" onclick="location.reload()">Nieuwe Voorspelling</button>
<button class="btn btn-primary" onclick="window.location.href='/scoreboard'">Scoreboard</button>
</div>
</div>
</div>
</div>

<script>
(function() {
"use strict";
var GROEPEN = %GROEPEN_JSON%;
var R32_STRUCTURE = %R32_STRUCTURE_JSON%;
var currentStep = 1;
var groupPredictions = {};
var thirdPlaceAssignments = {};
var knockoutSelections = {};

function loadQRCode(name) {
    var container = document.getElementById('qr-container');
    container.style.background = 'rgba(255,255,255,0.1)';
    container.style.padding = '30px';
    container.innerHTML = '&#9203; QR-code wordt gegenereerd...';
    fetch('/api/qr?naam=' + encodeURIComponent(name))
    .then(function(r){ return r.json(); })
    .then(function(d) {
        if (d.success) {
            container.style.background = '#fff';
            container.style.padding = '20px';
            container.innerHTML = '<img src="data:image/png;base64,' + d.qr + '" alt="SEPA QR-code" style="display:block;max-width:280px;width:100%;height:auto;">';
        } else {
            container.innerHTML = 'Fout: ' + (d.error || 'kon QR niet genereren');
        }
    })
    .catch(function() {
        container.innerHTML = 'Fout bij laden QR-code.';
    });
}

function validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function goToStep(step) {
    if (step === 2) {
        var nameVal = document.getElementById('player-name').value.trim();
        var emailVal = document.getElementById('player-email').value.trim();
        var relationVal = document.getElementById('player-relation').value.trim();
        var goalsVal = document.getElementById('player-goals').value.trim();
        var errorEl = document.getElementById('form-error');
        if (!nameVal || !emailVal || !relationVal || !goalsVal) {
            errorEl.textContent = '\u26A0 Vul alle velden in!';
            errorEl.classList.add('show');
            return;
        }
        if (!validateEmail(emailVal)) {
            errorEl.textContent = '\u26A0 Vul een geldig e-mailadres in!';
            errorEl.classList.add('show');
            return;
        }
        var goalsNum = parseInt(goalsVal, 10);
        if (isNaN(goalsNum) || goalsNum < 0 || goalsNum > 500) {
            errorEl.textContent = '\u26A0 Vul een geldig aantal doelpunten in (0-500)!';
            errorEl.classList.add('show');
            return;
        }
        errorEl.classList.remove('show');
    }
    if (step === 3) {
        groupPredictions = getGroupResults();
        buildKnockout();
    }
    if (step === 4) {
        if (!knockoutSelections.final_round || knockoutSelections.final_round[0] === undefined) {
            alert('Vul eerst alle knock-out wedstrijden in!');
            return;
        }
        var playerName = document.getElementById('player-name').value.trim();
        document.getElementById('mededeling-naam').textContent = playerName;
        loadQRCode(playerName);
    }
    document.getElementById('step-' + currentStep).classList.add('hidden');
    document.getElementById('step-' + step).classList.remove('hidden');
    for (var i = 1; i <= 5; i++) {
        var ind = document.getElementById('step-ind-' + i);
        ind.classList.remove('active', 'done');
        if (i < step) ind.classList.add('done');
        if (i === step) ind.classList.add('active');
    }
    currentStep = step;
    window.scrollTo(0, 0);
}

function buildGroups() {
    var container = document.getElementById('groups-container');
    container.innerHTML = '';
    var groups = Object.keys(GROEPEN);
    for (var g = 0; g < groups.length; g++) {
        var group = groups[g], teams = GROEPEN[group];
        var card = document.createElement('div');
        card.className = 'group-card';
        var html = '<h3>Groep ' + group + '</h3><ul class="sortable-list" id="group-' + group + '">';
        for (var i = 0; i < teams.length; i++) {
            html += '<li draggable="true" data-team="' + teams[i] + '">';
            html += '<span class="position-badge pos-' + (i+1) + '">' + (i+1) + '</span>';
            html += '<span>' + teams[i] + '</span>';
            html += '<span class="move-buttons">';
            html += '<button type="button" class="move-btn" data-dir="up">&#9650;</button>';
            html += '<button type="button" class="move-btn" data-dir="down">&#9660;</button>';
            html += '</span></li>';
        }
        html += '</ul>';
        card.innerHTML = html;
        container.appendChild(card);
        var list = card.querySelector('.sortable-list');
        initSortable(list);
        initMoveButtons(list);
    }
}

function initMoveButtons(list) {
    list.addEventListener('click', function(e) {
        var btn = e.target.closest('.move-btn');
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        var li = btn.closest('li'), dir = btn.getAttribute('data-dir');
        if (dir === 'up' && li.previousElementSibling) list.insertBefore(li, li.previousElementSibling);
        else if (dir === 'down' && li.nextElementSibling) list.insertBefore(li.nextElementSibling, li);
        updatePositionBadges(list);
    });
}

function initSortable(list) {
    var dragged = null;
    list.addEventListener('dragstart', function(e) { dragged = e.target.closest('li'); if (dragged) dragged.classList.add('dragging'); });
    list.addEventListener('dragend', function() { if (dragged) { dragged.classList.remove('dragging'); dragged = null; updatePositionBadges(list); } });
    list.addEventListener('dragover', function(e) {
        e.preventDefault(); if (!dragged) return;
        var after = getDragAfter(list, e.clientY);
        if (after == null) list.appendChild(dragged); else list.insertBefore(dragged, after);
    });
}

function getDragAfter(c, y) {
    var els = c.querySelectorAll('li:not(.dragging)'), closest = null, co = -Infinity;
    for (var i = 0; i < els.length; i++) {
        var box = els[i].getBoundingClientRect();
        var off = y - box.top - box.height / 2;
        if (off < 0 && off > co) { co = off; closest = els[i]; }
    }
    return closest;
}

function updatePositionBadges(list) {
    var items = list.querySelectorAll('li');
    for (var i = 0; i < items.length; i++) {
        var b = items[i].querySelector('.position-badge');
        b.className = 'position-badge pos-' + (i + 1);
        b.textContent = i + 1;
    }
}

function getGroupResults() {
    var r = {};
    var groups = Object.keys(GROEPEN);
    for (var g = 0; g < groups.length; g++) {
        var list = document.getElementById('group-' + groups[g]);
        if (!list) continue;
        var items = list.querySelectorAll('li');
        r[groups[g]] = [];
        for (var i = 0; i < items.length; i++) r[groups[g]].push(items[i].getAttribute('data-team'));
    }
    return r;
}

function buildKnockout() {
    var container = document.getElementById('knockout-container');
    container.innerHTML = '';
    knockoutSelections = { r32: {}, r16: {}, qf: {}, sf: {}, final_round: {} };
    thirdPlaceAssignments = {};
    buildThirdPlaceAssignment(container);
}

function resolveTeam(slot) {
    if (slot.type === 'winner') return groupPredictions[slot.group][0];
    if (slot.type === 'runnerup') return groupPredictions[slot.group][1];
    return 'TBD';
}

function buildThirdPlaceAssignment(container) {
    var div = document.createElement('div');
    div.className = 'knockout-round';
    div.id = 'third-assignment';
    var html = '<h3>&#127919; Wijs Beste Derdes toe aan Wedstrijden</h3>';
    html += '<p class="drag-hint">Voor elke wedstrijd: kies welk #3 team daadwerkelijk speelt.</p>';
    for (var i = 0; i < R32_STRUCTURE.length; i++) {
        var match = R32_STRUCTURE[i];
        if (match.slot2.type !== 'third') continue;
        var slot1Team = resolveTeam(match.slot1);
        html += '<div class="match-card" style="flex-direction:column;align-items:stretch;">';
        html += '<div style="text-align:center;margin-bottom:8px;"><strong>' + slot1Team + '</strong> vs <em>3e uit groep ' + match.slot2.allowed.join('/') + '</em></div>';
        html += '<select class="third-assign-select" data-match="' + i + '">';
        html += '<option value="">-- Kies een team --</option>';
        for (var j = 0; j < match.slot2.allowed.length; j++) {
            var grp = match.slot2.allowed[j];
            if (groupPredictions[grp] && groupPredictions[grp][2]) {
                html += '<option value="' + grp + '">' + groupPredictions[grp][2] + ' (Groep ' + grp + ')</option>';
            }
        }
        html += '</select></div>';
    }
    html += '<div class="btn-group"><button class="btn btn-primary" id="btn-confirm-thirds">Bevestig &#8594;</button></div>';
    div.innerHTML = html;
    container.appendChild(div);
    var selects = div.querySelectorAll('.third-assign-select');
    for (var s = 0; s < selects.length; s++) selects[s].addEventListener('change', updateThirdAssignOptions);
    document.getElementById('btn-confirm-thirds').addEventListener('click', confirmThirdAssignments);
}

function updateThirdAssignOptions() {
    var selects = document.querySelectorAll('.third-assign-select');
    var used = [];
    for (var i = 0; i < selects.length; i++) if (selects[i].value) used.push(selects[i].value);
    for (var i = 0; i < selects.length; i++) {
        var current = selects[i].value;
        var opts = selects[i].querySelectorAll('option');
        for (var j = 0; j < opts.length; j++) {
            if (opts[j].value === '') continue;
            opts[j].disabled = (opts[j].value !== current && used.indexOf(opts[j].value) >= 0);
        }
    }
}

function confirmThirdAssignments() {
    var selects = document.querySelectorAll('.third-assign-select');
    thirdPlaceAssignments = {};
    for (var i = 0; i < selects.length; i++) {
        if (!selects[i].value) { alert('Wijs alle wedstrijden een #3 team toe!'); return; }
        thirdPlaceAssignments[parseInt(selects[i].getAttribute('data-match'))] = selects[i].value;
    }
    document.getElementById('third-assignment').remove();
    buildR32Matches();
}

function buildR32Matches() {
    var container = document.getElementById('knockout-container');
    var matches = [];
    for (var i = 0; i < R32_STRUCTURE.length; i++) {
        var m = R32_STRUCTURE[i];
        var t1 = resolveTeam(m.slot1);
        var t2;
        if (m.slot2.type === 'third') {
            var ag = thirdPlaceAssignments[i];
            t2 = ag ? groupPredictions[ag][2] : 'TBD';
        } else { t2 = resolveTeam(m.slot2); }
        matches.push({ team1: t1, team2: t2 });
    }
    renderRound(container, '1/32 Finales', matches, 'r32');
}

function renderRound(container, title, matches, roundKey) {
    var div = document.createElement('div');
    div.className = 'knockout-round';
    div.id = 'round-' + roundKey;
    var html = '<h3>' + title + '</h3>';
    for (var i = 0; i < matches.length; i++) {
        var m = matches[i];
        html += '<div class="match-card">';
        html += '<div class="match-team" id="' + roundKey + '-' + i + '-1" data-round="' + roundKey + '" data-match="' + i + '" data-team="' + esc(m.team1) + '">' + m.team1 + '</div>';
        html += '<span class="match-vs">VS</span>';
        html += '<div class="match-team" id="' + roundKey + '-' + i + '-2" data-round="' + roundKey + '" data-match="' + i + '" data-team="' + esc(m.team2) + '">' + m.team2 + '</div>';
        html += '</div>';
    }
    div.innerHTML = html;
    container.appendChild(div);
    var teamDivs = div.querySelectorAll('.match-team');
    for (var t = 0; t < teamDivs.length; t++) teamDivs[t].addEventListener('click', handleMatchClick);
}

function esc(s) { return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function handleMatchClick(e) {
    var el = e.currentTarget;
    var rk = el.getAttribute('data-round');
    var mi = parseInt(el.getAttribute('data-match'));
    var tn = el.getAttribute('data-team');
    document.getElementById(rk + '-' + mi + '-1').classList.remove('selected');
    document.getElementById(rk + '-' + mi + '-2').classList.remove('selected');
    el.classList.add('selected');
    knockoutSelections[rk][mi] = tn;
    buildNextRound(rk);
}

function buildNextRound(rk) {
    var container = document.getElementById('knockout-container');
    var counts = { r32: 16, r16: 8, qf: 4, sf: 2, final_round: 1 };
    var nexts = { r32: 'r16', r16: 'qf', qf: 'sf', sf: 'final_round' };

    /* ENKEL TITELS GECORRIGEERD */
    var names = {
        r32: '1/16 Finales',
        r16: '1/8 Finales',
        qf: 'Kwartfinales',
        sf: '&#127942; FINALE'
    };

    if (Object.keys(knockoutSelections[rk]).length < counts[rk]) return;
    var nk = nexts[rk];
    if (!nk) return;
    var order = ['r16', 'qf', 'sf', 'final_round'];
    for (var i = order.indexOf(nk); i < order.length; i++) {
        var ex = document.getElementById('round-' + order[i]);
        if (ex) ex.remove();
        knockoutSelections[order[i]] = {};
    }
    var winners = [];
    for (var j = 0; j < counts[rk]; j++) winners.push(knockoutSelections[rk][j]);
    var nm = [];
    for (var k = 0; k < winners.length; k += 2) nm.push({ team1: winners[k], team2: winners[k + 1] });
    renderRound(container, names[nk], nm, nk);
}

document.addEventListener('click', function(e) {
    if (e.target && e.target.id === 'manual-toggle') {
        document.getElementById('manual-details').classList.toggle('hidden');
        return;
    }
    var btn = e.target.closest('.copy-btn');
    if (!btn) return;
    var targetId = btn.getAttribute('data-copy');
    var text = '';
    if (targetId === 'iban-text') text = '%IBAN%';
    else if (targetId === 'mededeling-text') text = 'WK2026 - ' + document.getElementById('player-name').value.trim();
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function(){
            btn.classList.add('copied');
            var oldHtml = btn.innerHTML;
            btn.innerHTML = '&#10003; Gekopieerd';
            setTimeout(function(){ btn.classList.remove('copied'); btn.innerHTML = oldHtml; }, 2000);
        });
    }
});

document.getElementById('payment-confirm').addEventListener('change', function() {
    document.getElementById('btn-submit').disabled = !this.checked;
    document.getElementById('payment-confirm-row').classList.toggle('checked', this.checked);
});
document.getElementById('payment-confirm-row').addEventListener('click', function(e) {
    if (e.target.tagName !== 'INPUT') {
        var cb = document.getElementById('payment-confirm');
        cb.checked = !cb.checked;
        cb.dispatchEvent(new Event('change'));
    }
});

function submitPrediction() {
    var name = document.getElementById('player-name').value.trim();
    var email = document.getElementById('player-email').value.trim();
    var relation = document.getElementById('player-relation').value.trim();
    var goals = parseInt(document.getElementById('player-goals').value, 10);
    if (!document.getElementById('payment-confirm').checked) {
        alert('Bevestig eerst de betaling!'); return;
    }
    var derdes = [];
    for (var k in thirdPlaceAssignments) {
        var grp = thirdPlaceAssignments[k];
        derdes.push({ groep: grp, team: groupPredictions[grp][2] });
    }
    var data = {
        naam: name,
        email: email,
        relatie: relation,
        totaal_doelpunten: goals,
        groepsfase: getGroupResults(),
        beste_derdes: derdes,
        third_assignments: thirdPlaceAssignments,
        knockout: {
            ronde_van_32: knockoutSelections.r32, ronde_van_16: knockoutSelections.r16,
            kwartfinales: knockoutSelections.qf, halve_finales: knockoutSelections.sf,
            finale: knockoutSelections.final_round[0]
        }
    };
    fetch('/api/submit', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) })
    .then(function(r) { return r.json(); })
    .then(function(res) {
        if (res.success) {
            document.getElementById('confirm-name').textContent = name;
            document.getElementById('confirm-champion').textContent = knockoutSelections.final_round[0];
            goToStep(5);
        } else alert('Fout: ' + res.error);
    });
}

document.getElementById('btn-next-1').addEventListener('click', function() { goToStep(2); });
document.getElementById('btn-back-2').addEventListener('click', function() { goToStep(1); });
document.getElementById('btn-next-2').addEventListener('click', function() { goToStep(3); });
document.getElementById('btn-back-3').addEventListener('click', function() { goToStep(2); });
document.getElementById('btn-next-3').addEventListener('click', function() { goToStep(4); });
document.getElementById('btn-back-4').addEventListener('click', function() { goToStep(3); });
document.getElementById('btn-submit').addEventListener('click', submitPrediction);
['player-name','player-email','player-relation','player-goals'].forEach(function(id){
    document.getElementById(id).addEventListener('input', function() { document.getElementById('form-error').classList.remove('show'); });
});

buildGroups();
})();
</script>
</body></html>
"""

# ============================================================
# SCOREBOARD
# ============================================================
SCOREBOARD_TEMPLATE = r"""<!DOCTYPE html>
<html lang="nl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Scoreboard</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',sans-serif; background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460); min-height:100vh; color:#fff; padding:20px; }
.container { max-width:1000px; margin:0 auto; }
h1 { text-align:center; font-size:2.2em; margin-bottom:10px; }
.subtitle { text-align:center; color:#aaa; margin-bottom:30px; }
.nav-links { text-align:center; margin-bottom:20px; }
.nav-links a { color:#aaa; text-decoration:none; margin:0 10px; padding:8px 16px; border-radius:8px; background:rgba(255,255,255,0.05); }
.nav-links a:hover { color:#fff; background:rgba(255,255,255,0.15); }
.card { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:24px; margin-bottom:20px; }
.card h2 { color:#e94560; margin-bottom:16px; }
.leaderboard { width:100%; border-collapse:collapse; }
.leaderboard th { background:rgba(233,69,96,0.2); padding:12px 10px; text-align:center; font-size:0.8em; }
.leaderboard td { padding:12px 10px; border-bottom:1px solid rgba(255,255,255,0.05); text-align:center; }
.leaderboard tr.clickable { cursor:pointer; transition:background 0.2s; }
.leaderboard tr.clickable:hover { background:rgba(233,69,96,0.1); }
.leaderboard .name { text-align:left; font-weight:bold; color:#fff; }
.leaderboard .total { font-weight:bold; font-size:1.3em; color:#2ecc71; }
.leaderboard .schifting { color:#bb8fce; font-size:0.85em; }
.rank-1{color:#ffd700;} .rank-2{color:#c0c0c0;} .rank-3{color:#cd7f32;}
.punten-info { background:rgba(255,215,0,0.08); border:1px solid rgba(255,215,0,0.2); border-radius:12px; padding:16px; margin-bottom:20px; }
.punten-info h3 { color:#ffd700; margin-bottom:8px; font-size:1em; }
.punten-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:4px; }
.punten-grid span { color:#ccc; font-size:0.85em; }
.punten-grid strong { color:#fff; }
.stats-bar { display:flex; gap:12px; margin-bottom:16px; flex-wrap:wrap; }
.stat-pill { background:rgba(46,204,113,0.15); border:1px solid rgba(46,204,113,0.3); padding:8px 14px; border-radius:20px; font-size:0.9em; }
.stat-pill.purple { background:rgba(155,89,182,0.15); border-color:rgba(155,89,182,0.3); }
.modal-overlay { display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.85); z-index:1000; padding:20px; overflow-y:auto; }
.modal-overlay.active { display:block; }
.modal-content { max-width:900px; margin:20px auto; background:linear-gradient(135deg,#1a1a2e,#16213e); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:30px; position:relative; }
.modal-close { position:absolute; top:15px; right:15px; width:40px; height:40px; border-radius:50%; border:none; background:rgba(233,69,96,0.2); color:#fff; font-size:1.5em; cursor:pointer; }
.modal-content h2 { color:#e94560; margin-bottom:8px; }
.modal-content h3 { color:#f0a500; margin:20px 0 10px 0; padding-bottom:6px; border-bottom:1px solid rgba(255,255,255,0.1); }
.modal-info { color:#aaa; font-size:0.9em; margin-bottom:20px; }
.modal-group-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
.modal-group { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:10px; padding:12px; }
.modal-group h4 { color:#f0a500; margin-bottom:8px; font-size:0.95em; }
.modal-group ol { list-style:none; padding:0; counter-reset:item; }
.modal-group ol li { padding:4px 8px; margin-bottom:3px; background:rgba(255,255,255,0.05); border-radius:4px; font-size:0.85em; counter-increment:item; }
.modal-group ol li::before { content:counter(item) ". "; color:#888; font-weight:bold; }
.modal-group ol li.correct { background:rgba(46,204,113,0.15); border-left:3px solid #2ecc71; }
.modal-group ol li.wrong { background:rgba(231,76,60,0.1); border-left:3px solid rgba(231,76,60,0.5); }
.modal-match { display:flex; align-items:center; justify-content:space-between; padding:8px 12px; margin-bottom:6px; background:rgba(255,255,255,0.03); border-radius:6px; font-size:0.85em; }
.modal-match .pred-team { flex:1; text-align:center; padding:4px 8px; border-radius:4px; }
.modal-match .pred-team.winner { background:rgba(46,204,113,0.2); font-weight:bold; }
.modal-match .pred-team.correct { background:rgba(46,204,113,0.3); color:#2ecc71; font-weight:bold; }
.modal-match .pred-team.wrong { background:rgba(231,76,60,0.15); color:#e74c3c; }
.legend { display:flex; gap:16px; margin-bottom:12px; flex-wrap:wrap; font-size:0.8em; color:#aaa; }
.legend-item { display:flex; align-items:center; gap:4px; }
.legend-dot { width:12px; height:12px; border-radius:3px; }
.schifting-display { background:rgba(155,89,182,0.1); border:1px solid rgba(155,89,182,0.3); border-radius:8px; padding:10px 14px; margin:10px 0; font-size:0.9em; }
.schifting-display strong { color:#bb8fce; }
@media (max-width:700px) {
    .leaderboard { font-size:0.85em; }
    .leaderboard th, .leaderboard td { padding:8px 4px; }
    .hide-mobile { display:none; }
}
</style></head><body>
<div class="container">
<h1>&#127942; AZ St Blasius - WK 2026</h1>
<p class="subtitle">Klik op een naam om de voorspellingen te bekijken</p>
<div class="nav-links"><a href="/">&#9917; Voorspelling</a><a href="/admin">&#128272; Admin</a></div>

<div class="punten-info">
<h3>&#128218; Puntensysteem</h3>
<div class="punten-grid">
<span><strong>3pt</strong> juiste positie in groep</span>
<span><strong>10pt</strong> 1/32 finale winnaar</span>
<span><strong>20pt</strong> 1/16 finale winnaar</span>
<span><strong>30pt</strong> 1/8 finale winnaar</span>
<span><strong>50pt</strong> kwartfinale winnaar</span>
<span><strong>100pt</strong> wereldkampioen</span>
</div>
<p style="margin-top:8px;color:#bb8fce;font-size:0.85em;">&#127943; <strong>Tiebreaker:</strong> bij gelijke punten wint wie het dichtst bij het echte aantal doelpunten zit. Antwoorden van deelnemers blijven geheim tot na het toernooi.</p>
</div>

<div class="card">
<h2>&#128203; Rangschikking</h2>
<div id="stats-bar" class="stats-bar"></div>
<div id="scoreboard-content">Laden...</div>
</div>
</div>

<div class="modal-overlay" id="player-modal">
<div class="modal-content">
<button class="modal-close" id="modal-close">&times;</button>
<div id="modal-body"></div>
</div>
</div>

<script>
var allPredictions = {};
var realResults = {};

Promise.all([
    fetch('/api/scoreboard').then(function(r){return r.json();}),
    fetch('/api/predictions').then(function(r){return r.json();}),
    fetch('/api/public/results').then(function(r){return r.json();})
]).then(function(results) {
    var d = results[0];
    allPredictions = results[1];
    realResults = results[2];
    var c = document.getElementById('scoreboard-content');
    var sb = document.getElementById('stats-bar');

    var totalPlayers = d.players ? d.players.length : 0;
    var statsHtml = '<div class="stat-pill">&#127918; ' + totalPlayers + ' deelnemer(s)</div>';
    if (realResults && realResults.totaal_doelpunten !== undefined && realResults.totaal_doelpunten !== null) {
        statsHtml += '<div class="stat-pill purple">&#9917; ' + realResults.totaal_doelpunten + ' doelpunten (echt)</div>';
    }
    sb.innerHTML = statsHtml;

    if (!d.players || !d.players.length) { c.innerHTML = '<p>Nog geen voorspellingen.</p>'; return; }
    var hasGoals = realResults && realResults.totaal_doelpunten !== undefined && realResults.totaal_doelpunten !== null;
    var h = '<table class="leaderboard"><thead><tr><th>#</th><th style="text-align:left;">Speler</th><th>Kampioen</th><th class="hide-mobile">Groep</th><th class="hide-mobile">R32</th><th class="hide-mobile">R16</th><th class="hide-mobile">KF</th><th class="hide-mobile">HF</th><th class="hide-mobile">Win</th><th>TOTAAL</th>';
    if (hasGoals) h += '<th class="hide-mobile">Tiebreaker (&Delta;)</th>';
    h += '</tr></thead><tbody>';
    for (var i = 0; i < d.players.length; i++) {
        var p = d.players[i];
        var rc = i===0?'rank-1':i===1?'rank-2':i===2?'rank-3':'';
        var medal = i===0?'&#129351;':i===1?'&#129352;':i===2?'&#129353;':(i+1);
        h += '<tr class="clickable" data-name="' + escAttr(p.naam) + '">';
        h += '<td class="' + rc + '">' + medal + '</td>';
        h += '<td class="name">' + escHtml(p.naam) + '</td>';
        h += '<td>' + (p.kampioen || '?') + '</td>';
        h += '<td class="hide-mobile">' + p.points.groep_positie + '</td>';
        h += '<td class="hide-mobile">' + p.points.r32 + '</td>';
        h += '<td class="hide-mobile">' + p.points.r16 + '</td>';
        h += '<td class="hide-mobile">' + p.points.qf + '</td>';
        h += '<td class="hide-mobile">' + p.points.sf + '</td>';
        h += '<td class="hide-mobile">' + p.points.winnaar + '</td>';
        h += '<td class="total">' + p.points.totaal + '</td>';
        if (hasGoals) {
            var goalsCell = '-';
            if (p.points.schifting_diff !== null && p.points.schifting_diff !== undefined) {
                goalsCell = '&Delta;' + p.points.schifting_diff;
            }
            h += '<td class="hide-mobile schifting">' + goalsCell + '</td>';
        }
        h += '</tr>';
    }
    h += '</tbody></table>';
    c.innerHTML = h;

    var rows = c.querySelectorAll('tr.clickable');
    for (var i = 0; i < rows.length; i++) {
        rows[i].addEventListener('click', function() { showPlayer(this.getAttribute('data-name')); });
    }
});

function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escAttr(s) { return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

function showPlayer(name) {
    var pred = allPredictions[name];
    if (!pred) return;
    var hasReal = realResults && realResults.groepsfase && Object.keys(realResults.groepsfase).length > 0;
    var body = document.getElementById('modal-body');
    var html = '<h2>&#128100; ' + escHtml(name) + '</h2>';
    html += '<p class="modal-info">Ingediend: <strong>' + (pred.datum || '?') + '</strong></p>';

    if (realResults && realResults.totaal_doelpunten !== undefined && realResults.totaal_doelpunten !== null
        && pred.totaal_doelpunten !== undefined && pred.totaal_doelpunten !== null) {
        var diff = Math.abs(parseInt(realResults.totaal_doelpunten,10) - parseInt(pred.totaal_doelpunten,10));
        html += '<div class="schifting-display">&#127943; <strong>Tiebreaker verschil:</strong> &Delta; ' + diff + ' doelpunten t.o.v. echte uitslag</div>';
    } else {
        html += '<div class="schifting-display">&#127943; <strong>Tiebreaker:</strong> antwoord op de schiftingsvraag is geheim tot de echte uitslag bekend is.</div>';
    }

    if (hasReal) {
        html += '<div class="legend">';
        html += '<div class="legend-item"><div class="legend-dot" style="background:rgba(46,204,113,0.5);"></div> Juist</div>';
        html += '<div class="legend-item"><div class="legend-dot" style="background:rgba(231,76,60,0.3);"></div> Fout</div>';
        html += '</div>';
    }

    html += '<h3>&#128202; Groepsfase</h3>';
    html += '<div class="modal-group-grid">';
    var groups = Object.keys(pred.groepsfase || {}).sort();
    for (var i = 0; i < groups.length; i++) {
        var g = groups[i];
        var teams = pred.groepsfase[g];
        var realTeams = (realResults.groepsfase || {})[g] || [];
        html += '<div class="modal-group"><h4>Groep ' + g + '</h4><ol>';
        for (var j = 0; j < teams.length; j++) {
            var cls = '';
            if (hasReal && realTeams.length > j) {
                cls = (realTeams[j] === teams[j]) ? 'correct' : 'wrong';
            }
            html += '<li class="' + cls + '">' + escHtml(teams[j]) + '</li>';
        }
        html += '</ol></div>';
    }
    html += '</div>';

    var ko = pred.knockout || {};
    var realKo = realResults.knockout || {};
    var rounds = [
        { key: 'ronde_van_32', name: '&#127919; 1/32 Finales (R32)' },
        { key: 'ronde_van_16', name: '&#127919; 1/16 Finales (R16)' },
        { key: 'kwartfinales', name: '&#127919; 1/8 Finales' },
        { key: 'halve_finales', name: '&#127919; Kwartfinales' }
    ];
    for (var r = 0; r < rounds.length; r++) {
        var rd = rounds[r];
        var winners = ko[rd.key];
        if (!winners) continue;
        var realWinners = realKo[rd.key] || {};
        var realSet = {};
        if (typeof realWinners === 'object') {
            for (var k in realWinners) realSet[realWinners[k]] = true;
        }
        html += '<h3>' + rd.name + '</h3>';
        var keys = Object.keys(winners).sort(function(a,b){return parseInt(a)-parseInt(b);});
        for (var k = 0; k < keys.length; k++) {
            var team = winners[keys[k]];
            var cls = 'winner';
            if (hasReal && Object.keys(realSet).length > 0) {
                cls = realSet[team] ? 'correct' : 'wrong';
            }
            html += '<div class="modal-match"><div class="pred-team ' + cls + '">' + escHtml(team) + '</div></div>';
        }
    }

    html += '<h3>&#127942; Wereldkampioen</h3>';
    var champion = ko.finale || '?';
    var champCls = 'winner';
    if (hasReal && realKo.finale) {
        champCls = (realKo.finale === champion) ? 'correct' : 'wrong';
    }
    html += '<div class="modal-match"><div class="pred-team ' + champCls + '" style="font-size:1.2em;padding:10px;">' + escHtml(champion) + '</div></div>';

    body.innerHTML = html;
    document.getElementById('player-modal').classList.add('active');
    document.body.style.overflow = 'hidden';
}

document.getElementById('modal-close').addEventListener('click', function() {
    document.getElementById('player-modal').classList.remove('active');
    document.body.style.overflow = '';
});
document.getElementById('player-modal').addEventListener('click', function(e) {
    if (e.target === this) {
        this.classList.remove('active');
        document.body.style.overflow = '';
    }
});
</script>
</body></html>
"""

# ============================================================
# ADMIN LOGIN
# ============================================================
ADMIN_LOGIN_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Admin Login</title>
<style>
body { font-family:sans-serif; background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460); min-height:100vh; color:#fff; display:flex; align-items:center; justify-content:center; padding:20px; }
.card { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:40px; max-width:400px; width:100%; }
.card h2 { color:#e94560; margin-bottom:20px; text-align:center; }
input { width:100%; padding:14px 20px; border:2px solid rgba(255,255,255,0.2); border-radius:10px; background:rgba(255,255,255,0.05); color:#fff; outline:none; margin-bottom:16px; }
.btn { width:100%; padding:14px; font-size:1.1em; font-weight:bold; border:none; border-radius:10px; cursor:pointer; background:#e94560; color:#fff; }
.error { color:#e94560; text-align:center; margin-top:12px; }
a { color:#aaa; }
</style></head><body>
<div class="card">
<h2>&#128272; Admin Login</h2>
<form method="POST">
<input type="password" name="password" placeholder="Wachtwoord..." autofocus>
<button type="submit" class="btn">Inloggen</button>
</form>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<p style="text-align:center;margin-top:16px;"><a href="/">&larr; Terug</a></p>
</div>
</body></html>
"""

# ============================================================
# ADMIN DASHBOARD
# ============================================================
ADMIN_TEMPLATE = r"""<!DOCTYPE html>
<html lang="nl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',sans-serif; background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460); min-height:100vh; color:#fff; padding:20px; }
.container { max-width:1100px; margin:0 auto; }
h1 { text-align:center; font-size:2.2em; margin-bottom:10px; }
.nav-links { text-align:center; margin-bottom:20px; }
.nav-links a { color:#aaa; text-decoration:none; margin:0 10px; padding:8px 16px; border-radius:8px; background:rgba(255,255,255,0.05); }
.card { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:24px; margin-bottom:20px; }
.card h2 { color:#e94560; margin-bottom:16px; }
.card h3 { color:#f0a500; margin-bottom:12px; }
.tabs { display:flex; gap:8px; margin-bottom:20px; flex-wrap:wrap; }
.tab { padding:10px 20px; border-radius:8px; cursor:pointer; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); color:#aaa; }
.tab.active { background:#e94560; color:#fff; }
.tab-content { display:none; }
.tab-content.active { display:block; }
.group-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:16px; margin-bottom:20px; }
.group-card { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:16px; }
.sortable-list { list-style:none; padding:0; }
.sortable-list li { display:flex; align-items:center; gap:10px; padding:10px 14px; margin-bottom:6px; background:rgba(255,255,255,0.08); border-radius:8px; cursor:grab; user-select:none; }
.sortable-list li.dragging { opacity:0.5; }
.sortable-list li .move-buttons { margin-left:auto; display:flex; gap:4px; }
.sortable-list li .move-btn { width:28px; height:28px; border-radius:50%; border:1px solid rgba(255,255,255,0.3); background:rgba(255,255,255,0.1); color:#fff; cursor:pointer; }
.position-badge { width:24px; height:24px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:0.8em; font-weight:bold; }
.pos-1 { background:#ffd700; color:#000; } .pos-2 { background:#c0c0c0; color:#000; }
.pos-3 { background:#cd7f32; color:#fff; } .pos-4 { background:#555; color:#fff; }
.btn { display:inline-block; padding:14px 32px; font-size:1.1em; font-weight:bold; border:none; border-radius:10px; cursor:pointer; }
.btn-primary { background:#e94560; color:#fff; }
.btn-success { background:#2ecc71; color:#fff; }
.btn-secondary { background:rgba(255,255,255,0.1); color:#fff; border:1px solid rgba(255,255,255,0.2); }
.btn-danger { background:rgba(231,76,60,0.2); color:#e74c3c; border:1px solid #e74c3c; padding:6px 12px; font-size:0.85em; }
.btn-danger:hover { background:#e74c3c; color:#fff; }
.btn-warning { background:rgba(243,156,18,0.2); color:#f39c12; border:1px solid #f39c12; }
.btn-warning:hover { background:#f39c12; color:#fff; }
.btn-small { padding:8px 16px; font-size:0.9em; text-transform:none; }
.btn:disabled { opacity:0.5; cursor:not-allowed; }
.btn-group { display:flex; gap:12px; justify-content:center; margin-top:24px; flex-wrap:wrap; }
.hidden { display:none; }
.drag-hint { color:#888; font-size:0.85em; margin-bottom:12px; font-style:italic; }
.status-msg { padding:12px; border-radius:8px; margin-top:12px; text-align:center; }
.status-msg.success { background:rgba(46,204,113,0.2); border:1px solid #2ecc71; color:#2ecc71; }
.status-msg.error { background:rgba(231,76,60,0.2); border:1px solid #e74c3c; color:#e74c3c; }
.leaderboard { width:100%; border-collapse:collapse; margin-top:12px; }
.leaderboard th { background:rgba(233,69,96,0.2); padding:12px 10px; text-align:center; font-size:0.8em; }
.leaderboard td { padding:10px; border-bottom:1px solid rgba(255,255,255,0.05); text-align:center; }
.leaderboard .name { text-align:left; font-weight:bold; }
.leaderboard .total { font-weight:bold; font-size:1.2em; color:#2ecc71; }
.player-detail-card { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:10px; padding:16px; margin-bottom:12px; }
.player-detail-card h4 { color:#e94560; margin-bottom:8px; }
.player-detail-card .info { color:#aaa; font-size:0.85em; margin-bottom:4px; }
.pay-summary { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-bottom:20px; }
.pay-stat { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.1); border-radius:10px; padding:16px; text-align:center; }
.pay-stat .num { font-size:2em; font-weight:bold; }
.pay-stat .lbl { color:#aaa; font-size:0.85em; margin-top:4px; }
.pay-stat.total .num { color:#ffd700; }
.pay-stat.collected .num { color:#3498db; }
.participants-list { list-style:none; padding:0; }
.participants-row { display:flex; align-items:center; gap:12px; padding:14px; margin-bottom:8px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.1); border-radius:10px; }
.participants-row .pn { flex:1; font-weight:bold; }
.participants-row .pe { color:#aaa; font-size:0.85em; }
.participants-row .pr { color:#3498db; font-size:0.85em; padding:4px 8px; background:rgba(52,152,219,0.15); border-radius:6px; }
.participants-row .pd { color:#888; font-size:0.85em; }
.pay-search { width:100%; padding:12px 16px; margin-bottom:16px; border:2px solid rgba(255,255,255,0.2); border-radius:10px; background:rgba(255,255,255,0.05); color:#fff; font-size:1em; outline:none; }
.iban-display { background:rgba(255,215,0,0.1); border:1px solid rgba(255,215,0,0.3); padding:12px; border-radius:10px; margin-bottom:16px; font-family:'Courier New',monospace; }
.backup-card { background:linear-gradient(135deg,rgba(52,152,219,0.1),rgba(46,204,113,0.05)); border:1px solid rgba(52,152,219,0.3); border-radius:12px; padding:20px; margin-bottom:20px; }
.backup-card h3 { color:#3498db; }
.results-section { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.1); border-radius:12px; padding:20px; margin-bottom:16px; }
.results-section h3 { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; }
.results-section h3 .status { font-size:0.7em; padding:4px 12px; border-radius:12px; font-weight:normal; }
.results-section h3 .status.saved { background:rgba(46,204,113,0.2); color:#2ecc71; border:1px solid #2ecc71; }
.results-section h3 .status.empty { background:rgba(255,255,255,0.05); color:#888; border:1px solid rgba(255,255,255,0.1); }
.team-checklist { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; margin:12px 0; }
.team-check { display:flex; align-items:center; gap:8px; padding:10px 12px; background:rgba(255,255,255,0.04); border:2px solid rgba(255,255,255,0.1); border-radius:8px; cursor:pointer; user-select:none; }
.team-check.checked { background:rgba(46,204,113,0.15); border-color:#2ecc71; }
.team-check input { transform:scale(1.2); accent-color:#2ecc71; }
.counter-badge { display:inline-block; padding:4px 12px; background:rgba(155,89,182,0.2); border:1px solid rgba(155,89,182,0.5); border-radius:12px; font-size:0.85em; color:#bb8fce; margin-left:8px; }
.counter-badge.full { background:rgba(46,204,113,0.2); border-color:#2ecc71; color:#2ecc71; }
.goals-input { width:200px; padding:14px; border:2px solid rgba(155,89,182,0.4); border-radius:10px; background:rgba(155,89,182,0.05); color:#fff; font-size:1.3em; text-align:center; font-weight:bold; }
.intro-info { background:linear-gradient(135deg,rgba(52,152,219,0.1),rgba(155,89,182,0.05)); border-left:4px solid #3498db; padding:14px 18px; border-radius:8px; margin-bottom:20px; line-height:1.6; }
.intro-info strong { color:#3498db; }
@media (max-width:600px) {
    .participants-row { flex-wrap:wrap; }
    .goals-input { width:100%; }
}
</style></head><body>
<div class="container">
<h1>&#128272; Admin Dashboard</h1>
<div class="nav-links"><a href="/">Home</a><a href="/scoreboard">Scoreboard</a><a href="/admin/logout">Uitloggen</a></div>

<div class="tabs">
<div class="tab active" data-tab="participants">&#128101; Deelnemers</div>
<div class="tab" data-tab="results-input">&#9989; Resultaten</div>
<div class="tab" data-tab="leaderboard">&#127942; Rangschikking</div>
<div class="tab" data-tab="all-predictions">&#128203; Voorspellingen</div>
</div>

<div class="tab-content active" id="tab-participants">
<div class="card">
<h2>&#128101; Deelnemers Overzicht</h2>
<div class="iban-display">
<strong>Bankrekening:</strong> %IBAN% &nbsp;|&nbsp; <strong>Inleg:</strong> &euro;%INLEG% per persoon
</div>
<div id="pay-summary" class="pay-summary"></div>
<input type="text" class="pay-search" id="pay-search" placeholder="&#128269; Zoek op naam, e-mail of relatie...">
<div id="participants-container">Laden...</div>
</div>

<div class="backup-card">
<h3>&#128190; Backup</h3>
<p style="color:#ccc;margin-bottom:12px;">Download alle voorspellingen en resultaten als JSON-bestand.</p>
<a href="/api/admin/backup" class="btn btn-success" style="display:inline-block;text-decoration:none;">&#128229; Download Backup</a>
</div>
</div>

<div class="tab-content" id="tab-results-input">
<div class="card">
<h2>&#9989; Echte Resultaten - Per Ronde Opslaan</h2>
<div class="intro-info">
<strong>&#128161; Werkwijze:</strong> Vul tussentijds resultaten in zodra een ronde is afgelopen. Elke sectie heeft een eigen <strong>"Opslaan"</strong> en <strong>"Wissen"</strong> knop.
</div>

<div class="results-section">
<h3>&#128202; 1. Groepsfase (eindstand) <span id="status-groepsfase" class="status empty">Niet ingevuld</span></h3>
<p class="drag-hint">Sleep teams in de juiste eindstand per groep.</p>
<div class="group-grid" id="admin-groups-container"></div>
<div class="btn-group" style="justify-content:flex-start;">
<button class="btn btn-success btn-small" id="save-groepsfase">&#128190; Groepsfase Opslaan</button>
<button class="btn btn-warning btn-small" data-clear="groepsfase">&#128465; Wissen</button>
</div>
<div class="status-msg hidden" id="status-msg-groepsfase"></div>
</div>

<div class="results-section">
<h3>&#127919; 2. 1/32 Finales <span id="status-r32" class="status empty">Niet ingevuld</span> <span id="counter-r32" class="counter-badge">0/16</span></h3>
<p class="drag-hint">Vink de 16 teams aan die de 1/16 finales bereiken.</p>
<div id="r32-container">Vul eerst de groepsfase in &amp; sla op.</div>
<div class="btn-group hidden" style="justify-content:flex-start;" id="save-r32-row">
<button class="btn btn-success btn-small" id="save-r32" disabled>&#128190; R32 Opslaan</button>
<button class="btn btn-warning btn-small" data-clear="ronde_van_32">&#128465; Wissen</button>
</div>
<div class="status-msg hidden" id="status-msg-r32"></div>
</div>

<div class="results-section">
<h3>&#127919; 3. 1/16 Finales <span id="status-r16" class="status empty">Niet ingevuld</span> <span id="counter-r16" class="counter-badge">0/8</span></h3>
<p class="drag-hint">Vink de 8 teams aan die de 1/8 finales bereiken.</p>
<div id="r16-container">Vul eerst R32 in &amp; sla op.</div>
<div class="btn-group hidden" style="justify-content:flex-start;" id="save-r16-row">
<button class="btn btn-success btn-small" id="save-r16" disabled>&#128190; R16 Opslaan</button>
<button class="btn btn-warning btn-small" data-clear="ronde_van_16">&#128465; Wissen</button>
</div>
<div class="status-msg hidden" id="status-msg-r16"></div>
</div>

<div class="results-section">
<h3>&#127919; 4. 1/8 Finales <span id="status-qf" class="status empty">Niet ingevuld</span> <span id="counter-qf" class="counter-badge">0/4</span></h3>
<p class="drag-hint">Vink de 4 teams aan die de kwartfinales bereiken.</p>
<div id="qf-container">Vul eerst R16 in &amp; sla op.</div>
<div class="btn-group hidden" style="justify-content:flex-start;" id="save-qf-row">
<button class="btn btn-success btn-small" id="save-qf" disabled>&#128190; 1/8 Finales Opslaan</button>
<button class="btn btn-warning btn-small" data-clear="kwartfinales">&#128465; Wissen</button>
</div>
<div class="status-msg hidden" id="status-msg-qf"></div>
</div>

<div class="results-section">
<h3>&#127919; 5. Kwartfinales <span id="status-sf" class="status empty">Niet ingevuld</span> <span id="counter-sf" class="counter-badge">0/2</span></h3>
<p class="drag-hint">Vink de 2 finalisten aan.</p>
<div id="sf-container">Vul eerst 1/8 finales in &amp; sla op.</div>
<div class="btn-group hidden" style="justify-content:flex-start;" id="save-sf-row">
<button class="btn btn-success btn-small" id="save-sf" disabled>&#128190; Kwartfinales Opslaan</button>
<button class="btn btn-warning btn-small" data-clear="halve_finales">&#128465; Wissen</button>
</div>
<div class="status-msg hidden" id="status-msg-sf"></div>
</div>

<div class="results-section">
<h3>&#127942; 6. Wereldkampioen <span id="status-finale" class="status empty">Niet ingevuld</span></h3>
<p class="drag-hint">Selecteer de wereldkampioen.</p>
<div id="finale-container">Vul eerst kwartfinales in &amp; sla op.</div>
<div class="btn-group hidden" style="justify-content:flex-start;" id="save-finale-row">
<button class="btn btn-success btn-small" id="save-finale" disabled>&#128190; Kampioen Opslaan</button>
<button class="btn btn-warning btn-small" data-clear="finale">&#128465; Wissen</button>
</div>
<div class="status-msg hidden" id="status-msg-finale"></div>
</div>

<div class="results-section">
<h3>&#9917; 7. Schiftingsvraag - Totaal aantal doelpunten <span id="status-goals" class="status empty">Niet ingevuld</span></h3>
<p class="drag-hint">Vul het werkelijke aantal doelpunten in.</p>
<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
<input type="number" class="goals-input" id="real-goals" placeholder="Bijv. 165" min="0" max="500">
<button class="btn btn-success btn-small" id="save-goals">&#128190; Doelpunten Opslaan</button>
<button class="btn btn-warning btn-small" data-clear="totaal_doelpunten">&#128465; Wissen</button>
</div>
<div class="status-msg hidden" id="status-msg-goals"></div>
</div>

</div>
</div>

<div class="tab-content" id="tab-leaderboard">
<div class="card"><h2>Rangschikking</h2><div id="admin-leaderboard-container">Laden...</div></div>
</div>

<div class="tab-content" id="tab-all-predictions">
<div class="card"><h2>Alle Voorspellingen</h2><div id="all-predictions-container">Laden...</div></div>
</div>
</div>

<script>
(function() {
"use strict";
var GROEPEN = %GROEPEN_JSON%;
var INLEG = %INLEG%;
var allParticipants = [];
var currentResults = {};
var teamSelections = { r32: {}, r16: {}, qf: {}, sf: {}, finale: {} };

document.querySelectorAll('.tab').forEach(function(t) {
    t.addEventListener('click', function() {
        document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});
        document.querySelectorAll('.tab-content').forEach(function(x){x.classList.remove('active');});
        t.classList.add('active');
        document.getElementById('tab-' + t.getAttribute('data-tab')).classList.add('active');
    });
});

function escAttr(s) { return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

function adminBuildGroups() {
    var c = document.getElementById('admin-groups-container');
    c.innerHTML = '';
    var groups = Object.keys(GROEPEN);
    var existing = currentResults.groepsfase || {};
    for (var g = 0; g < groups.length; g++) {
        var group = groups[g];
        var teams = (existing[group] && existing[group].length === GROEPEN[group].length) ? existing[group] : GROEPEN[group];
        var card = document.createElement('div');
        card.className = 'group-card';
        var html = '<h3>Groep ' + group + '</h3><ul class="sortable-list" id="admin-group-' + group + '">';
        for (var i = 0; i < teams.length; i++) {
            html += '<li draggable="true" data-team="' + teams[i] + '">';
            html += '<span class="position-badge pos-' + (i+1) + '">' + (i+1) + '</span>';
            html += '<span>' + teams[i] + '</span>';
            html += '<span class="move-buttons">';
            html += '<button type="button" class="move-btn" data-dir="up">&#9650;</button>';
            html += '<button type="button" class="move-btn" data-dir="down">&#9660;</button>';
            html += '</span></li>';
        }
        html += '</ul>';
        card.innerHTML = html;
        c.appendChild(card);
        var list = card.querySelector('.sortable-list');
        initSortable(list); initMoveButtons(list);
    }
}

function initMoveButtons(list) {
    list.addEventListener('click', function(e) {
        var btn = e.target.closest('.move-btn'); if (!btn) return;
        e.preventDefault(); e.stopPropagation();
        var li = btn.closest('li'), dir = btn.getAttribute('data-dir');
        if (dir === 'up' && li.previousElementSibling) list.insertBefore(li, li.previousElementSibling);
        else if (dir === 'down' && li.nextElementSibling) list.insertBefore(li.nextElementSibling, li);
        updatePositionBadges(list);
    });
}

function initSortable(list) {
    var d = null;
    list.addEventListener('dragstart', function(e) { d = e.target.closest('li'); if (d) d.classList.add('dragging'); });
    list.addEventListener('dragend', function() { if (d) { d.classList.remove('dragging'); d = null; updatePositionBadges(list); } });
    list.addEventListener('dragover', function(e) {
        e.preventDefault(); if (!d) return;
        var a = getDragAfter(list, e.clientY);
        if (a == null) list.appendChild(d); else list.insertBefore(d, a);
    });
}

function getDragAfter(c, y) {
    var els = c.querySelectorAll('li:not(.dragging)'), cl = null, co = -Infinity;
    for (var i = 0; i < els.length; i++) {
        var b = els[i].getBoundingClientRect();
        var o = y - b.top - b.height / 2;
        if (o < 0 && o > co) { co = o; cl = els[i]; }
    }
    return cl;
}

function updatePositionBadges(list) {
    var items = list.querySelectorAll('li');
    for (var i = 0; i < items.length; i++) {
        var b = items[i].querySelector('.position-badge');
        b.className = 'position-badge pos-' + (i + 1);
        b.textContent = i + 1;
    }
}

function adminGetGroupResults() {
    var r = {};
    var groups = Object.keys(GROEPEN);
    for (var g = 0; g < groups.length; g++) {
        var list = document.getElementById('admin-group-' + groups[g]);
        if (!list) continue;
        var items = list.querySelectorAll('li');
        r[groups[g]] = [];
        for (var i = 0; i < items.length; i++) r[groups[g]].push(items[i].getAttribute('data-team'));
    }
    return r;
}

function showStatus(elId, msg, ok) {
    var s = document.getElementById(elId);
    if (!s) return;
    s.classList.remove('hidden');
    s.className = 'status-msg ' + (ok ? 'success' : 'error');
    s.textContent = msg;
    setTimeout(function() { s.classList.add('hidden'); }, 3500);
}

function setSectionStatus(id, filled) {
    var el = document.getElementById('status-' + id);
    if (!el) return;
    if (filled) { el.className = 'status saved'; el.textContent = '\u2713 Opgeslagen'; }
    else { el.className = 'status empty'; el.textContent = 'Niet ingevuld'; }
}

document.getElementById('save-groepsfase').addEventListener('click', function() {
    var data = adminGetGroupResults();
    fetch('/api/admin/results/partial', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ groepsfase: data })
    }).then(function(r){return r.json();}).then(function(res) {
        if (res.success) {
            showStatus('status-msg-groepsfase', 'Groepsfase opgeslagen!', true);
            currentResults = res.results || currentResults;
            currentResults.groepsfase = data;
            setSectionStatus('groepsfase', true);
            renderTeamSelector('r32', 16);
            loadAdminLeaderboard();
        } else showStatus('status-msg-groepsfase', 'Fout: ' + res.error, false);
    });
});

function getAvailableTeams(round) {
    if (round === 'r32') {
        var teams = [];
        var groups = Object.keys(GROEPEN);
        for (var i = 0; i < groups.length; i++) {
            var g = groups[i];
            var stand = (currentResults.groepsfase || {})[g] || [];
            for (var k = 0; k < 3 && k < stand.length; k++) {
                if (stand[k]) teams.push({ name: stand[k], group: g, pos: k+1 });
            }
        }
        return teams;
    }
    var prevSel = null;
    if (round === 'r16') prevSel = (currentResults.knockout || {})['ronde_van_32'];
    else if (round === 'qf') prevSel = (currentResults.knockout || {})['ronde_van_16'];
    else if (round === 'sf') prevSel = (currentResults.knockout || {})['kwartfinales'];
    else if (round === 'finale') prevSel = (currentResults.knockout || {})['halve_finales'];
    if (!prevSel) return [];
    var teams = [];
    var keys = Object.keys(prevSel);
    for (var i = 0; i < keys.length; i++) {
        var t = prevSel[keys[i]];
        if (t) teams.push({ name: t, group: '', pos: 0 });
    }
    return teams;
}

function renderTeamSelector(round, max) {
    var containerId = round + '-container';
    var saveRow = document.getElementById('save-' + round + '-row');
    var c = document.getElementById(containerId);
    var teams = getAvailableTeams(round);
    if (!teams.length) {
        c.innerHTML = '<p style="color:#888;">Vul eerst de vorige ronde in &amp; sla op.</p>';
        if (saveRow) saveRow.classList.add('hidden');
        return;
    }
    if (saveRow) saveRow.classList.remove('hidden');

    var preSelected = {};
    var koMap = { r32: 'ronde_van_32', r16: 'ronde_van_16', qf: 'kwartfinales', sf: 'halve_finales', finale: 'finale' };
    var existing = (currentResults.knockout || {})[koMap[round]];
    if (existing) {
        if (round === 'finale') {
            preSelected[existing] = true;
        } else if (typeof existing === 'object') {
            for (var k in existing) preSelected[existing[k]] = true;
        }
    }
    teamSelections[round] = {};
    for (var k in preSelected) teamSelections[round][k] = true;

    var html = '<div class="team-checklist">';
    for (var i = 0; i < teams.length; i++) {
        var t = teams[i];
        var lbl = t.name;
        if (t.group) lbl += ' <span style="color:#888;font-size:0.8em;">(Gr.' + t.group + ' #' + t.pos + ')</span>';
        var checkedCls = preSelected[t.name] ? ' checked' : '';
        var checkedAttr = preSelected[t.name] ? ' checked' : '';
        html += '<label class="team-check' + checkedCls + '" data-team="' + escAttr(t.name) + '">';
        html += '<input type="checkbox"' + checkedAttr + ' data-round="' + round + '" data-team="' + escAttr(t.name) + '">';
        html += '<span>' + lbl + '</span></label>';
    }
    html += '</div>';
    c.innerHTML = html;

    var checks = c.querySelectorAll('input[type="checkbox"]');
    for (var i = 0; i < checks.length; i++) {
        checks[i].addEventListener('change', function() {
            var team = this.getAttribute('data-team');
            var rd = this.getAttribute('data-round');
            var lbl = this.closest('.team-check');
            if (this.checked) {
                var count = Object.keys(teamSelections[rd]).length;
                if (count >= max) {
                    this.checked = false;
                    alert('Je hebt al ' + max + ' teams geselecteerd!');
                    return;
                }
                teamSelections[rd][team] = true;
                lbl.classList.add('checked');
            } else {
                delete teamSelections[rd][team];
                lbl.classList.remove('checked');
            }
            updateCounter(rd, max);
        });
    }
    updateCounter(round, max);
}

function updateCounter(round, max) {
    var c = document.getElementById('counter-' + round);
    var btn = document.getElementById('save-' + round);
    var n = Object.keys(teamSelections[round]).length;
    if (c) {
        c.textContent = n + '/' + max;
        c.className = 'counter-badge' + (n === max ? ' full' : '');
    }
    if (btn) btn.disabled = (n !== max);
}

function saveRound(round, max, koKey) {
    var sel = Object.keys(teamSelections[round]);
    if (sel.length !== max) {
        alert('Selecteer exact ' + max + ' teams!');
        return;
    }
    if (round === 'finale') {
        var payload = { knockout: {} };
        payload.knockout[koKey] = sel[0];
        fetch('/api/admin/results/partial', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify(payload)
        }).then(function(r){return r.json();}).then(function(res){
            if (res.success) {
                showStatus('status-msg-' + round, 'Wereldkampioen opgeslagen!', true);
                if (!currentResults.knockout) currentResults.knockout = {};
                currentResults.knockout[koKey] = sel[0];
                setSectionStatus(round, true);
                loadAdminLeaderboard();
            } else showStatus('status-msg-' + round, 'Fout: ' + res.error, false);
        });
        return;
    }
    var koObj = {};
    for (var i = 0; i < sel.length; i++) koObj[i] = sel[i];
    var payload = { knockout: {} };
    payload.knockout[koKey] = koObj;
    fetch('/api/admin/results/partial', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(payload)
    }).then(function(r){return r.json();}).then(function(res) {
        if (res.success) {
            showStatus('status-msg-' + round, round.toUpperCase() + ' opgeslagen!', true);
            if (!currentResults.knockout) currentResults.knockout = {};
            currentResults.knockout[koKey] = koObj;
            setSectionStatus(round, true);
            var nextMap = { r32: ['r16', 8], r16: ['qf', 4], qf: ['sf', 2], sf: ['finale', 1] };
            if (nextMap[round]) {
                renderTeamSelector(nextMap[round][0], nextMap[round][1]);
            }
            loadAdminLeaderboard();
        } else showStatus('status-msg-' + round, 'Fout: ' + res.error, false);
    });
}

document.getElementById('save-r32').addEventListener('click', function() { saveRound('r32', 16, 'ronde_van_32'); });
document.getElementById('save-r16').addEventListener('click', function() { saveRound('r16', 8, 'ronde_van_16'); });
document.getElementById('save-qf').addEventListener('click', function() { saveRound('qf', 4, 'kwartfinales'); });
document.getElementById('save-sf').addEventListener('click', function() { saveRound('sf', 2, 'halve_finales'); });
document.getElementById('save-finale').addEventListener('click', function() { saveRound('finale', 1, 'finale'); });

document.getElementById('save-goals').addEventListener('click', function() {
    var v = document.getElementById('real-goals').value.trim();
    var n = parseInt(v, 10);
    if (isNaN(n) || n < 0 || n > 500) {
        showStatus('status-msg-goals', 'Vul een geldig aantal in (0-500)!', false);
        return;
    }
    fetch('/api/admin/results/partial', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ totaal_doelpunten: n })
    }).then(function(r){return r.json();}).then(function(res){
        if (res.success) {
            showStatus('status-msg-goals', 'Aantal doelpunten opgeslagen!', true);
            currentResults.totaal_doelpunten = n;
            setSectionStatus('goals', true);
            loadAdminLeaderboard();
        } else showStatus('status-msg-goals', 'Fout: ' + res.error, false);
    });
});

document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-clear]');
    if (!btn) return;
    var section = btn.getAttribute('data-clear');
    var labels = {
        'groepsfase': 'groepsfase',
        'ronde_van_32': '1/32 finales (R32)',
        'ronde_van_16': '1/16 finales (R16)',
        'kwartfinales': '1/8 finales',
        'halve_finales': 'kwartfinales',
        'finale': 'wereldkampioen',
        'totaal_doelpunten': 'doelpunten (schiftingsvraag)'
    };
    if (!confirm('Weet je zeker dat je "' + (labels[section] || section) + '" wilt wissen?')) return;
    fetch('/api/admin/results/clear', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ section: section })
    }).then(function(r){return r.json();}).then(function(res) {
        if (!res.success) {
            alert('Fout: ' + res.error);
            return;
        }
        currentResults = res.results || {};
        var statusMap = {
            'groepsfase': 'groepsfase',
            'ronde_van_32': 'r32',
            'ronde_van_16': 'r16',
            'kwartfinales': 'qf',
            'halve_finales': 'sf',
            'finale': 'finale',
            'totaal_doelpunten': 'goals'
        };
        var sId = statusMap[section];
        if (sId) setSectionStatus(sId, false);

        if (section === 'groepsfase') {
            adminBuildGroups();
            ['r32','r16','qf','sf','finale'].forEach(function(rd){
                var el = document.getElementById(rd + '-container');
                if (el) el.innerHTML = '<p style="color:#888;">Vul eerst de vorige ronde in &amp; sla op.</p>';
                var row = document.getElementById('save-' + rd + '-row');
                if (row) row.classList.add('hidden');
                teamSelections[rd] = {};
                setSectionStatus(rd, false);
            });
        } else if (section === 'totaal_doelpunten') {
            document.getElementById('real-goals').value = '';
        } else {
            var order = ['ronde_van_32','ronde_van_16','kwartfinales','halve_finales','finale'];
            var rdMap = {'ronde_van_32':'r32','ronde_van_16':'r16','kwartfinales':'qf','halve_finales':'sf','finale':'finale'};
            var maxMap = {'r32':16,'r16':8,'qf':4,'sf':2,'finale':1};
            var idx = order.indexOf(section);
            for (var i = idx; i < order.length; i++) {
                var rd = rdMap[order[i]];
                teamSelections[rd] = {};
                setSectionStatus(rd, false);
                if (i > idx) {
                    var el = document.getElementById(rd + '-container');
                    if (el) el.innerHTML = '<p style="color:#888;">Vul eerst de vorige ronde in &amp; sla op.</p>';
                    var row = document.getElementById('save-' + rd + '-row');
                    if (row) row.classList.add('hidden');
                }
            }
            var thisRd = rdMap[section];
            if (thisRd && getAvailableTeams(thisRd).length) {
                renderTeamSelector(thisRd, maxMap[thisRd]);
            }
        }
        loadAdminLeaderboard();
        showStatus('status-msg-' + (statusMap[section] || 'groepsfase'), '\u2713 ' + (labels[section] || section) + ' gewist!', true);
    });
});

function loadParticipants() {
    fetch('/api/admin/payments').then(function(r){return r.json();}).then(function(d) {
        allParticipants = d.players || [];
        renderSummary();
        renderParticipantsList(allParticipants);
    });
}

function renderSummary() {
    var total = allParticipants.length;
    var html = '';
    html += '<div class="pay-stat total"><div class="num">' + total + '</div><div class="lbl">Deelnemers</div></div>';
    html += '<div class="pay-stat collected"><div class="num">&euro;' + (total * INLEG) + '</div><div class="lbl">Verwacht totaal</div></div>';
    html += '<div class="pay-stat collected"><div class="num">&euro;' + (total * INLEG / 2).toFixed(0) + '</div><div class="lbl">&#10084;&#65039; Naar goed doel</div></div>';
    html += '<div class="pay-stat collected"><div class="num">&euro;' + (total * INLEG / 2).toFixed(0) + '</div><div class="lbl">&#127942; Voor winnaars</div></div>';
    document.getElementById('pay-summary').innerHTML = html;
}

function renderParticipantsList(list) {
    var c = document.getElementById('participants-container');
    if (!list.length) { c.innerHTML = '<p style="color:#aaa;">Nog geen deelnemers.</p>'; return; }
    list.sort(function(a,b){ return (a.datum || '').localeCompare(b.datum || ''); });
    var h = '<ul class="participants-list">';
    for (var i = 0; i < list.length; i++) {
        var p = list[i];
        h += '<li class="participants-row">';
        h += '<div style="flex:1;min-width:200px;">';
        h += '<div class="pn">' + escAttr(p.naam) + '</div>';
        if (p.email) h += '<div class="pe">&#9993; ' + escAttr(p.email) + '</div>';
        h += '<div class="pd">Ingediend: ' + (p.datum||'?') + '</div>';
        if (p.totaal_doelpunten !== undefined && p.totaal_doelpunten !== null) {
            h += '<div class="pd" style="color:#bb8fce;">&#9917; Voorspelt: ' + p.totaal_doelpunten + ' doelpunten</div>';
        }
        h += '</div>';
        if (p.relatie) h += '<span class="pr">' + escAttr(p.relatie) + '</span>';
        h += '<button class="btn btn-danger" data-delete="' + escAttr(p.naam) + '">&#128465; Verwijder</button>';
        h += '</li>';
    }
    h += '</ul>';
    c.innerHTML = h;

    var delBtns = c.querySelectorAll('[data-delete]');
    for (var i = 0; i < delBtns.length; i++) {
        delBtns[i].addEventListener('click', function() {
            var name = this.getAttribute('data-delete');
            if (!confirm('Voorspelling van "' + name + '" verwijderen?')) return;
            fetch('/api/admin/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({naam:name}) })
            .then(function(r){return r.json();}).then(function(res) {
                if (res.success) { loadParticipants(); loadAdminLeaderboard(); loadAllPredictions(); }
                else alert('Fout: ' + res.error);
            });
        });
    }
}

function filterParticipants() {
    var q = document.getElementById('pay-search').value.toLowerCase().trim();
    if (!q) return allParticipants;
    return allParticipants.filter(function(p){
        return (p.naam||'').toLowerCase().indexOf(q) >= 0
            || (p.email||'').toLowerCase().indexOf(q) >= 0
            || (p.relatie||'').toLowerCase().indexOf(q) >= 0;
    });
}

document.getElementById('pay-search').addEventListener('input', function() {
    renderParticipantsList(filterParticipants());
});

function loadAdminLeaderboard() {
    fetch('/api/scoreboard').then(function(r){return r.json();}).then(function(d) {
        var c = document.getElementById('admin-leaderboard-container');
        if (!d.players || !d.players.length) { c.innerHTML = '<p>Nog geen voorspellingen.</p>'; return; }
        var h = '<table class="leaderboard"><thead><tr><th>#</th><th style="text-align:left;">Speler</th><th>Kampioen</th><th>Groep</th><th>R32</th><th>R16</th><th>KF</th><th>HF</th><th>Win</th><th>TOTAAL</th><th>Goals (&Delta;)</th></tr></thead><tbody>';
        for (var i = 0; i < d.players.length; i++) {
            var p = d.players[i];
            h += '<tr><td>'+(i+1)+'</td><td class="name">'+p.naam+'</td><td>'+(p.kampioen||'?')+'</td>';
            h += '<td>'+p.points.groep_positie+'</td>';
            h += '<td>'+p.points.r32+'</td><td>'+p.points.r16+'</td><td>'+p.points.qf+'</td><td>'+p.points.sf+'</td>';
            h += '<td>'+p.points.winnaar+'</td>';
            h += '<td class="total">'+p.points.totaal+'</td>';
            var g = (p.totaal_doelpunten !== undefined && p.totaal_doelpunten !== null) ? p.totaal_doelpunten : '-';
            if (p.points.schifting_diff !== null && p.points.schifting_diff !== undefined) {
                g += ' (\u0394' + p.points.schifting_diff + ')';
            }
            h += '<td>'+g+'</td></tr>';
        }
        h += '</tbody></table>';
        c.innerHTML = h;
    });
}

function loadAllPredictions() {
    fetch('/api/predictions').then(function(r){return r.json();}).then(function(d) {
        var c = document.getElementById('all-predictions-container');
        var names = Object.keys(d);
        if (!names.length) { c.innerHTML = '<p>Nog geen voorspellingen.</p>'; return; }
        var h = '<p style="color:#aaa;">' + names.length + ' voorspelling(en)</p>';
        for (var i = 0; i < names.length; i++) {
            var p = d[names[i]];
            h += '<div class="player-detail-card"><h4>' + p.naam + '</h4>';
            if (p.email) h += '<div class="info">&#9993; ' + p.email + '</div>';
            if (p.relatie) h += '<div class="info">&#127973; ' + p.relatie + '</div>';
            h += '<div class="info">Kampioen: <strong style="color:#ffd700;">' + (p.knockout ? p.knockout.finale : '?') + '</strong></div>';
            if (p.totaal_doelpunten !== undefined && p.totaal_doelpunten !== null) {
                h += '<div class="info">&#9917; Voorspelt: <strong style="color:#bb8fce;">' + p.totaal_doelpunten + ' doelpunten</strong></div>';
            }
            h += '<div class="info">Ingediend: ' + (p.datum || '?') + '</div></div>';
        }
        c.innerHTML = h;
    });
}

function loadCurrentResults() {
    fetch('/api/admin/results').then(function(r){return r.json();}).then(function(d) {
        currentResults = d || {};
        adminBuildGroups();
        if (currentResults.groepsfase && Object.keys(currentResults.groepsfase).length === 12) {
            setSectionStatus('groepsfase', true);
            renderTeamSelector('r32', 16);
        }
        var ko = currentResults.knockout || {};
        if (ko.ronde_van_32 && Object.keys(ko.ronde_van_32).length === 16) {
            setSectionStatus('r32', true);
            renderTeamSelector('r16', 8);
        }
        if (ko.ronde_van_16 && Object.keys(ko.ronde_van_16).length === 8) {
            setSectionStatus('r16', true);
            renderTeamSelector('qf', 4);
        }
        if (ko.kwartfinales && Object.keys(ko.kwartfinales).length === 4) {
            setSectionStatus('qf', true);
            renderTeamSelector('sf', 2);
        }
        if (ko.halve_finales && Object.keys(ko.halve_finales).length === 2) {
            setSectionStatus('sf', true);
            renderTeamSelector('finale', 1);
        }
        if (ko.finale) {
            setSectionStatus('finale', true);
        }
        if (currentResults.totaal_doelpunten !== undefined && currentResults.totaal_doelpunten !== null) {
            setSectionStatus('goals', true);
            document.getElementById('real-goals').value = currentResults.totaal_doelpunten;
        }
    });
}

loadCurrentResults();
loadParticipants();
loadAdminLeaderboard();
loadAllPredictions();
})();
</script>
</body></html>
"""


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    groepen_json = json.dumps(GROEPEN, ensure_ascii=False)
    r32_json = json.dumps(R32_STRUCTURE, ensure_ascii=False)
    html = HTML_TEMPLATE.replace('%GROEPEN_JSON%', groepen_json)
    html = html.replace('%R32_STRUCTURE_JSON%', r32_json)
    html = html.replace('%IBAN%', IBAN)
    html = html.replace('%INLEG%', str(INLEG))
    return html


@app.route('/scoreboard')
def scoreboard():
    return render_template_string(SCOREBOARD_TEMPLATE)


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        if request.form.get('password', '') == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        error = "Onjuist wachtwoord!"
    return render_template_string(ADMIN_LOGIN_TEMPLATE, error=error)


@app.route('/admin')
@admin_required
def admin_dashboard():
    groepen_json = json.dumps(GROEPEN, ensure_ascii=False)
    r32_json = json.dumps(R32_STRUCTURE, ensure_ascii=False)
    html = ADMIN_TEMPLATE.replace('%GROEPEN_JSON%', groepen_json)
    html = html.replace('%R32_STRUCTURE_JSON%', r32_json)
    html = html.replace('%IBAN%', IBAN)
    html = html.replace('%INLEG%', str(INLEG))
    return html


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))


@app.route('/api/qr')
def api_qr():
    try:
        naam = request.args.get('naam', '').strip()
        if not naam:
            return jsonify({"success": False, "error": "Naam vereist"})
        communication = "WK2026 - " + naam
        payload = generate_epc_payload(BEGUNSTIGDE, IBAN_CLEAN, INLEG, communication)
        qr_b64 = generate_qr_image_base64(payload)
        return jsonify({"success": True, "qr": qr_b64, "mededeling": communication})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/submit', methods=['POST'])
def api_submit():
    try:
        data = request.get_json()
        naam = data.get('naam', '').strip()
        if not naam:
            return jsonify({"success": False, "error": "Naam is verplicht"})
        if not data.get('email', '').strip():
            return jsonify({"success": False, "error": "Email is verplicht"})
        if not data.get('relatie', '').strip():
            return jsonify({"success": False, "error": "Relatie is verplicht"})
        save_prediction(naam, data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/predictions')
def api_predictions():
    return jsonify(load_data())


@app.route('/api/public/results')
def api_public_results():
    return jsonify(load_results())


@app.route('/api/scoreboard')
def api_scoreboard():
    predictions = load_data()
    real_results = load_results()
    players = []
    for naam, pred in predictions.items():
        points = calculate_points(pred, real_results)
        players.append({
            "naam": naam,
            "kampioen": (pred.get("knockout") or {}).get("finale"),
            "datum": pred.get("datum"),
            "totaal_doelpunten": pred.get("totaal_doelpunten"),
            "points": points
        })

    def sort_key(p):
        diff = p["points"].get("schifting_diff")
        diff_val = diff if diff is not None else 9999
        return (-p["points"]["totaal"], diff_val)

    players.sort(key=sort_key)
    return jsonify({"players": players, "real_results": real_results})


@app.route('/api/admin/results', methods=['GET'])
@admin_required
def api_admin_results_get():
    return jsonify(load_results())


@app.route('/api/admin/results/partial', methods=['POST'])
@admin_required
def api_admin_results_partial():
    try:
        data = request.get_json()
        updated = update_results_partial(data)
        return jsonify({"success": True, "results": updated})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/admin/results/clear', methods=['POST'])
@admin_required
def api_admin_results_clear():
    try:
        data = request.get_json()
        section = data.get('section')
        if not section:
            return jsonify({"success": False, "error": "section vereist"})
        updated = clear_results_section(section)
        return jsonify({"success": True, "results": updated})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/admin/payments')
@admin_required
def api_admin_payments():
    predictions = load_data()
    players = []
    for naam, pred in predictions.items():
        players.append({
            "naam": naam,
            "email": pred.get("email", ""),
            "relatie": pred.get("relatie", ""),
            "datum": pred.get("datum", ""),
            "totaal_doelpunten": pred.get("totaal_doelpunten"),
        })
    return jsonify({"players": players})


@app.route('/api/admin/delete', methods=['POST'])
@admin_required
def api_admin_delete():
    try:
        data = request.get_json()
        naam = data.get('naam', '').strip()
        if not naam:
            return jsonify({"success": False, "error": "naam vereist"})
        delete_prediction(naam)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/admin/backup')
@admin_required
def api_admin_backup():
    backup = {
        "voorspellingen": load_data(),
        "echte_resultaten": load_results(),
        "exported_at": datetime.now().isoformat(),
    }
    response = Response(
        json.dumps(backup, ensure_ascii=False, indent=2),
        mimetype='application/json'
    )
    filename = "wk2026-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json"
    response.headers['Content-Disposition'] = 'attachment; filename=' + filename
    return response


# ============================================================
# RUN
# ============================================================
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
