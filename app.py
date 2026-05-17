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
BEGUNSTIGDE = "AZ St Blasius WK Poule"  # Naam ontvanger op QR
INLEG = 10  # euro

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
# SEPA EPC QR-CODE GENERATIE (EPC069-12 standaard)
# ============================================================
def generate_epc_payload(name, iban, amount_eur, communication):
    """
    Genereer EPC QR payload volgens EPC069-12 (Version 002).
    Dit is de Europese standaard voor SEPA betaal-QR-codes.
    Wordt herkend door alle Belgische bankapps (KBC, Belfius, ING, BNP, Argenta, ...).
    """
    # Limieten volgens EPC standaard
    name = name[:70]
    communication = communication[:140]
    amount_str = "EUR{:.2f}".format(amount_eur)

    lines = [
        "BCD",                  # Service tag
        "002",                  # Version (002 = laatste)
        "1",                    # Character set (1 = UTF-8)
        "SCT",                  # Identification (SEPA Credit Transfer)
        "",                     # BIC (optioneel - leeg laten = bank zoekt zelf)
        name,                   # Begunstigde naam
        iban,                   # IBAN (zonder spaties)
        amount_str,             # Bedrag
        "",                     # Purpose code (optioneel)
        "",                     # Structured remittance (leeg)
        communication,          # Unstructured remittance (mededeling)
        ""                      # Beneficiary to originator info (optioneel)
    ]
    return "\n".join(lines)


def generate_qr_image_base64(payload):
    """Genereer een PNG QR-code en encode als base64 voor inline weergave."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
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
.name-input { width:100%; padding:14px 20px; font-size:1.1em; border:2px solid rgba(255,255,255,0.2); border-radius:10px; background:rgba(255,255,255,0.05); color:#fff; outline:none; margin-bottom:10px; }
.name-input:focus { border-color:#e94560; }
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

/* Payment / QR styles */
.payment-card { background:linear-gradient(135deg,rgba(255,215,0,0.12),rgba(233,69,96,0.08)); border:2px solid #ffd700; border-radius:16px; padding:24px; text-align:center; margin-bottom:20px; }
.payment-icon { font-size:3em; margin-bottom:8px; }
.payment-amount { font-size:2.5em; font-weight:bold; color:#ffd700; margin:8px 0; }
.qr-wrapper { background:#fff; padding:20px; border-radius:16px; display:inline-block; margin:16px 0; box-shadow:0 8px 24px rgba(0,0,0,0.3); }
.qr-wrapper img { display:block; max-width:280px; width:100%; height:auto; }
.qr-loading { background:rgba(255,255,255,0.1); padding:40px; border-radius:16px; min-height:280px; display:flex; align-items:center; justify-content:center; color:#aaa; }
.qr-instructions { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:12px; padding:16px; margin:16px 0; text-align:left; }
.qr-instructions h4 { color:#2ecc71; margin-bottom:10px; font-size:1em; }
.qr-instructions ol { margin-left:20px; color:#ccc; font-size:0.9em; line-height:1.7; }
.qr-instructions ol li strong { color:#fff; }
.payment-detail { background:rgba(0,0,0,0.3); border-radius:12px; padding:16px; margin:16px 0; text-align:left; }
.payment-detail-row { display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.08); flex-wrap:wrap; gap:6px; align-items:center; }
.payment-detail-row:last-child { border-bottom:none; }
.payment-detail-row .label { color:#aaa; font-size:0.9em; }
.payment-detail-row .value { color:#fff; font-weight:bold; font-family:'Courier New',monospace; }
.copy-btn { padding:5px 10px; font-size:0.8em; background:rgba(46,204,113,0.2); border:1px solid #2ecc71; color:#2ecc71; border-radius:6px; cursor:pointer; margin-left:6px; }
.copy-btn:hover { background:#2ecc71; color:#fff; }
.copy-btn.copied { background:#2ecc71; color:#fff; }
.manual-toggle { color:#aaa; cursor:pointer; text-decoration:underline; font-size:0.9em; margin-top:12px; display:inline-block; }
.manual-toggle:hover { color:#fff; }
.payment-warning { background:rgba(233,69,96,0.12); border:1px solid rgba(233,69,96,0.4); border-radius:10px; padding:12px; margin:16px 0; font-size:0.9em; }
.payment-checkbox-row { background:rgba(255,255,255,0.05); border:2px solid rgba(255,255,255,0.1); border-radius:10px; padding:14px; margin:20px 0; cursor:pointer; transition:all 0.2s; }
.payment-checkbox-row:hover { border-color:#2ecc71; background:rgba(46,204,113,0.05); }
.payment-checkbox-row.checked { border-color:#2ecc71; background:rgba(46,204,113,0.1); }
.payment-checkbox-row input[type=checkbox] { margin-right:10px; transform:scale(1.4); accent-color:#2ecc71; }
.payment-checkbox-row label { cursor:pointer; user-select:none; font-size:0.95em; }

@media (max-width:600px) { .match-card { flex-direction:column; } .match-team { width:100%; } .payment-amount { font-size:2em; } .qr-wrapper img { max-width:240px; } }
</style></head><body>
<div class="container">
<h1>&#9917; AZ St Blasius - WK 2026</h1>
<p class="subtitle">Vul je voorspellingen in voor het WK 2026!</p>
<div class="nav-links"><a href="/scoreboard">&#127942; Scoreboard</a><a href="/admin">&#128272; Admin</a></div>

<div class="step-indicator">
<div class="step active" id="step-ind-1">1. Naam</div>
<div class="step" id="step-ind-2">2. Groepsfase</div>
<div class="step" id="step-ind-3">3. Knock-out</div>
<div class="step" id="step-ind-4">4. Betaling</div>
<div class="step" id="step-ind-5">5. Klaar!</div>
</div>

<div id="step-1" class="card">
<h2>&#128100; Wie ben je?</h2>
<input type="text" class="name-input" id="player-name" placeholder="Vul je naam in..." autocomplete="off">
<p class="error-msg" id="name-error">&#9888; Vul je naam in!</p>
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
<h2 style="color:#ffd700;border:none;">Scan om te betalen</h2>
<p style="color:#ddd;margin-bottom:8px;">Inleg poule</p>
<div class="payment-amount">&euro;%INLEG%</div>

<div id="qr-container" class="qr-loading">
&#9203; QR-code wordt gegenereerd...
</div>

<div class="qr-instructions">
<h4>&#128241; Hoe betalen met QR-code?</h4>
<ol>
<li>Open je <strong>bankapp</strong> (KBC, Belfius, ING, BNP, Argenta, Belfius, ...)</li>
<li>Kies <strong>"Overschrijven"</strong> &rarr; <strong>"QR-code scannen"</strong></li>
<li>Scan de QR-code hierboven &rarr; alles wordt automatisch ingevuld</li>
<li>Bevestig de betaling met je app</li>
</ol>
</div>

<a class="manual-toggle" id="manual-toggle">&#9881; Of: handmatig overschrijven</a>

<div class="payment-detail hidden" id="manual-details">
<div class="payment-detail-row">
<span class="label">IBAN</span>
<span class="value" id="iban-text">%IBAN%<button class="copy-btn" data-copy="iban">&#128203;</button></span>
</div>
<div class="payment-detail-row">
<span class="label">Bedrag</span>
<span class="value">&euro; %INLEG%,00</span>
</div>
<div class="payment-detail-row">
<span class="label">Mededeling</span>
<span class="value"><span id="mededeling-text">WK2026 - <span id="mededeling-naam">jouw naam</span></span><button class="copy-btn" data-copy="mededeling">&#128203;</button></span>
</div>
</div>
</div>

<div class="payment-warning">
&#9888; <strong>Belangrijk:</strong> De QR-code bevat <strong>automatisch jouw naam</strong> in de mededeling, zodat we de betaling kunnen koppelen aan je voorspelling.
</div>

<div class="payment-checkbox-row" id="payment-confirm-row">
<label style="display:flex;align-items:center;">
<input type="checkbox" id="payment-confirm">
<span>Ik heb de betaling uitgevoerd (of doe dit zo direct)</span>
</label>
</div>

<p style="text-align:center;color:#aaa;font-size:0.85em;margin-top:12px;">
&#8505; Je voorspelling wordt opgeslagen, maar verschijnt pas op het scoreboard nadat de betaling bevestigd is door de admin.
</p>

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
<p style="color:#aaa;margin:20px 0;">&#8505; Je voorspelling verschijnt op het scoreboard zodra de admin je betaling bevestigt.</p>
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

function goToStep(step) {
    if (step === 2) {
        var nameVal = document.getElementById('player-name').value.trim();
        if (!nameVal) { document.getElementById('name-error').classList.add('show'); return; }
    }
    if (step === 3) {
        groupPredictions = getGroupResults();
        buildKnockout();
    }
    if (step === 4) {
        if (!knockoutSelections.final_round || knockoutSelections.final_round[0] === undefined) {
            alert('Vul eerst alle knock-out wedstrijden in!'); return;
        }
        var name = document.getElementById('player-name').value.trim();
        document.getElementById('mededeling-naam').textContent = name;
        loadQRCode(name);
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

function loadQRCode(name) {
    var container = document.getElementById('qr-container');
    container.className = 'qr-loading';
    container.innerHTML = '&#9203; QR-code wordt gegenereerd...';
    fetch('/api/qr?naam=' + encodeURIComponent(name))
    .then(function(r){ return r.json(); })
    .then(function(d) {
        if (d.success) {
            container.className = 'qr-wrapper';
            container.innerHTML = '<img src="data:image/png;base64,' + d.qr + '" alt="SEPA QR-code">';
        } else {
            container.className = 'qr-loading';
            container.innerHTML = 'Fout bij genereren QR-code. Gebruik handmatige gegevens hieronder.';
        }
    })
    .catch(function() {
        container.className = 'qr-loading';
        container.innerHTML = 'Fout bij genereren QR-code. Gebruik handmatige gegevens hieronder.';
    });
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
    var teamDivs = div.querySelect
