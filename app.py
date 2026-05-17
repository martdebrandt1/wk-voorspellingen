#!/usr/bin/env python3
"""
WK 2026 Voorspellingstool - Web App (48 teams, 12 groepen)
"""

from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
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
    """EPC069-12 SEPA QR payload."""
    name = name[:70]
    communication = communication[:140]
    amount_str = "EUR{:.2f}".format(amount_eur)
    lines = ["BCD", "002", "1", "SCT", "", name, iban, amount_str, "", "", communication, ""]
    return "\n".join(lines)


def generate_qr_image_base64(payload):
    """Genereer PNG QR-code als base64 string."""
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
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS voorspellingen (naam TEXT PRIMARY KEY, data TEXT NOT NULL, datum TEXT NOT NULL, betaald INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS echte_resultaten (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL, datum TEXT NOT NULL)")
    try:
        c.execute("ALTER TABLE voorspellingen ADD COLUMN betaald INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def load_data():
    conn = sqlite3.connect(DB_FILE)
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
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    datum = datetime.now().strftime("%Y-%m-%d %H:%M")
    data['datum'] = datum
    c.execute("SELECT betaald FROM voorspellingen WHERE naam = ?", (naam,))
    row = c.fetchone()
    betaald = row[0] if row else 0
    c.execute("INSERT OR REPLACE INTO voorspellingen (naam, data, datum, betaald) VALUES (?, ?, ?, ?)",
              (naam, json.dumps(data, ensure_ascii=False), datum, betaald))
    conn.commit()
    conn.close()

def set_paid_status(naam, betaald):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE voorspellingen SET betaald = ? WHERE naam = ?", (1 if betaald else 0, naam))
    conn.commit()
    conn.close()

def delete_prediction(naam):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM voorspellingen WHERE naam = ?", (naam,))
    conn.commit()
    conn.close()

def load_results():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT data FROM echte_resultaten WHERE id = 1")
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else {}

def save_results(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    datum = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT OR REPLACE INTO echte_resultaten (id, data, datum) VALUES (1, ?, ?)",
              (json.dumps(data, ensure_ascii=False), datum))
    conn.commit()
    conn.close()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


def calculate_points(prediction, real_results):
    points = {"groep_positie":0,"r32":0,"r16":0,"qf":0,"sf":0,"winnaar":0,"totaal":0}
    if not real_results:
        return points
    real_groups = real_results.get("groepsfase", {})
    pred_groups = prediction.get("groepsfase", {})
    for group in pred_groups:
        if group not in real_groups: continue
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
        rr = real_ko.get(key, {}); pr = pred_ko.get(key, {})
        if rr and pr:
            rw = set(rr.values()) if isinstance(rr,dict) else set()
            pw = set(pr.values()) if isinstance(pr,dict) else set()
            points[pk] = len(rw & pw) * pp
    if real_ko.get("finale") and pred_ko.get("finale") == real_ko.get("finale"):
        points["winnaar"] = PUNTEN["winnaar_juist"]
    points["totaal"] = sum(points[k] for k in ["groep_positie","r32","r16","qf","sf","winnaar"])
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
.name-input, .form-input, .form-select { width:100%; padding:14px 20px; font-size:1.05em; border:2px solid rgba(255,255,255,0.2); border-radius:10px; background:rgba(255,255,255,0.05); color:#fff; outline:none; }
.form-select option { background:#1a1a2e; color:#fff; }
.name-input:focus, .form-input:focus, .form-select:focus { border-color:#e94560; }
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
<p>&#127881; <strong>Het is weer zover!</strong> Onze 2-jaarlijkse traditie is terug: de grote AZ St Blasius voetbalpoule! Of het nu de Wereldbeker of het EK is &mdash; wij voorspellen er lustig op los.</p>

<p>&#127918; <strong>Je hoeft GEEN voetbalkenner te zijn!</strong> Wie weet zit jij straks bovenaan met je &laquo;buikgevoel-tactiek&raquo;. We hebben in het verleden al gezien dat de stagiaire die nog nooit een match gezien heeft, de kenners om de oren slaat. &#128514;</p>

<p>&#129309; <strong>Meedoen is belangrijker dan winnen.</strong> Het draait om de plezier, de discussies aan de koffieautomaat en het samen leven met onze favorieten op het veld.</p>

<div class="intro-highlight">
&#10084;&#65039; <strong>De helft van de inleg gaat naar het goede doel.</strong> De andere helft wordt verdeeld over de top-voorspellers. Win-win voor iedereen!
</div>

<p>&#9917; Klaar? Vul hieronder je gegevens in en laat de voorspellingen beginnen!</p>
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
<select class="form-select" id="player-relation">
<option value="">-- Maak een keuze --</option>
<option value="Medewerker">Medewerker</option>
<option value="Arts">Arts</option>
<option value="Verpleegkundige">Verpleegkundige</option>
<option value="Vrijwilliger">Vrijwilliger</option>
<option value="Stagiair">Stagiair(e)</option>
<option value="Familie van medewerker">Familie van medewerker</option>
<option value="Vriend(in) van medewerker">Vriend(in) van medewerker</option>
<option value="Patient">Patiënt / Bezoeker</option>
<option value="Andere">Andere</option>
</select>
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
&#9888; <strong>Belangrijk:</strong> De QR-code bevat <strong>automatisch jouw naam</strong> in de mededeling, zodat we de betaling kunnen koppelen aan je voorspelling.
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
<p style="color:#aaa;margin:20px 0;">Veel succes! Hou het scoreboard in de gaten tijdens het toernooi. &#9917;</p>
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
        container.innerHTML = 'Fout bij laden QR-code. Gebruik handmatige gegevens hieronder.';
    });
}

function validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function goToStep(step) {
    if (step === 2) {
        var nameVal = document.getElementById('player-name').value.trim();
        var emailVal = document.getElementById('player-email').value.trim();
        var relationVal = document.getElementById('player-relation').value;
        var errorEl = document.getElementById('form-error');
        if (!nameVal || !emailVal || !relationVal) {
            errorEl.textContent = '\u26A0 Vul alle velden in!';
            errorEl.classList.add('show'); return;
        }
        if (!validateEmail(emailVal)) {
            errorEl.textContent = '\u26A0 Vul een geldig e-mailadres in!';
            errorEl.classList.add('show'); return;
        }
        errorEl.classList.remove('show');
    }
    if (step === 3) {
        groupPredictions = getGroupResults();
        buildKnockout();
    }
    if (step === 4) {
        if (!knockoutSelections.final_round || knockoutSelections.final_round[0] === undefined) {
            alert('Vul eerst alle knock-out wedstrijden in!'); return;
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
    html += '<p class="drag-hint">Voor elke wedstrijd: kies welk #3 team daadwerkelijk speelt. Elk team kan maar 1x. De 4 niet-gekozen #3 teams gaan naar huis.</p>';
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
    renderRound(container, '1/16 Finales', matches, 'r32');
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
    var names = { r32: '1/8 Finales', r16: 'Kwartfinales', qf: 'Halve Finales', sf: '&#127942; FINALE' };
    if (Object.keys(knockoutSelections[rk]).length < counts[rk]) return;
    var nk = nexts[rk]; if (!nk) return;
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
    renderRound(container, names[rk], nm, nk);
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
    } else {
        var ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); } catch(e) {}
        document.body.removeChild(ta);
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
    var relation = document.getElementById('player-relation').value;
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
['player-name','player-email','player-relation'].forEach(function(id){
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
.leaderboard .name:hover { color:#e94560; text-decoration:underline; }
.leaderboard .total { font-weight:bold; font-size:1.3em; color:#2ecc71; }
.rank-1{color:#ffd700;} .rank-2{color:#c0c0c0;} .rank-3{color:#cd7f32;}
.punten-info { background:rgba(255,215,0,0.08); border:1px solid rgba(255,215,0,0.2); border-radius:12px; padding:16px; margin-bottom:20px; }
.punten-info h3 { color:#ffd700; margin-bottom:8px; font-size:1em; }
.punten-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:4px; }
.punten-grid span { color:#ccc; font-size:0.85em; }
.punten-grid strong { color:#fff; }
.stats-bar { display:flex; gap:12px; margin-bottom:16px; flex-wrap:wrap; }
.stat-pill { background:rgba(46,204,113,0.15); border:1px solid rgba(46,204,113,0.3); padding:8px 14px; border-radius:20px; font-size:0.9em; }
.modal-overlay { display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.85); z-index:1000; padding:20px; overflow-y:auto; }
.modal-overlay.active { display:block; }
.modal-content { max-width:900px; margin:20px auto; background:linear-gradient(135deg,#1a1a2e,#16213e); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:30px; position:relative; }
.modal-close { position:absolute; top:15px; right:15px; width:40px; height:40px; border-radius:50%; border:none; background:rgba(233,69,96,0.2); color:#fff; font-size:1.5em; cursor:pointer; }
.modal-close:hover { background:#e94560; }
.modal-content h2 { color:#e94560; margin-bottom:8px; }
.modal-content h3 { color:#f0a500; margin:20px 0 10px 0; padding-bottom:6px; border-bottom:1px solid rgba(255,255,255,0.1); }
.modal-info { color:#aaa; font-size:0.9em; margin-bottom:20px; }
.modal-info strong { color:#ffd700; }
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
<span><strong>3pt</strong> juiste positie in groep (max 12/groep)</span>
<span><strong>10pt</strong> 1/16 finale winnaar</span>
<span><strong>20pt</strong> 1/8 finale winnaar</span>
<span><strong>30pt</strong> kwartfinale winnaar</span>
<span><strong>50pt</strong> halve finale winnaar</span>
<span><strong>100pt</strong> wereldkampioen</span>
</div>
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
    sb.innerHTML = statsHtml;

    if (!d.players || !d.players.length) { c.innerHTML = '<p>Nog geen voorspellingen.</p>'; return; }
    var h = '<table class="leaderboard"><thead><tr><th>#</th><th style="text-align:left;">Speler</th><th>Kampioen</th><th class="hide-mobile">Groep</th><th class="hide-mobile">R32</th><th class="hide-mobile">R16</th><th class="hide-mobile">KF</th><th class="hide-mobile">HF</th><th class="hide-mobile">Win</th><th>TOTAAL</th></tr></thead><tbody>';
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
        h += '</tr>';
    }
    h += '</tbody></table>';
    if (d.results_available) h += '<p style="text-align:center;color:#666;font-size:0.8em;margin-top:12px;">&#9989; Echte resultaten ingevuld</p>';
    else h += '<p style="text-align:center;color:#666;font-size:0.8em;margin-top:12px;">&#9888; Nog geen echte resultaten</p>';
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
        { key: 'ronde_van_32', name: '&#127919; 1/16 Finales (R32)' },
        { key: 'ronde_van_16', name: '&#127919; 1/8 Finales (R16)' },
        { key: 'kwartfinales', name: '&#127919; Kwartfinales' },
        { key: 'halve_finales', name: '&#127919; Halve Finales' }
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
.container { max-width:1000px; margin:0 auto; }
h1 { text-align:center; font-size:2.2em; margin-bottom:10px; }
.subtitle { text-align:center; color:#aaa; margin-bottom:30px; }
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
.step-indicator { display:flex; justify-content:center; gap:8px; margin-bottom:20px; flex-wrap:wrap; }
.step { padding:8px 14px; border-radius:20px; background:rgba(255,255,255,0.1); font-size:0.8em; }
.step.active { background:#e94560; font-weight:bold; }
.step.done { background:#2ecc71; }
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
.match-card { display:flex; align-items:center; justify-content:space-between; padding:12px 16px; margin-bottom:10px; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:10px; gap:10px; }
.match-team { flex:1; text-align:center; padding:10px; border-radius:8px; cursor:pointer; border:2px solid transparent; }
.match-team.selected { background:rgba(46,204,113,0.2); border-color:#2ecc71; }
.match-vs { font-weight:bold; color:#e94560; font-size:0.9em; }
.knockout-round { margin-bottom:24px; }
.knockout-round h3 { margin-bottom:12px; padding-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.1); }
.btn { display:inline-block; padding:14px 32px; font-size:1.1em; font-weight:bold; border:none; border-radius:10px; cursor:pointer; }
.btn-primary { background:#e94560; color:#fff; }
.btn-success { background:#2ecc71; color:#fff; }
.btn-secondary { background:rgba(255,255,255,0.1); color:#fff; border:1px solid rgba(255,255,255,0.2); }
.btn-danger { background:rgba(231,76,60,0.2); color:#e74c3c; border:1px solid #e74c3c; padding:6px 12px; font-size:0.85em; }
.btn-danger:hover { background:#e74c3c; color:#fff; }
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
.third-assign-select { width:100%; padding:10px; border-radius:8px; background:rgba(0,0,0,0.4); color:#fff; border:2px solid rgba(255,255,255,0.2); font-size:1em; }
.third-assign-select option { background:#1a1a2e; color:#fff; }
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
.pay-search:focus { border-color:#e94560; }
.iban-display { background:rgba(255,215,0,0.1); border:1px solid rgba(255,215,0,0.3); padding:12px; border-radius:10px; margin-bottom:16px; font-family:'Courier New',monospace; }
@media (max-width:600px) {
    .match-card { flex-direction:column; }
    .participants-row { flex-wrap:wrap; }
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
</div>

<div class="tab-content" id="tab-results-input">
<div class="card">
<h2>&#9989; Echte Resultaten Invullen</h2>
<div class="step-indicator">
<div class="step active" id="admin-step-ind-1">1. Groepsfase</div>
<div class="step" id="admin-step-ind-2">2. Knock-out</div>
</div>
<div id="admin-step-1">
<h3>Eindstand Groepsfase</h3>
<div class="group-grid" id="admin-groups-container"></div>
<div class="btn-group"><button class="btn btn-primary" id="admin-btn-next-1">Volgende &#8594;</button></div>
</div>
<div id="admin-step-2" class="hidden">
<h3>Knock-out Resultaten</h3>
<div id="admin-knockout-container"></div>
<div class="btn-group">
<button class="btn btn-secondary" id="admin-btn-back-2">&#8592; Terug</button>
<button class="btn btn-success" id="admin-btn-save">&#128190; Opslaan</button>
</div>
</div>
<div class="status-msg hidden" id="admin-save-status"></div>
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
var R32_STRUCTURE = %R32_STRUCTURE_JSON%;
var INLEG = %INLEG%;
var adminGroupResults = {};
var adminThirdAssignments = {};
var adminKnockoutSelections = {};
var adminCurrentStep = 1;
var allParticipants = [];

document.querySelectorAll('.tab').forEach(function(t) {
    t.addEventListener('click', function() {
        document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});
        document.querySelectorAll('.tab-content').forEach(function(x){x.classList.remove('active');});
        t.classList.add('active');
        document.getElementById('tab-' + t.getAttribute('data-tab')).classList.add('active');
    });
});

function adminGoToStep(step) {
    if (step === 2) {
        adminGroupResults = adminGetGroupResults();
        adminBuildKnockout();
    }
    document.getElementById('admin-step-' + adminCurrentStep).classList.add('hidden');
    document.getElementById('admin-step-' + step).classList.remove('hidden');
    for (var i = 1; i <= 2; i++) {
        var ind = document.getElementById('admin-step-ind-' + i);
        ind.classList.remove('active','done');
        if (i < step) ind.classList.add('done');
        if (i === step) ind.classList.add('active');
    }
    adminCurrentStep = step;
}

function adminBuildGroups() {
    var c = document.getElementById('admin-groups-container');
    c.innerHTML = '';
    var groups = Object.keys(GROEPEN);
    for (var g = 0; g < groups.length; g++) {
        var group = groups[g], teams = GROEPEN[group];
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

function adminResolveTeam(slot) {
    if (slot.type === 'winner') return adminGroupResults[slot.group][0];
    if (slot.type === 'runnerup') return adminGroupResults[slot.group][1];
    return 'TBD';
}

function adminBuildKnockout() {
    var c = document.getElementById('admin-knockout-container');
    c.innerHTML = '';
    adminKnockoutSelections = { r32: {}, r16: {}, qf: {}, sf: {}, final_round: {} };
    adminThirdAssignments = {};
    adminBuildThirdAssignment(c);
}

function adminBuildThirdAssignment(container) {
    var div = document.createElement('div');
    div.className = 'knockout-round';
    div.id = 'admin-third-assignment';
    var html = '<h3>Wijs Beste Derdes toe aan Wedstrijden</h3>';
    html += '<p class="drag-hint">Voor elke wedstrijd: kies welk #3 team daadwerkelijk speelt.</p>';
    for (var i = 0; i < R32_STRUCTURE.length; i++) {
        var match = R32_STRUCTURE[i];
        if (match.slot2.type !== 'third') continue;
        var t1 = adminResolveTeam(match.slot1);
        html += '<div class="match-card" style="flex-direction:column;align-items:stretch;">';
        html += '<div style="text-align:center;margin-bottom:8px;"><strong>' + t1 + '</strong> vs <em>3e uit groep ' + match.slot2.allowed.join('/') + '</em></div>';
        html += '<select class="third-assign-select admin-tas" data-match="' + i + '">';
        html += '<option value="">-- Kies --</option>';
        for (var j = 0; j < match.slot2.allowed.length; j++) {
            var grp = match.slot2.allowed[j];
            if (adminGroupResults[grp] && adminGroupResults[grp][2]) {
                html += '<option value="' + grp + '">' + adminGroupResults[grp][2] + ' (Groep ' + grp + ')</option>';
            }
        }
        html += '</select></div>';
    }
    html += '<div class="btn-group"><button class="btn btn-primary" id="admin-btn-confirm-thirds">Bevestig &#8594;</button></div>';
    div.innerHTML = html;
    container.appendChild(div);
    var sels = div.querySelectorAll('.admin-tas');
    for (var s = 0; s < sels.length; s++) sels[s].addEventListener('change', adminUpdateAssignOptions);
    document.getElementById('admin-btn-confirm-thirds').addEventListener('click', adminConfirmThirdAssignments);
}

function adminUpdateAssignOptions() {
    var sels = document.querySelectorAll('.admin-tas');
    var used = [];
    for (var i = 0; i < sels.length; i++) if (sels[i].value) used.push(sels[i].value);
    for (var i = 0; i < sels.length; i++) {
        var cur = sels[i].value;
        var opts = sels[i].querySelectorAll('option');
        for (var j = 0; j < opts.length; j++) {
            if (opts[j].value === '') continue;
            opts[j].disabled = (opts[j].value !== cur && used.indexOf(opts[j].value) >= 0);
        }
    }
}

function adminConfirmThirdAssignments() {
    var sels = document.querySelectorAll('.admin-tas');
    adminThirdAssignments = {};
    for (var i = 0; i < sels.length; i++) {
        if (!sels[i].value) { alert('Wijs alle wedstrijden toe!'); return; }
        adminThirdAssignments[parseInt(sels[i].getAttribute('data-match'))] = sels[i].value;
    }
    document.getElementById('admin-third-assignment').remove();
    adminBuildR32();
}

function adminBuildR32() {
    var c = document.getElementById('admin-knockout-container');
    var matches = [];
    for (var i = 0; i < R32_STRUCTURE.length; i++) {
        var m = R32_STRUCTURE[i];
        var t1 = adminResolveTeam(m.slot1);
        var t2;
        if (m.slot2.type === 'third') {
            var ag = adminThirdAssignments[i];
            t2 = ag ? adminGroupResults[ag][2] : 'TBD';
        } else { t2 = adminResolveTeam(m.slot2); }
        matches.push({ team1: t1, team2: t2 });
    }
    adminRenderRound(c, '1/16 Finales', matches, 'r32');
}

function adminRenderRound(container, title, matches, rk) {
    var div = document.createElement('div');
    div.className = 'knockout-round';
    div.id = 'admin-round-' + rk;
    var html = '<h3>' + title + '</h3>';
    for (var i = 0; i < matches.length; i++) {
        var m = matches[i];
        html += '<div class="match-card">';
        html += '<div class="match-team" id="admin-' + rk + '-' + i + '-1" data-round="' + rk + '" data-match="' + i + '" data-team="' + esc(m.team1) + '">' + m.team1 + '</div>';
        html += '<span class="match-vs">VS</span>';
        html += '<div class="match-team" id="admin-' + rk + '-' + i + '-2" data-round="' + rk + '" data-match="' + i + '" data-team="' + esc(m.team2) + '">' + m.team2 + '</div>';
        html += '</div>';
    }
    div.innerHTML = html;
    container.appendChild(div);
    var tds = div.querySelectorAll('.match-team');
    for (var t = 0; t < tds.length; t++) tds[t].addEventListener('click', adminMatchClick);
}

function esc(s) { return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escAttr(s) { return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

function adminMatchClick(e) {
    var el = e.currentTarget;
    var rk = el.getAttribute('data-round');
    var mi = parseInt(el.getAttribute('data-match'));
    var tn = el.getAttribute('data-team');
    document.getElementById('admin-' + rk + '-' + mi + '-1').classList.remove('selected');
    document.getElementById('admin-' + rk + '-' + mi + '-2').classList.remove('selected');
    el.classList.add('selected');
    adminKnockoutSelections[rk][mi] = tn;
    adminBuildNext(rk);
}

function adminBuildNext(rk) {
    var c = document.getElementById('admin-knockout-container');
    var counts = { r32: 16, r16: 8, qf: 4, sf: 2, final_round: 1 };
    var nexts = { r32: 'r16', r16: 'qf', qf: 'sf', sf: 'final_round' };
    var names = { r32: '1/8 Finales', r16: 'Kwartfinales', qf: 'Halve Finales', sf: '&#127942; FINALE' };
    if (Object.keys(adminKnockoutSelections[rk]).length < counts[rk]) return;
    var nk = nexts[rk]; if (!nk) return;
    var order = ['r16','qf','sf','final_round'];
    for (var i = order.indexOf(nk); i < order.length; i++) {
        var ex = document.getElementById('admin-round-' + order[i]);
        if (ex) ex.remove();
        adminKnockoutSelections[order[i]] = {};
    }
    var w = [];
    for (var j = 0; j < counts[rk]; j++) w.push(adminKnockoutSelections[rk][j]);
    var nm = [];
    for (var k = 0; k < w.length; k += 2) nm.push({ team1: w[k], team2: w[k+1] });
    adminRenderRound(c, names[rk], nm, nk);
}

function adminSave() {
    if (!adminKnockoutSelections.final_round || adminKnockoutSelections.final_round[0] === undefined) {
        alert('Vul alle wedstrijden in!'); return;
    }
    var derdes = [];
    for (var k in adminThirdAssignments) {
        var grp = adminThirdAssignments[k];
        derdes.push({ groep: grp, team: adminGroupResults[grp][2] });
    }
    var data = {
        groepsfase: adminGetGroupResults(),
        beste_derdes: derdes,
        third_assignments: adminThirdAssignments,
        knockout: {
            ronde_van_32: adminKnockoutSelections.r32, ronde_van_16: adminKnockoutSelections.r16,
            kwartfinales: adminKnockoutSelections.qf, halve_finales: adminKnockoutSelections.sf,
            finale: adminKnockoutSelections.final_round[0]
        }
    };
    fetch('/api/admin/results', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data) })
    .then(function(r){return r.json();})
    .then(function(res) {
        var s = document.getElementById('admin-save-status');
        s.classList.remove('hidden');
        if (res.success) { s.className = 'status-msg success'; s.textContent = 'Opgeslagen!'; loadAdminLeaderboard(); }
        else { s.className = 'status-msg error'; s.textContent = 'Fout: ' + res.error; }
    });
}

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
            if (!confirm('Voorspelling van "' + name + '" verwijderen? Dit kan niet ongedaan worden!')) return;
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
        var h = '<table class="leaderboard"><thead><tr><th>#</th><th style="text-align:left;">Speler</th><th>Kampioen</th><th>Groep</th><th>R32</th><th>R16</th><th>KF</th><th>HF</th><th>Win</th><th>TOTAAL</th></tr></thead><tbody>';
        for (var i = 0; i < d.players.length; i++) {
            var p = d.players[i];
            h += '<tr><td>'+(i+1)+'</td><td class="name">'+p.naam+'</td><td>'+(p.kampioen||'?')+'</td>';
            h += '<td>'+p.points.groep_positie+'</td>';
            h += '<td>'+p.points.r32+'</td><td>'+p.points.r16+'</td><td>'+p.points.qf+'</td><td>'+p.points.sf+'</td>';
            h += '<td>'+p.points.winnaar+'</td>';
            h += '<td class="total">'+p.points.totaal+'</td></tr>';
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
            h += '<div class="info">Ingediend: ' + (p.datum || '?') + '</div></div>';
        }
        c.innerHTML = h;
    });
}

document.getElementById('admin-btn-next-1').addEventListener('click', function() { adminGoToStep(2); });
document.getElementById('admin-btn-back-2').addEventListener('click', function() { adminGoToStep(1); });
document.getElementById('admin-btn-save').addEventListener('click', adminSave);

adminBuildGroups();
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
def submit():
    try:
        data = request.get_json()
        naam = data.get('naam', '').strip()
        if not naam:
            return jsonify({"success": False, "error": "Naam is verplicht"})
        # Auto-set betaald op true (we vertrouwen iedereen)
        save_prediction(naam, data)
        set_paid_status(naam, True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    return jsonify(load_data())


@app.route('/api/public/results', methods=['GET'])
def public_results():
    return jsonify(load_results())


@app.route('/api/scoreboard', methods=['GET'])
def get_scoreboard():
    all_predictions = load_data()
    real_results = load_results()
    players = []
    for naam, pred in all_predictions.items():
        points = calculate_points(pred, real_results)
        kampioen = pred.get('knockout', {}).get('finale', '?')
        players.append({"naam": naam, "kampioen": kampioen, "points": points})
    players.sort(key=lambda x: x["points"]["totaal"], reverse=True)
    return jsonify({
        "players": players,
        "results_available": bool(real_results and real_results.get("groepsfase"))
    })


@app.route('/api/admin/payments', methods=['GET'])
@admin_required
def admin_payments():
    all_data = load_data()
    players = []
    for naam, pred in all_data.items():
        players.append({
            "naam": naam,
            "email": pred.get('email', ''),
            "relatie": pred.get('relatie', ''),
            "datum": pred.get('datum', '?'),
            "kampioen": pred.get('knockout', {}).get('finale', '?')
        })
    return jsonify({"players": players})


@app.route('/api/admin/delete', methods=['POST'])
def admin_delete():
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "Niet geautoriseerd"})
    try:
        data = request.get_json()
        naam = data.get('naam', '').strip()
        if not naam:
            return jsonify({"success": False, "error": "Naam is verplicht"})
        delete_prediction(naam)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/admin/results', methods=['GET', 'POST'])
def admin_results():
    if request.method == 'GET':
        return jsonify(load_results())
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "Niet geautoriseerd"})
    try:
        data = request.get_json()
        save_results(data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
