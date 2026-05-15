#!/usr/bin/env python3
"""
WK 2026 Voorspellingstool - Web App (48 teams, 12 groepen)
"""

from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
import json
import os
import sqlite3
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'wk2026-geheim-sleutel-verander-dit!')

DB_FILE = os.environ.get('DB_PATH', 'wk2026.db')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin2026')

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
    "groep_juiste_positie": 1, "groep_juiste_winnaar": 2, "groep_juiste_tweede": 1,
    "beste_derde_juist": 2, "r32_juist": 3, "r16_juist": 5, "qf_juist": 7,
    "sf_juist": 10, "finalist_juist": 12, "winnaar_juist": 15,
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
# DATABASE
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS voorspellingen (naam TEXT PRIMARY KEY, data TEXT NOT NULL, datum TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS echte_resultaten (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL, datum TEXT NOT NULL)")
    conn.commit()
    conn.close()

def load_data():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT naam, data FROM voorspellingen")
    rows = c.fetchall()
    conn.close()
    return {naam: json.loads(data) for naam, data in rows}

def save_prediction(naam, data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    datum = datetime.now().strftime("%Y-%m-%d %H:%M")
    data['datum'] = datum
    c.execute("INSERT OR REPLACE INTO voorspellingen (naam, data, datum) VALUES (?, ?, ?)",
              (naam, json.dumps(data, ensure_ascii=False), datum))
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
    points = {"groep_positie":0,"groep_winnaar":0,"groep_tweede":0,"beste_derdes":0,
              "r32":0,"r16":0,"qf":0,"sf":0,"finalist":0,"winnaar":0,"totaal":0,"details":[]}
    if not real_results:
        return points

    real_groups = real_results.get("groepsfase", {})
    pred_groups = prediction.get("groepsfase", {})
    for group in pred_groups:
        if group not in real_groups: continue
        real_order = real_groups[group]
        pred_order = pred_groups[group]
        if len(real_order)>0 and len(pred_order)>0 and pred_order[0]==real_order[0]:
            points["groep_winnaar"] += PUNTEN["groep_juiste_winnaar"]
        if len(real_order)>1 and len(pred_order)>1 and pred_order[1]==real_order[1]:
            points["groep_tweede"] += PUNTEN["groep_juiste_tweede"]
        for i, team in enumerate(pred_order):
            if i < len(real_order) and real_order[i] == team:
                points["groep_positie"] += PUNTEN["groep_juiste_positie"]

    real_thirds = real_results.get("beste_derdes", [])
    pred_thirds = prediction.get("beste_derdes", [])
    if real_thirds and pred_thirds:
        rt = set(item.get("team","") if isinstance(item,dict) else str(item) for item in real_thirds)
        pt = set(item.get("team","") if isinstance(item,dict) else str(item) for item in pred_thirds)
        points["beste_derdes"] = len(rt & pt) * PUNTEN["beste_derde_juist"]

    real_ko = real_results.get("knockout", {})
    pred_ko = prediction.get("knockout", {})
    for key, pk, pp, _ in [("ronde_van_32","r32",PUNTEN["r32_juist"],""),
                            ("ronde_van_16","r16",PUNTEN["r16_juist"],""),
                            ("kwartfinales","qf",PUNTEN["qf_juist"],""),
                            ("halve_finales","sf",PUNTEN["sf_juist"],"")]:
        rr = real_ko.get(key, {}); pr = pred_ko.get(key, {})
        if rr and pr:
            rw = set(rr.values()) if isinstance(rr,dict) else set()
            pw = set(pr.values()) if isinstance(pr,dict) else set()
            points[pk] = len(rw & pw) * pp

    if real_ko.get("finale") and pred_ko.get("finale") == real_ko.get("finale"):
        points["winnaar"] = PUNTEN["winnaar_juist"]

    rsf = real_ko.get("halve_finales", {})
    psf = pred_ko.get("halve_finales", {})
    if rsf and psf:
        rf = set(rsf.values()) if isinstance(rsf,dict) else set()
        pf = set(psf.values()) if isinstance(psf,dict) else set()
        points["finalist"] = len(rf & pf) * PUNTEN["finalist_juist"]

    points["totaal"] = sum(points[k] for k in ["groep_positie","groep_winnaar","groep_tweede",
                          "beste_derdes","r32","r16","qf","sf","finalist","winnaar"])
    return points


# ============================================================
# SHARED JS for knockout (used in both player + admin templates)
# ============================================================
# We will inject one shared script. Player uses id prefix '', admin uses 'admin-'.

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
.third-place-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; margin:16px 0; }
.third-place-option { padding:10px; border-radius:8px; text-align:center; background:rgba(255,255,255,0.05); border:2px solid rgba(255,255,255,0.1); cursor:pointer; }
.third-place-option:hover { background:rgba(255,255,255,0.1); }
.third-place-option.selected { background:rgba(46,204,113,0.2); border-color:#2ecc71; }
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
.counter { color:#f0a500; font-weight:bold; margin:8px 0; }
.error-msg { color:#e94560; font-size:0.9em; margin-top:8px; display:none; }
.error-msg.show { display:block; }
.third-assign-select { width:100%; padding:10px; border-radius:8px; background:rgba(0,0,0,0.4); color:#fff; border:2px solid rgba(255,255,255,0.2); font-size:1em; }
.third-assign-select option { background:#1a1a2e; color:#fff; }
@media (max-width:600px) { .match-card { flex-direction:column; } .match-team { width:100%; } }
</style></head><body>
<div class="container">
<h1>&#9917; AZ St Blasius - WK 2026</h1>
<p class="subtitle">Vul je voorspellingen in voor het WK 2026!</p>
<div class="nav-links"><a href="/scoreboard">&#127942; Scoreboard</a><a href="/admin">&#128272; Admin</a></div>

<div class="step-indicator">
<div class="step active" id="step-ind-1">1. Naam</div>
<div class="step" id="step-ind-2">2. Groepsfase</div>
<div class="step" id="step-ind-3">3. Beste #3</div>
<div class="step" id="step-ind-4">4. Knock-out</div>
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
<h2>&#127941; Beste Nummers 3</h2>
<p class="drag-hint">Selecteer welke 8 nummers 3 doorgaan</p>
<p class="counter" id="third-counter">Geselecteerd: 0 / 8</p>
<div class="third-place-grid" id="third-place-container"></div>
<div class="btn-group">
<button class="btn btn-secondary" id="btn-back-3">&#8592; Terug</button>
<button class="btn btn-primary" id="btn-to-knockout" disabled>Volgende &#8594;</button>
</div>
</div>

<div id="step-4" class="card hidden">
<h2>&#127942; Knock-outfase</h2>
<div id="knockout-container"></div>
<div class="btn-group">
<button class="btn btn-secondary" id="btn-back-4">&#8592; Terug</button>
<button class="btn btn-primary" id="btn-submit">&#9989; Indienen</button>
</div>
</div>

<div id="step-5" class="card hidden">
<div class="success-screen">
<div class="trophy">&#127942;</div>
<h2>Voorspelling Ingediend!</h2>
<p>Bedankt <strong id="confirm-name"></strong>!</p>
<p class="champion-name">Jouw kampioen: <span id="confirm-champion"></span></p>
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
var selectedThirds = [];
var thirdPlaceAssignments = {};
var knockoutSelections = {};

function goToStep(step) {
    if (step === 2) {
        var nameVal = document.getElementById('player-name').value.trim();
        if (!nameVal) { document.getElementById('name-error').classList.add('show'); return; }
    }
    if (step === 3) { groupPredictions = getGroupResults(); buildThirdPlaces(); }
    if (step === 4) {
        if (selectedThirds.length !== 8) { alert('Selecteer precies 8 nummers 3!'); return; }
        buildKnockout();
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
    list.addEventListener('dragend', function(e) { if (dragged) { dragged.classList.remove('dragging'); dragged = null; updatePositionBadges(list); } });
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

function buildThirdPlaces() {
    var container = document.getElementById('third-place-container');
    container.innerHTML = '';
    selectedThirds = [];
    updateThirdCounter();
    var groups = Object.keys(groupPredictions);
    for (var g = 0; g < groups.length; g++) {
        var group = groups[g], teams = groupPredictions[group];
        if (!teams || teams.length < 3) continue;
        var div = document.createElement('div');
        div.className = 'third-place-option';
        div.id = 'third-' + group;
        div.textContent = teams[2] + ' (Groep ' + group + ')';
        (function(grp) { div.addEventListener('click', function() { toggleThird(grp); }); })(group);
        container.appendChild(div);
    }
}

function toggleThird(group) {
    var div = document.getElementById('third-' + group);
    var idx = selectedThirds.indexOf(group);
    if (idx >= 0) { selectedThirds.splice(idx, 1); div.classList.remove('selected'); }
    else {
        if (selectedThirds.length >= 8) { alert('Max 8!'); return; }
        selectedThirds.push(group); div.classList.add('selected');
    }
    updateThirdCounter();
}

function updateThirdCounter() {
    document.getElementById('third-counter').textContent = 'Geselecteerd: ' + selectedThirds.length + ' / 8';
    document.getElementById('btn-to-knockout').disabled = (selectedThirds.length !== 8);
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
    html += '<p class="drag-hint">Voor elke wedstrijd: kies welk #3 team speelt. Elk team kan maar 1x.</p>';
    for (var i = 0; i < R32_STRUCTURE.length; i++) {
        var match = R32_STRUCTURE[i];
        if (match.slot2.type !== 'third') continue;
        var slot1Team = resolveTeam(match.slot1);
        html += '<div class="match-card" style="flex-direction:column;align-items:stretch;">';
        html += '<div style="text-align:center;margin-bottom:8px;"><strong>' + slot1Team + '</strong> vs <em>3e uit groep ' + match.slot2.allowed.join('/') + '</em></div>';
        html += '<select class="third-assign-select" data-match="' + i + '">';
        html += '<option value="">-- Kies een team --</option>';
        for (var j = 0; j < selectedThirds.length; j++) {
            var grp = selectedThirds[j];
            if (match.slot2.allowed.indexOf(grp) >= 0) {
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

function submitPrediction() {
    var name = document.getElementById('player-name').value.trim();
    if (!knockoutSelections.final_round || knockoutSelections.final_round[0] === undefined) {
        alert('Vul alle wedstrijden in!'); return;
    }
    var data = {
        naam: name,
        groepsfase: getGroupResults(),
        beste_derdes: selectedThirds.map(function(g) { return { groep: g, team: groupPredictions[g][2] }; }),
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
document.getElementById('btn-to-knockout').addEventListener('click', function() { goToStep(4); });
document.getElementById('btn-back-4').addEventListener('click', function() { goToStep(3); });
document.getElementById('btn-submit').addEventListener('click', submitPrediction);
document.getElementById('player-name').addEventListener('keypress', function(e) { if (e.key === 'Enter') goToStep(2); });
document.getElementById('player-name').addEventListener('input', function() { document.getElementById('name-error').classList.remove('show'); });

buildGroups();
})();
</script>
</body></html>
"""

# ============================================================
# SCOREBOARD
# ============================================================
SCOREBOARD_TEMPLATE = """<!DOCTYPE html>
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
.card { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:24px; margin-bottom:20px; }
.card h2 { color:#e94560; margin-bottom:16px; }
.leaderboard { width:100%; border-collapse:collapse; }
.leaderboard th { background:rgba(233,69,96,0.2); padding:12px 10px; text-align:center; font-size:0.8em; }
.leaderboard td { padding:12px 10px; border-bottom:1px solid rgba(255,255,255,0.05); text-align:center; }
.leaderboard .name { text-align:left; font-weight:bold; }
.leaderboard .total { font-weight:bold; font-size:1.3em; color:#2ecc71; }
.rank-1{color:#ffd700;} .rank-2{color:#c0c0c0;} .rank-3{color:#cd7f32;}
@media (max-width:700px) { .hide-mobile { display:none; } }
</style></head><body>
<div class="container">
<h1>&#127942; WK 2026 Scoreboard</h1>
<div class="nav-links"><a href="/">Voorspelling</a><a href="/admin">Admin</a></div>
<div class="card"><h2>Rangschikking</h2><div id="scoreboard-content">Laden...</div></div>
</div>
<script>
fetch('/api/scoreboard').then(function(r){return r.json();}).then(function(d){
var c = document.getElementById('scoreboard-content');
if (!d.players || !d.players.length) { c.innerHTML = '<p>Nog geen voorspellingen.</p>'; return; }
var h = '<table class="leaderboard"><thead><tr><th>#</th><th style="text-align:left;">Speler</th><th>Kampioen</th><th class="hide-mobile">R32</th><th class="hide-mobile">R16</th><th class="hide-mobile">KF</th><th class="hide-mobile">HF</th><th>TOTAAL</th></tr></thead><tbody>';
for (var i=0;i<d.players.length;i++) {
    var p = d.players[i];
    var rc = i===0?'rank-1':i===1?'rank-2':i===2?'rank-3':'';
    h += '<tr><td class="'+rc+'">'+(i+1)+'</td><td class="name">'+p.naam+'</td><td>'+(p.kampioen||'?')+'</td>';
    h += '<td class="hide-mobile">'+p.points.r32+'</td><td class="hide-mobile">'+p.points.r16+'</td>';
    h += '<td class="hide-mobile">'+p.points.qf+'</td><td class="hide-mobile">'+p.points.sf+'</td>';
    h += '<td class="total">'+p.points.totaal+'</td></tr>';
}
h += '</tbody></table>';
c.innerHTML = h;
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
# ADMIN DASHBOARD - now uses same R32_STRUCTURE flow
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
.third-place-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; margin:16px 0; }
.third-place-option { padding:10px; border-radius:8px; text-align:center; background:rgba(255,255,255,0.05); border:2px solid rgba(255,255,255,0.1); cursor:pointer; }
.third-place-option.selected { background:rgba(46,204,113,0.2); border-color:#2ecc71; }
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
.btn:disabled { opacity:0.5; cursor:not-allowed; }
.btn-group { display:flex; gap:12px; justify-content:center; margin-top:24px; flex-wrap:wrap; }
.hidden { display:none; }
.drag-hint { color:#888; font-size:0.85em; margin-bottom:12px; font-style:italic; }
.counter { color:#f0a500; font-weight:bold; margin:8px 0; }
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
@media (max-width:600px) { .match-card { flex-direction:column; } }
</style></head><body>
<div class="container">
<h1>&#128272; Admin Dashboard</h1>
<div class="nav-links"><a href="/">Home</a><a href="/scoreboard">Scoreboard</a><a href="/admin/logout">Uitloggen</a></div>

<div class="tabs">
<div class="tab active" data-tab="results-input">Resultaten Invullen</div>
<div class="tab" data-tab="leaderboard">Rangschikking</div>
<div class="tab" data-tab="all-predictions">Voorspellingen</div>
</div>

<div class="tab-content active" id="tab-results-input">
<div class="card">
<h2>&#9989; Echte Resultaten Invullen</h2>
<div class="step-indicator">
<div class="step active" id="admin-step-ind-1">1. Groepsfase</div>
<div class="step" id="admin-step-ind-2">2. Beste #3</div>
<div class="step" id="admin-step-ind-3">3. Knock-out</div>
</div>
<div id="admin-step-1">
<h3>Eindstand Groepsfase</h3>
<div class="group-grid" id="admin-groups-container"></div>
<div class="btn-group"><button class="btn btn-primary" id="admin-btn-next-1">Volgende &#8594;</button></div>
</div>
<div id="admin-step-2" class="hidden">
<h3>Beste Nummers 3</h3>
<p class="counter" id="admin-third-counter">Geselecteerd: 0 / 8</p>
<div class="third-place-grid" id="admin-third-place-container"></div>
<div class="btn-group">
<button class="btn btn-secondary" id="admin-btn-back-2">&#8592; Terug</button>
<button class="btn btn-primary" id="admin-btn-next-2" disabled>Volgende &#8594;</button>
</div>
</div>
<div id="admin-step-3" class="hidden">
<h3>Knock-out Resultaten</h3>
<div id="admin-knockout-container"></div>
<div class="btn-group">
<button class="btn btn-secondary" id="admin-btn-back-3">&#8592; Terug</button>
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
var adminGroupResults = {};
var adminSelectedThirds = [];
var adminThirdAssignments = {};
var adminKnockoutSelections = {};
var adminCurrentStep = 1;

document.querySelectorAll('.tab').forEach(function(t) {
    t.addEventListener('click', function() {
        document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});
        document.querySelectorAll('.tab-content').forEach(function(x){x.classList.remove('active');});
        t.classList.add('active');
        document.getElementById('tab-' + t.getAttribute('data-tab')).classList.add('active');
    });
});

function adminGoToStep(step) {
    if (step === 2) { adminGroupResults = adminGetGroupResults(); adminBuildThirdPlaces(); }
    if (step === 3) {
        if (adminSelectedThirds.length !== 8) { alert('Selecteer 8 nummers 3!'); return; }
        adminBuildKnockout();
    }
    document.getElementById('admin-step-' + adminCurrentStep).classList.add('hidden');
    document.getElementById('admin-step-' + step).classList.remove('hidden');
    for (var i = 1; i <= 3; i++) {
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

function adminBuildThirdPlaces() {
    var c = document.getElementById('admin-third-place-container');
    c.innerHTML = '';
    adminSelectedThirds = [];
    adminUpdateThirdCounter();
    var groups = Object.keys(adminGroupResults);
    for (var g = 0; g < groups.length; g++) {
        var group = groups[g], teams = adminGroupResults[group];
        if (!teams || teams.length < 3) continue;
        var div = document.createElement('div');
        div.className = 'third-place-option';
        div.id = 'admin-third-' + group;
        div.textContent = teams[2] + ' (Groep ' + group + ')';
        (function(grp) { div.addEventListener('click', function() { adminToggleThird(grp); }); })(group);
        c.appendChild(div);
    }
}

function adminToggleThird(group) {
    var div = document.getElementById('admin-third-' + group);
    var idx = adminSelectedThirds.indexOf(group);
    if (idx >= 0) { adminSelectedThirds.splice(idx, 1); div.classList.remove('selected'); }
    else {
        if (adminSelectedThirds.length >= 8) { alert('Max 8!'); return; }
        adminSelectedThirds.push(group); div.classList.add('selected');
    }
    adminUpdateThirdCounter();
}

function adminUpdateThirdCounter() {
    document.getElementById('admin-third-counter').textContent = 'Geselecteerd: ' + adminSelectedThirds.length + ' / 8';
    document.getElementById('admin-btn-next-2').disabled = (adminSelectedThirds.length !== 8);
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
        for (var j = 0; j < adminSelectedThirds.length; j++) {
            var grp = adminSelectedThirds[j];
            if (match.slot2.allowed.indexOf(grp) >= 0) {
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
    var data = {
        groepsfase: adminGetGroupResults(),
        beste_derdes: adminSelectedThirds.map(function(g) { return { groep: g, team: adminGroupResults[g][2] }; }),
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

function loadAdminLeaderboard() {
    fetch('/api/scoreboard').then(function(r){return r.json();}).then(function(d) {
        var c = document.getElementById('admin-leaderboard-container');
        if (!d.players || !d.players.length) { c.innerHTML = '<p>Nog geen voorspellingen.</p>'; return; }
        var h = '<table class="leaderboard"><thead><tr><th>#</th><th style="text-align:left;">Speler</th><th>Kampioen</th><th>R32</th><th>R16</th><th>KF</th><th>HF</th><th>TOTAAL</th></tr></thead><tbody>';
        for (var i = 0; i < d.players.length; i++) {
            var p = d.players[i];
            h += '<tr><td>'+(i+1)+'</td><td class="name">'+p.naam+'</td><td>'+(p.kampioen||'?')+'</td>';
            h += '<td>'+p.points.r32+'</td><td>'+p.points.r16+'</td><td>'+p.points.qf+'</td><td>'+p.points.sf+'</td>';
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
            h += '<div class="info">Kampioen: <strong style="color:#ffd700;">' + (p.knockout ? p.knockout.finale : '?') + '</strong></div>';
            h += '<div class="info">Ingediend: ' + (p.datum || '?') + '</div></div>';
        }
        c.innerHTML = h;
    });
}

document.getElementById('admin-btn-next-1').addEventListener('click', function() { adminGoToStep(2); });
document.getElementById('admin-btn-back-2').addEventListener('click', function() { adminGoToStep(1); });
document.getElementById('admin-btn-next-2').addEventListener('click', function() { adminGoToStep(3); });
document.getElementById('admin-btn-back-3').addEventListener('click', function() { adminGoToStep(2); });
document.getElementById('admin-btn-save').addEventListener('click', adminSave);

adminBuildGroups();
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
    return html


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))


@app.route('/api/submit', methods=['POST'])
def submit():
    try:
        data = request.get_json()
        naam = data.get('naam', '').strip()
        if not naam:
            return jsonify({"success": False, "error": "Naam is verplicht"})
        save_prediction(naam, data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    return jsonify(load_data())


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
