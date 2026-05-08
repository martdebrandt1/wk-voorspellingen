#!/usr/bin/env python3
"""
WK 2026 Voorspellingstool - Web App (48 teams, 12 groepen)
Met puntensysteem, publiek scoreboard, en admin resultaten-invoer via dezelfde UI
"""

from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
import json
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'wk2026-geheim-sleutel-verander-dit!')

DATA_FILE = "voorspellingen.json"
RESULTS_FILE = "echte_resultaten.json"
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin2026')

# WK 2026 Groepen
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

# Puntensysteem
PUNTEN = {
    "groep_juiste_positie": 1,
    "groep_juiste_winnaar": 2,
    "groep_juiste_tweede": 1,
    "beste_derde_juist": 2,
    "r32_juist": 3,
    "r16_juist": 5,
    "qf_juist": 7,
    "sf_juist": 10,
    "finalist_juist": 12,
    "winnaar_juist": 15,
}


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_results(data):
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


def calculate_points(prediction, real_results):
    """Bereken punten voor een speler op basis van echte resultaten"""
    points = {
        "groep_positie": 0,
        "groep_winnaar": 0,
        "groep_tweede": 0,
        "beste_derdes": 0,
        "r32": 0,
        "r16": 0,
        "qf": 0,
        "sf": 0,
        "finalist": 0,
        "winnaar": 0,
        "totaal": 0,
        "details": []
    }

    if not real_results:
        return points

    # Groepsfase punten
    real_groups = real_results.get("groepsfase", {})
    pred_groups = prediction.get("groepsfase", {})

    for group in pred_groups:
        if group not in real_groups:
            continue
        real_order = real_groups[group]
        pred_order = pred_groups[group]

        if len(real_order) > 0 and len(pred_order) > 0 and pred_order[0] == real_order[0]:
            points["groep_winnaar"] += PUNTEN["groep_juiste_winnaar"]
            points["details"].append(f"Groep {group}: juiste winnaar ({pred_order[0]}) +{PUNTEN['groep_juiste_winnaar']}pt")

        if len(real_order) > 1 and len(pred_order) > 1 and pred_order[1] == real_order[1]:
            points["groep_tweede"] += PUNTEN["groep_juiste_tweede"]
            points["details"].append(f"Groep {group}: juiste 2e ({pred_order[1]}) +{PUNTEN['groep_juiste_tweede']}pt")

        for i, team in enumerate(pred_order):
            if i < len(real_order) and real_order[i] == team:
                points["groep_positie"] += PUNTEN["groep_juiste_positie"]

    # Beste derdes
    real_thirds = real_results.get("beste_derdes", [])
    pred_thirds = prediction.get("beste_derdes", [])
    if real_thirds and pred_thirds:
        real_third_teams = set()
        pred_third_teams = set()
        for item in real_thirds:
            if isinstance(item, dict):
                real_third_teams.add(item.get("team", ""))
            else:
                real_third_teams.add(str(item))
        for item in pred_thirds:
            if isinstance(item, dict):
                pred_third_teams.add(item.get("team", ""))
            else:
                pred_third_teams.add(str(item))
        correct_thirds = len(real_third_teams & pred_third_teams)
        points["beste_derdes"] = correct_thirds * PUNTEN["beste_derde_juist"]
        if correct_thirds > 0:
            points["details"].append(f"Beste derdes: {correct_thirds} juist +{points['beste_derdes']}pt")

    # Knockout punten
    real_knockout = real_results.get("knockout", {})
    pred_knockout = prediction.get("knockout", {})

    knockout_mapping = [
        ("ronde_van_32", "r32", PUNTEN["r32_juist"], "1/16e finale"),
        ("ronde_van_16", "r16", PUNTEN["r16_juist"], "1/8e finale"),
        ("kwartfinales", "qf", PUNTEN["qf_juist"], "Kwartfinale"),
        ("halve_finales", "sf", PUNTEN["sf_juist"], "Halve finale"),
    ]

    for key, points_key, pts_per, label in knockout_mapping:
        real_round = real_knockout.get(key, {})
        pred_round = pred_knockout.get(key, {})
        if real_round and pred_round:
            real_winners = set(real_round.values()) if isinstance(real_round, dict) else set()
            pred_winners = set(pred_round.values()) if isinstance(pred_round, dict) else set()
            correct = len(real_winners & pred_winners)
            points[points_key] = correct * pts_per
            if correct > 0:
                points["details"].append(f"{label}: {correct} juist +{points[points_key]}pt")

    # Finale
    real_finale = real_knockout.get("finale", "")
    pred_finale = pred_knockout.get("finale", "")
    if real_finale and pred_finale:
        if pred_finale == real_finale:
            points["winnaar"] = PUNTEN["winnaar_juist"]
            points["details"].append(f"Juiste kampioen! ({pred_finale}) +{PUNTEN['winnaar_juist']}pt")

    # Finalisten
    real_sf = real_knockout.get("halve_finales", {})
    pred_sf = pred_knockout.get("halve_finales", {})
    if real_sf and pred_sf:
        real_finalists = set(real_sf.values()) if isinstance(real_sf, dict) else set()
        pred_finalists = set(pred_sf.values()) if isinstance(pred_sf, dict) else set()
        correct_finalists = len(real_finalists & pred_finalists)
        points["finalist"] = correct_finalists * PUNTEN["finalist_juist"]
        if correct_finalists > 0:
            points["details"].append(f"Juiste finalisten: {correct_finalists} +{points['finalist']}pt")

    points["totaal"] = (
        points["groep_positie"] + points["groep_winnaar"] + points["groep_tweede"] +
        points["beste_derdes"] + points["r32"] + points["r16"] +
        points["qf"] + points["sf"] + points["finalist"] + points["winnaar"]
    )

    return points


# ============================================================
# MAIN PAGE - Voorspelling invullen
# ============================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WK 2026 Voorspellingstool</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh; color: #fff; padding: 20px;
        }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { text-align: center; font-size: 2.5em; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.5); }
        .subtitle { text-align: center; color: #aaa; margin-bottom: 30px; font-size: 1.1em; }
        .nav-links { text-align: center; margin-bottom: 20px; }
        .nav-links a { color: #aaa; text-decoration: none; margin: 0 10px; padding: 8px 16px; border-radius: 8px; background: rgba(255,255,255,0.05); transition: all 0.3s; }
        .nav-links a:hover { color: #fff; background: rgba(255,255,255,0.15); }
        .step-indicator { display: flex; justify-content: center; gap: 8px; margin-bottom: 30px; flex-wrap: wrap; }
        .step { padding: 8px 14px; border-radius: 20px; background: rgba(255,255,255,0.1); font-size: 0.8em; transition: all 0.3s; }
        .step.active { background: #e94560; font-weight: bold; }
        .step.done { background: #2ecc71; }
        .card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px; padding: 24px; margin-bottom: 20px; backdrop-filter: blur(10px);
        }
        .card h2 { color: #e94560; margin-bottom: 16px; font-size: 1.4em; }
        .card h3 { color: #f0a500; margin-bottom: 12px; }
        .name-input {
            width: 100%; padding: 14px 20px; font-size: 1.1em;
            border: 2px solid rgba(255,255,255,0.2); border-radius: 10px;
            background: rgba(255,255,255,0.05); color: #fff; outline: none;
            margin-bottom: 10px;
        }
        .name-input:focus { border-color: #e94560; }
        .name-input::placeholder { color: rgba(255,255,255,0.4); }
        .group-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 20px; }
        .group-card {
            background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px; padding: 16px;
        }
        .group-card h3 { font-size: 1.1em; margin-bottom: 10px; color: #f0a500; }
        .sortable-list { list-style: none; padding: 0; }
        .sortable-list li {
            display: flex; align-items: center; gap: 10px;
            padding: 10px 14px; margin-bottom: 6px;
            background: rgba(255,255,255,0.08); border-radius: 8px;
            cursor: grab; transition: all 0.2s; user-select: none;
            border: 1px solid transparent;
        }
        .sortable-list li:hover { background: rgba(255,255,255,0.15); }
        .sortable-list li.dragging { opacity: 0.5; background: rgba(233, 69, 96, 0.3); }
        .sortable-list li .move-buttons { margin-left: auto; display: flex; gap: 4px; }
        .sortable-list li .move-btn {
            width: 28px; height: 28px; border-radius: 50%;
            border: 1px solid rgba(255,255,255,0.3); background: rgba(255,255,255,0.1);
            color: #fff; cursor: pointer; display: flex; align-items: center;
            justify-content: center; font-size: 14px; transition: all 0.2s;
        }
        .sortable-list li .move-btn:hover { background: rgba(233, 69, 96, 0.4); border-color: #e94560; }
        .position-badge {
            width: 24px; height: 24px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 0.8em; font-weight: bold; flex-shrink: 0;
        }
        .pos-1 { background: #ffd700; color: #000; }
        .pos-2 { background: #c0c0c0; color: #000; }
        .pos-3 { background: #cd7f32; color: #fff; }
        .pos-4 { background: #555; color: #fff; }
        .third-place-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; margin: 16px 0; }
        .third-place-option {
            padding: 10px; border-radius: 8px; text-align: center;
            background: rgba(255,255,255,0.05); border: 2px solid rgba(255,255,255,0.1);
            cursor: pointer; transition: all 0.3s;
        }
        .third-place-option:hover { background: rgba(255,255,255,0.1); }
        .third-place-option.selected { background: rgba(46, 204, 113, 0.2); border-color: #2ecc71; }
        .match-card {
            display: flex; align-items: center; justify-content: space-between;
            padding: 12px 16px; margin-bottom: 10px;
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px; gap: 10px;
        }
        .match-team {
            flex: 1; text-align: center; padding: 10px; border-radius: 8px;
            cursor: pointer; transition: all 0.3s; border: 2px solid transparent;
        }
        .match-team:hover { background: rgba(255,255,255,0.1); }
        .match-team.selected { background: rgba(46, 204, 113, 0.2); border-color: #2ecc71; }
        .match-vs { font-weight: bold; color: #e94560; font-size: 0.9em; flex-shrink: 0; }
        .knockout-round { margin-bottom: 24px; }
        .knockout-round h3 { margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .btn {
            display: inline-block; padding: 14px 32px; font-size: 1.1em;
            font-weight: bold; border: none; border-radius: 10px;
            cursor: pointer; transition: all 0.3s; text-transform: uppercase; letter-spacing: 1px;
        }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-primary:hover { background: #d63851; transform: translateY(-2px); box-shadow: 0 4px 15px rgba(233, 69, 96, 0.4); }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; border: 1px solid rgba(255,255,255,0.2); }
        .btn-secondary:hover { background: rgba(255,255,255,0.2); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; }
        .btn-group { display: flex; gap: 12px; justify-content: center; margin-top: 24px; flex-wrap: wrap; }
        .hidden { display: none; }
        .success-screen { text-align: center; padding: 40px 20px; }
        .success-screen h2 { color: #2ecc71; font-size: 2em; margin-bottom: 16px; }
        .success-screen .trophy { font-size: 4em; margin-bottom: 20px; }
        .champion-name { font-size: 1.5em; color: #ffd700; margin: 16px 0; }
        .drag-hint { color: #888; font-size: 0.85em; margin-bottom: 12px; font-style: italic; }
        .counter { color: #f0a500; font-weight: bold; margin: 8px 0; }
        .error-msg { color: #e94560; font-size: 0.9em; margin-top: 8px; display: none; }
        .error-msg.show { display: block; }
        @media (max-width: 600px) {
            h1 { font-size: 1.8em; }
            .match-card { flex-direction: column; }
            .match-team { width: 100%; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>&#9917; WK 2026 Voorspellingen</h1>
        <p class="subtitle">Vul je voorspellingen in voor het WK 2026!</p>
        <div class="nav-links">
            <a href="/scoreboard">&#127942; Scoreboard</a>
            <a href="/admin">&#128272; Admin</a>
        </div>

        <div class="step-indicator">
            <div class="step active" id="step-ind-1">1. Naam</div>
            <div class="step" id="step-ind-2">2. Groepsfase</div>
            <div class="step" id="step-ind-3">3. Beste #3</div>
            <div class="step" id="step-ind-4">4. Knock-out</div>
            <div class="step" id="step-ind-5">5. Klaar!</div>
        </div>

        <!-- STEP 1: Name -->
        <div id="step-1" class="card">
            <h2>&#128100; Wie ben je?</h2>
            <input type="text" class="name-input" id="player-name" placeholder="Vul je naam in..." autocomplete="off">
            <p class="error-msg" id="name-error">&#9888; Vul je naam in om verder te gaan!</p>
            <div class="btn-group">
                <button class="btn btn-primary" id="btn-next-1" type="button">Volgende &#8594;</button>
            </div>
        </div>

        <!-- STEP 2: Group Stage -->
        <div id="step-2" class="card hidden">
            <h2>&#128202; Groepsfase</h2>
            <p class="drag-hint">&#128161; Gebruik de pijltjes om landen te verplaatsen (1 = groepswinnaar, 4 = laatste). Je kunt ook slepen op desktop.</p>
            <div class="group-grid" id="groups-container"></div>
            <div class="btn-group">
                <button class="btn btn-secondary" id="btn-back-2" type="button">&#8592; Terug</button>
                <button class="btn btn-primary" id="btn-next-2" type="button">Volgende &#8594;</button>
            </div>
        </div>

        <!-- STEP 3: Best Third Places -->
        <div id="step-3" class="card hidden">
            <h2>&#127941; Beste Nummers 3</h2>
            <p class="drag-hint">Selecteer welke 8 nummers 3 doorgaan naar de knock-outfase</p>
            <p class="counter" id="third-counter">Geselecteerd: 0 / 8</p>
            <div class="third-place-grid" id="third-place-container"></div>
            <div class="btn-group">
                <button class="btn btn-secondary" id="btn-back-3" type="button">&#8592; Terug</button>
                <button class="btn btn-primary" id="btn-to-knockout" type="button" disabled>Volgende &#8594;</button>
            </div>
        </div>

        <!-- STEP 4: Knockout -->
        <div id="step-4" class="card hidden">
            <h2>&#127942; Knock-outfase</h2>
            <p class="drag-hint">Klik op het team dat je denkt dat wint</p>
            <div id="knockout-container"></div>
            <div class="btn-group">
                <button class="btn btn-secondary" id="btn-back-4" type="button">&#8592; Terug</button>
                <button class="btn btn-primary" id="btn-submit" type="button">&#9989; Voorspelling Indienen</button>
            </div>
        </div>

        <!-- STEP 5: Success -->
        <div id="step-5" class="card hidden">
            <div class="success-screen">
                <div class="trophy">&#127942;</div>
                <h2>Voorspelling Ingediend!</h2>
                <p>Bedankt <strong id="confirm-name"></strong>!</p>
                <p class="champion-name">Jouw kampioen: <span id="confirm-champion"></span></p>
                <div class="btn-group">
                    <button class="btn btn-secondary" onclick="location.reload()">Nieuwe Voorspelling</button>
                    <button class="btn btn-primary" onclick="window.location.href='/scoreboard'">Bekijk Scoreboard</button>
                </div>
            </div>
        </div>
    </div>

<script>
(function() {
    "use strict";

    var GROEPEN = %GROEPEN_JSON%;
    var currentStep = 1;
    var groupPredictions = {};
    var selectedThirds = [];
    var knockoutSelections = {};

    function goToStep(step) {
        if (step === 2) {
            var nameVal = document.getElementById('player-name').value.trim();
            if (!nameVal) {
                document.getElementById('name-error').classList.add('show');
                document.getElementById('player-name').focus();
                return;
            }
            document.getElementById('name-error').classList.remove('show');
        }
        if (step === 3) {
            groupPredictions = getGroupResults();
            buildThirdPlaces();
        }
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
        if (!container) return;
        container.innerHTML = '';
        var groups = Object.keys(GROEPEN);
        for (var g = 0; g < groups.length; g++) {
            var group = groups[g];
            var teams = GROEPEN[group];
            var card = document.createElement('div');
            card.className = 'group-card';
            var html = '<h3>Groep ' + group + '</h3>';
            html += '<ul class="sortable-list" id="group-' + group + '">';
            for (var i = 0; i < teams.length; i++) {
                html += '<li draggable="true" data-team="' + teams[i] + '">';
                html += '<span class="position-badge pos-' + (i+1) + '">' + (i+1) + '</span>';
                html += '<span class="team-name">' + teams[i] + '</span>';
                html += '<span class="move-buttons">';
                html += '<button type="button" class="move-btn" data-dir="up" title="Omhoog">&#9650;</button>';
                html += '<button type="button" class="move-btn" data-dir="down" title="Omlaag">&#9660;</button>';
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
            e.preventDefault(); e.stopPropagation();
            var li = btn.closest('li');
            var dir = btn.getAttribute('data-dir');
            if (dir === 'up' && li.previousElementSibling) list.insertBefore(li, li.previousElementSibling);
            else if (dir === 'down' && li.nextElementSibling) list.insertBefore(li.nextElementSibling, li);
            updatePositionBadges(list);
        });
    }

    function initSortable(list) {
        var draggedItem = null;
        list.addEventListener('dragstart', function(e) {
            draggedItem = e.target.closest('li');
            if (draggedItem) draggedItem.classList.add('dragging');
        });
        list.addEventListener('dragend', function(e) {
            if (draggedItem) { draggedItem.classList.remove('dragging'); draggedItem = null; updatePositionBadges(list); }
        });
        list.addEventListener('dragover', function(e) {
            e.preventDefault();
            if (!draggedItem) return;
            var afterElement = getDragAfterElement(list, e.clientY);
            if (afterElement == null) list.appendChild(draggedItem);
            else list.insertBefore(draggedItem, afterElement);
        });
    }

    function getDragAfterElement(container, y) {
        var elements = container.querySelectorAll('li:not(.dragging)');
        var closest = null, closestOffset = Number.NEGATIVE_INFINITY;
        for (var i = 0; i < elements.length; i++) {
            var box = elements[i].getBoundingClientRect();
            var offset = y - box.top - box.height / 2;
            if (offset < 0 && offset > closestOffset) { closestOffset = offset; closest = elements[i]; }
        }
        return closest;
    }

    function updatePositionBadges(list) {
        var items = list.querySelectorAll('li');
        for (var i = 0; i < items.length; i++) {
            var badge = items[i].querySelector('.position-badge');
            badge.className = 'position-badge pos-' + (i + 1);
            badge.textContent = i + 1;
        }
    }

    function getGroupResults() {
        var results = {};
        var groups = Object.keys(GROEPEN);
        for (var g = 0; g < groups.length; g++) {
            var group = groups[g];
            var list = document.getElementById('group-' + group);
            if (!list) continue;
            var items = list.querySelectorAll('li');
            results[group] = [];
            for (var i = 0; i < items.length; i++) results[group].push(items[i].getAttribute('data-team'));
        }
        return results;
    }

    function buildThirdPlaces() {
        var container = document.getElementById('third-place-container');
        container.innerHTML = '';
        selectedThirds = [];
        updateThirdCounter();
        var groups = Object.keys(groupPredictions);
        for (var g = 0; g < groups.length; g++) {
            var group = groups[g];
            var teams = groupPredictions[group];
            if (!teams || teams.length < 3) continue;
            var thirdPlace = teams[2];
            var div = document.createElement('div');
            div.className = 'third-place-option';
            div.id = 'third-' + group;
            div.textContent = thirdPlace + ' (Groep ' + group + ')';
            div.setAttribute('data-group', group);
            div.setAttribute('data-team', thirdPlace);
            (function(grp) { div.addEventListener('click', function() { toggleThird(grp); }); })(group);
            container.appendChild(div);
        }
    }

    function toggleThird(group) {
        var div = document.getElementById('third-' + group);
        var idx = selectedThirds.indexOf(group);
        if (idx >= 0) { selectedThirds.splice(idx, 1); div.classList.remove('selected'); }
        else {
            if (selectedThirds.length >= 8) { alert('Je kunt maximaal 8 nummers 3 selecteren!'); return; }
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
        var winners = [], runnersUp = [], thirds = [];
        var groups = Object.keys(groupPredictions);
        for (var g = 0; g < groups.length; g++) {
            var group = groups[g]; var teams = groupPredictions[group];
            winners.push({ team: teams[0], group: group });
            runnersUp.push({ team: teams[1], group: group });
        }
        for (var t = 0; t < selectedThirds.length; t++) {
            var grp = selectedThirds[t];
            thirds.push({ team: groupPredictions[grp][2], group: grp });
        }
        var r32Matches = [
            { team1: winners[0].team, team2: thirds.length > 0 ? thirds[0].team : 'TBD' },
            { team1: winners[1].team, team2: thirds.length > 1 ? thirds[1].team : 'TBD' },
            { team1: winners[2].team, team2: thirds.length > 2 ? thirds[2].team : 'TBD' },
            { team1: winners[3].team, team2: thirds.length > 3 ? thirds[3].team : 'TBD' },
            { team1: winners[4].team, team2: thirds.length > 4 ? thirds[4].team : 'TBD' },
            { team1: winners[5].team, team2: thirds.length > 5 ? thirds[5].team : 'TBD' },
            { team1: winners[6].team, team2: thirds.length > 6 ? thirds[6].team : 'TBD' },
            { team1: winners[7].team, team2: thirds.length > 7 ? thirds[7].team : 'TBD' },
            { team1: runnersUp[0].team, team2: runnersUp[1].team },
            { team1: runnersUp[2].team, team2: runnersUp[3].team },
            { team1: runnersUp[4].team, team2: runnersUp[5].team },
            { team1: runnersUp[6].team, team2: runnersUp[7].team },
            { team1: winners[8].team, team2: runnersUp[8].team },
            { team1: winners[9].team, team2: runnersUp[9].team },
            { team1: winners[10].team, team2: runnersUp[10].team },
            { team1: winners[11].team, team2: runnersUp[11].team }
        ];
        renderRound(container, '1/16 Finales (Ronde van 32)', r32Matches, 'r32');
    }

    function renderRound(container, title, matches, roundKey) {
        var div = document.createElement('div');
        div.className = 'knockout-round'; div.id = 'round-' + roundKey;
        var html = '<h3>' + title + '</h3>';
        for (var i = 0; i < matches.length; i++) {
            var m = matches[i];
            html += '<div class="match-card">';
            html += '<div class="match-team" id="' + roundKey + '-' + i + '-1" data-round="' + roundKey + '" data-match="' + i + '" data-side="1" data-team="' + escapeAttr(m.team1) + '">' + m.team1 + '</div>';
            html += '<span class="match-vs">VS</span>';
            html += '<div class="match-team" id="' + roundKey + '-' + i + '-2" data-round="' + roundKey + '" data-match="' + i + '" data-side="2" data-team="' + escapeAttr(m.team2) + '">' + m.team2 + '</div>';
            html += '</div>';
        }
        div.innerHTML = html;
        container.appendChild(div);
        var teamDivs = div.querySelectorAll('.match-team');
        for (var t = 0; t < teamDivs.length; t++) teamDivs[t].addEventListener('click', handleMatchClick);
    }

    function escapeAttr(str) { return str.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

    function handleMatchClick(e) {
        var el = e.currentTarget;
        var roundKey = el.getAttribute('data-round');
        var matchIndex = parseInt(el.getAttribute('data-match'));
        var teamName = el.getAttribute('data-team');
        var el1 = document.getElementById(roundKey + '-' + matchIndex + '-1');
        var el2 = document.getElementById(roundKey + '-' + matchIndex + '-2');
        el1.classList.remove('selected'); el2.classList.remove('selected');
        el.classList.add('selected');
        knockoutSelections[roundKey][matchIndex] = teamName;
        buildNextRound(roundKey);
    }

    function buildNextRound(roundKey) {
        var container = document.getElementById('knockout-container');
        var expectedCounts = { r32: 16, r16: 8, qf: 4, sf: 2, final_round: 1 };
        var nextRounds = { r32: 'r16', r16: 'qf', qf: 'sf', sf: 'final_round' };
        var nextNames = { r32: '1/8 Finales (Ronde van 16)', r16: 'Kwartfinales', qf: 'Halve Finales', sf: '&#127942; FINALE' };
        var count = Object.keys(knockoutSelections[roundKey]).length;
        if (count < expectedCounts[roundKey]) return;
        var nextKey = nextRounds[roundKey];
        if (!nextKey) return;
        var order = ['r16', 'qf', 'sf', 'final_round'];
        var startIdx = order.indexOf(nextKey);
        for (var i = startIdx; i < order.length; i++) {
            var existingEl = document.getElementById('round-' + order[i]);
            if (existingEl) existingEl.remove();
            knockoutSelections[order[i]] = {};
        }
        var winners = [];
        for (var j = 0; j < expectedCounts[roundKey]; j++) winners.push(knockoutSelections[roundKey][j]);
        var nextMatches = [];
        for (var k = 0; k < winners.length; k += 2) nextMatches.push({ team1: winners[k], team2: winners[k + 1] });
        renderRound(container, nextNames[roundKey], nextMatches, nextKey);
    }

    function submitPrediction() {
        var name = document.getElementById('player-name').value.trim();
        var groups = getGroupResults();
        if (!knockoutSelections.final_round || knockoutSelections.final_round[0] === undefined) {
            alert('Vul alle knock-outwedstrijden in!'); return;
        }
        var data = {
            naam: name, groepsfase: groups,
            beste_derdes: selectedThirds.map(function(g) { return { groep: g, team: groupPredictions[g][2] }; }),
            knockout: {
                ronde_van_32: knockoutSelections.r32, ronde_van_16: knockoutSelections.r16,
                kwartfinales: knockoutSelections.qf, halve_finales: knockoutSelections.sf,
                finale: knockoutSelections.final_round[0]
            }
        };
        fetch('/api/submit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
        .then(function(res) { return res.json(); })
        .then(function(result) {
            if (result.success) {
                document.getElementById('confirm-name').textContent = name;
                document.getElementById('confirm-champion').textContent = knockoutSelections.final_round[0];
                goToStep(5);
            } else { alert('Er ging iets mis: ' + result.error); }
        })
        .catch(function(err) { alert('Fout bij verzenden: ' + err.message); });
    }

    document.getElementById('btn-next-1').addEventListener('click', function() { goToStep(2); });
    document.getElementById('btn-back-2').addEventListener('click', function() { goToStep(1); });
    document.getElementById('btn-next-2').addEventListener('click', function() { goToStep(3); });
    document.getElementById('btn-back-3').addEventListener('click', function() { goToStep(2); });
    document.getElementById('btn-to-knockout').addEventListener('click', function() { goToStep(4); });
    document.getElementById('btn-back-4').addEventListener('click', function() { goToStep(3); });
    document.getElementById('btn-submit').addEventListener('click', function() { submitPrediction(); });
    document.getElementById('player-name').addEventListener('keypress', function(e) { if (e.key === 'Enter') goToStep(2); });
    document.getElementById('player-name').addEventListener('input', function() { document.getElementById('name-error').classList.remove('show'); });

    buildGroups();
})();
</script>
</body>
</html>
"""

# ============================================================
# SCOREBOARD - Publiek, iedereen kan dit zien
# ============================================================
SCOREBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scoreboard - WK 2026</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh; color: #fff; padding: 20px;
        }
        .container { max-width: 1000px; margin: 0 auto; }
        h1 { text-align: center; font-size: 2.2em; margin-bottom: 10px; }
        .subtitle { text-align: center; color: #aaa; margin-bottom: 30px; }
        .nav-links { text-align: center; margin-bottom: 20px; }
        .nav-links a { color: #aaa; text-decoration: none; margin: 0 10px; padding: 8px 16px; border-radius: 8px; background: rgba(255,255,255,0.05); transition: all 0.3s; }
        .nav-links a:hover { color: #fff; background: rgba(255,255,255,0.15); }
        .card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px; padding: 24px; margin-bottom: 20px;
        }
        .card h2 { color: #e94560; margin-bottom: 16px; }
        .leaderboard { width: 100%; border-collapse: collapse; }
        .leaderboard th {
            background: rgba(233, 69, 96, 0.2); padding: 12px 10px;
            text-align: center; border-bottom: 2px solid rgba(255,255,255,0.1);
            font-size: 0.8em; color: #ccc;
        }
        .leaderboard td { padding: 12px 10px; border-bottom: 1px solid rgba(255,255,255,0.05); text-align: center; }
        .leaderboard tr:hover { background: rgba(255,255,255,0.05); }
        .leaderboard .rank { font-weight: bold; font-size: 1.2em; }
        .rank-1 { color: #ffd700; }
        .rank-2 { color: #c0c0c0; }
        .rank-3 { color: #cd7f32; }
        .leaderboard .name { text-align: left; font-weight: bold; }
        .leaderboard .champion { color: #aaa; font-size: 0.85em; }
        .leaderboard .total { font-weight: bold; font-size: 1.3em; color: #2ecc71; }
        .punten-info {
            background: rgba(255,215,0,0.08); border: 1px solid rgba(255,215,0,0.2);
            border-radius: 12px; padding: 16px; margin-bottom: 20px;
        }
        .punten-info h3 { color: #ffd700; margin-bottom: 8px; font-size: 1em; }
        .punten-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 4px; }
        .punten-grid span { color: #ccc; font-size: 0.85em; }
        .punten-grid strong { color: #fff; }
        .no-data { text-align: center; padding: 40px; color: #888; }
        .no-data a { color: #e94560; text-decoration: none; }
        .last-update { text-align: center; color: #666; font-size: 0.8em; margin-top: 12px; }
        @media (max-width: 700px) {
            .leaderboard { font-size: 0.85em; }
            .leaderboard th, .leaderboard td { padding: 8px 4px; }
            .hide-mobile { display: none; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>&#127942; Scoreboard</h1>
        <p class="subtitle">Live rangschikking van alle deelnemers</p>
        <div class="nav-links">
            <a href="/">&#9917; Voorspelling invullen</a>
            <a href="/admin">&#128272; Admin</a>
        </div>

        <div class="punten-info">
            <h3>&#128218; Puntensysteem</h3>
            <div class="punten-grid">
                <span><strong>1pt</strong> juiste positie in groep</span>
                <span><strong>2pt</strong> juiste groepswinnaar</span>
                <span><strong>1pt</strong> juiste #2 in groep</span>
                <span><strong>2pt</strong> juiste beste derde</span>
                <span><strong>3pt</strong> 1/16e finale juist</span>
                <span><strong>5pt</strong> 1/8e finale juist</span>
                <span><strong>7pt</strong> kwartfinale juist</span>
                <span><strong>10pt</strong> halve finale juist</span>
                <span><strong>12pt</strong> juiste finalist</span>
                <span><strong>15pt</strong> juiste kampioen</span>
            </div>
        </div>

        <div class="card">
            <h2>&#128203; Rangschikking</h2>
            <div id="scoreboard-content"><p style="color:#888;">Laden...</p></div>
        </div>
    </div>

<script>
fetch('/api/scoreboard')
.then(function(res) { return res.json(); })
.then(function(data) {
    var container = document.getElementById('scoreboard-content');
    if (!data.players || data.players.length === 0) {
        container.innerHTML = '<div class="no-data"><p>Nog geen voorspellingen ingediend.</p><p><a href="/">Wees de eerste!</a></p></div>';
        return;
    }
    var html = '<table class="leaderboard"><thead><tr>';
    html += '<th>#</th><th style="text-align:left;">Speler</th><th>Kampioen</th>';
    html += '<th class="hide-mobile">Groep</th><th class="hide-mobile">R32</th><th class="hide-mobile">R16</th>';
    html += '<th class="hide-mobile">KF</th><th class="hide-mobile">HF</th><th class="hide-mobile">Fin</th>';
    html += '<th>TOTAAL</th></tr></thead><tbody>';

    for (var i = 0; i < data.players.length; i++) {
        var p = data.players[i];
        var rankClass = i === 0 ? 'rank-1' : i === 1 ? 'rank-2' : i === 2 ? 'rank-3' : '';
        var medal = i === 0 ? '&#129351;' : i === 1 ? '&#129352;' : i === 2 ? '&#129353;' : (i+1);
        html += '<tr>';
        html += '<td class="rank ' + rankClass + '">' + medal + '</td>';
        html += '<td class="name">' + p.naam + '</td>';
        html += '<td class="champion">' + (p.kampioen || '?') + '</td>';
        var groepPts = p.points.groep_positie + p.points.groep_winnaar + p.points.groep_tweede + p.points.beste_derdes;
        html += '<td class="hide-mobile">' + groepPts + '</td>';
        html += '<td class="hide-mobile">' + p.points.r32 + '</td>';
        html += '<td class="hide-mobile">' + p.points.r16 + '</td>';
        html += '<td class="hide-mobile">' + p.points.qf + '</td>';
        html += '<td class="hide-mobile">' + p.points.sf + '</td>';
        html += '<td class="hide-mobile">' + (p.points.finalist + p.points.winnaar) + '</td>';
        html += '<td class="total">' + p.points.totaal + '</td>';
        html += '</tr>';
    }
    html += '</tbody></table>';
    if (data.results_available) {
        html += '<p class="last-update">&#9989; Echte resultaten zijn ingevuld - punten worden live berekend</p>';
    } else {
        html += '<p class="last-update">&#9888; Nog geen echte resultaten ingevuld - alle punten staan op 0</p>';
    }
    container.innerHTML = html;
});
</script>
</body>
</html>
"""

# ============================================================
# ADMIN LOGIN
# ============================================================
ADMIN_LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - WK 2026</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh; color: #fff; padding: 20px;
            display: flex; align-items: center; justify-content: center;
        }
        .card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px; padding: 40px; max-width: 400px; width: 100%;
        }
        .card h2 { color: #e94560; margin-bottom: 20px; text-align: center; }
        .name-input {
            width: 100%; padding: 14px 20px; font-size: 1.1em;
            border: 2px solid rgba(255,255,255,0.2); border-radius: 10px;
            background: rgba(255,255,255,0.05); color: #fff; outline: none; margin-bottom: 16px;
        }
        .name-input:focus { border-color: #e94560; }
        .name-input::placeholder { color: rgba(255,255,255,0.4); }
        .btn { width: 100%; padding: 14px; font-size: 1.1em; font-weight: bold; border: none; border-radius: 10px; cursor: pointer; background: #e94560; color: #fff; }
        .btn:hover { background: #d63851; }
        .error { color: #e94560; text-align: center; margin-top: 12px; }
        .back-link { text-align: center; margin-top: 16px; }
        .back-link a { color: #aaa; text-decoration: none; }
        .back-link a:hover { color: #fff; }
    </style>
</head>
<body>
    <div class="card">
        <h2>&#128272; Admin Login</h2>
        <form method="POST">
            <input type="password" name="password" class="name-input" placeholder="Admin wachtwoord..." autofocus>
            <button type="submit" class="btn">Inloggen</button>
        </form>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        <div class="back-link"><a href="/">&larr; Terug</a></div>
    </div>
</body>
</html>
"""

# ============================================================
# ADMIN DASHBOARD - Met dezelfde stap-voor-stap UI voor echte resultaten
# ============================================================
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin - WK 2026</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh; color: #fff; padding: 20px;
        }
        .container { max-width: 1000px; margin: 0 auto; }
        h1 { text-align: center; font-size: 2.2em; margin-bottom: 10px; }
        .subtitle { text-align: center; color: #aaa; margin-bottom: 30px; }
        .nav-links { text-align: center; margin-bottom: 20px; }
        .nav-links a { color: #aaa; text-decoration: none; margin: 0 10px; padding: 8px 16px; border-radius: 8px; background: rgba(255,255,255,0.05); transition: all 0.3s; }
        .nav-links a:hover { color: #fff; background: rgba(255,255,255,0.15); }
        .card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px; padding: 24px; margin-bottom: 20px;
        }
        .card h2 { color: #e94560; margin-bottom: 16px; font-size: 1.4em; }
        .card h3 { color: #f0a500; margin-bottom: 12px; }
        .tabs { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab { padding: 10px 20px; border-radius: 8px; cursor: pointer; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); transition: all 0.3s; color: #aaa; }
        .tab:hover { background: rgba(255,255,255,0.1); color: #fff; }
        .tab.active { background: #e94560; color: #fff; border-color: #e94560; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .group-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 20px; }
        .group-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px; }
        .group-card h3 { font-size: 1.1em; margin-bottom: 10px; color: #f0a500; }
        .sortable-list { list-style: none; padding: 0; }
        .sortable-list li {
            display: flex; align-items: center; gap: 10px;
            padding: 10px 14px; margin-bottom: 6px;
            background: rgba(255,255,255,0.08); border-radius: 8px;
            cursor: grab; transition: all 0.2s; user-select: none;
        }
        .sortable-list li:hover { background: rgba(255,255,255,0.15); }
        .sortable-list li.dragging { opacity: 0.5; background: rgba(233, 69, 96, 0.3); }
        .sortable-list li .move-buttons { margin-left: auto; display: flex; gap: 4px; }
        .sortable-list li .move-btn {
            width: 28px; height: 28px; border-radius: 50%;
            border: 1px solid rgba(255,255,255,0.3); background: rgba(255,255,255,0.1);
            color: #fff; cursor: pointer; display: flex; align-items: center;
            justify-content: center; font-size: 14px; transition: all 0.2s;
        }
        .sortable-list li .move-btn:hover { background: rgba(233, 69, 96, 0.4); border-color: #e94560; }
        .position-badge {
            width: 24px; height: 24px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 0.8em; font-weight: bold; flex-shrink: 0;
        }
        .pos-1 { background: #ffd700; color: #000; }
        .pos-2 { background: #c0c0c0; color: #000; }
        .pos-3 { background: #cd7f32; color: #fff; }
        .pos-4 { background: #555; color: #fff; }
        .third-place-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; margin: 16px 0; }
        .third-place-option {
            padding: 10px; border-radius: 8px; text-align: center;
            background: rgba(255,255,255,0.05); border: 2px solid rgba(255,255,255,0.1);
            cursor: pointer; transition: all 0.3s;
        }
        .third-place-option:hover { background: rgba(255,255,255,0.1); }
        .third-place-option.selected { background: rgba(46, 204, 113, 0.2); border-color: #2ecc71; }
        .match-card {
            display: flex; align-items: center; justify-content: space-between;
            padding: 12px 16px; margin-bottom: 10px;
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px; gap: 10px;
        }
        .match-team { flex: 1; text-align: center; padding: 10px; border-radius: 8px; cursor: pointer; transition: all 0.3s; border: 2px solid transparent; }
        .match-team:hover { background: rgba(255,255,255,0.1); }
        .match-team.selected { background: rgba(46, 204, 113, 0.2); border-color: #2ecc71; }
        .match-vs { font-weight: bold; color: #e94560; font-size: 0.9em; flex-shrink: 0; }
        .knockout-round { margin-bottom: 24px; }
        .knockout-round h3 { margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .btn { display: inline-block; padding: 14px 32px; font-size: 1.1em; font-weight: bold; border: none; border-radius: 10px; cursor: pointer; transition: all 0.3s; }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-primary:hover { background: #d63851; transform: translateY(-2px); }
        .btn-success { background: #2ecc71; color: #fff; }
        .btn-success:hover { background: #27ae60; transform: translateY(-2px); }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; border: 1px solid rgba(255,255,255,0.2); }
        .btn-secondary:hover { background: rgba(255,255,255,0.2); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; }
        .btn-group { display: flex; gap: 12px; justify-content: center; margin-top: 24px; flex-wrap: wrap; }
        .hidden { display: none; }
        .drag-hint { color: #888; font-size: 0.85em; margin-bottom: 12px; font-style: italic; }
        .counter { color: #f0a500; font-weight: bold; margin: 8px 0; }
        .status-msg { padding: 12px; border-radius: 8px; margin-top: 12px; text-align: center; }
        .status-msg.success { background: rgba(46, 204, 113, 0.2); border: 1px solid #2ecc71; color: #2ecc71; }
        .status-msg.error { background: rgba(231, 76, 60, 0.2); border: 1px solid #e74c3c; color: #e74c3c; }
        .leaderboard { width: 100%; border-collapse: collapse; margin-top: 12px; }
        .leaderboard th { background: rgba(233, 69, 96, 0.2); padding: 12px 10px; text-align: center; border-bottom: 2px solid rgba(255,255,255,0.1); font-size: 0.8em; }
        .leaderboard td { padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); text-align: center; }
        .leaderboard tr:hover { background: rgba(255,255,255,0.05); }
        .leaderboard .name { text-align: left; font-weight: bold; }
        .leaderboard .total { font-weight: bold; font-size: 1.2em; color: #2ecc71; }
        .player-detail-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 16px; margin-bottom: 12px; }
        .player-detail-card h4 { color: #e94560; margin-bottom: 8px; }
        .player-detail-card .info { color: #aaa; font-size: 0.85em; margin-bottom: 4px; }
        @media (max-width: 600px) {
            .match-card { flex-direction: column; }
            .match-team { width: 100%; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>&#128272; Admin Dashboard</h1>
        <p class="subtitle">Beheer echte resultaten en bekijk alle voorspellingen</p>
        <div class="nav-links">
            <a href="/">&#9917; Home</a>
            <a href="/scoreboard">&#127942; Scoreboard</a>
            <a href="/admin/logout">&#128682; Uitloggen</a>
        </div>

        <div class="tabs">
            <div class="tab active" data-tab="results-input">&#9989; Echte Resultaten Invullen</div>
            <div class="tab" data-tab="leaderboard">&#127942; Rangschikking</div>
            <div class="tab" data-tab="all-predictions">&#128203; Alle Voorspellingen</div>
        </div>

        <!-- RESULTS INPUT TAB - Dezelfde UI als speler-invoer -->
        <div class="tab-content active" id="tab-results-input">
            <div class="card">
                <h2>&#9989; Echte Resultaten Invullen</h2>
                <p class="drag-hint">Vul de echte resultaten in op dezelfde manier als spelers hun voorspellingen invoeren. Sleep of gebruik pijltjes om de eindstand per groep aan te geven.</p>

                <div class="step-indicator" style="margin: 20px 0;">
                    <div class="step active" id="admin-step-ind-1">1. Groepsfase</div>
                    <div class="step" id="admin-step-ind-2">2. Beste #3</div>
                    <div class="step" id="admin-step-ind-3">3. Knock-out</div>
                </div>

                <!-- Admin Step 1: Groups -->
                <div id="admin-step-1">
                    <h3>Eindstand Groepsfase</h3>
                    <p class="drag-hint">Zet de teams in de juiste volgorde (1 = groepswinnaar, 4 = laatste)</p>
                    <div class="group-grid" id="admin-groups-container"></div>
                    <div class="btn-group">
                        <button class="btn btn-primary" id="admin-btn-next-1" type="button">Volgende: Beste Derdes &#8594;</button>
                    </div>
                </div>

                <!-- Admin Step 2: Best Thirds -->
                <div id="admin-step-2" class="hidden">
                    <h3>Beste Nummers 3</h3>
                    <p class="drag-hint">Selecteer welke 8 nummers 3 zijn doorgegaan</p>
                    <p class="counter" id="admin-third-counter">Geselecteerd: 0 / 8</p>
                    <div class="third-place-grid" id="admin-third-place-container"></div>
                    <div class="btn-group">
                        <button class="btn btn-secondary" id="admin-btn-back-2" type="button">&#8592; Terug</button>
                        <button class="btn btn-primary" id="admin-btn-next-2" type="button" disabled>Volgende: Knock-out &#8594;</button>
                    </div>
                </div>

                <!-- Admin Step 3: Knockout -->
                <div id="admin-step-3" class="hidden">
                    <h3>Knock-out Resultaten</h3>
                    <p class="drag-hint">Klik op het team dat daadwerkelijk gewonnen heeft</p>
                    <div id="admin-knockout-container"></div>
                    <div class="btn-group">
                        <button class="btn btn-secondary" id="admin-btn-back-3" type="button">&#8592; Terug</button>
                        <button class="btn btn-success" id="admin-btn-save" type="button">&#128190; Resultaten Opslaan</button>
                    </div>
                </div>

                <div class="status-msg hidden" id="admin-save-status"></div>
            </div>
        </div>

        <!-- LEADERBOARD TAB -->
        <div class="tab-content" id="tab-leaderboard">
            <div class="card">
                <h2>&#127942; Rangschikking</h2>
                <div id="admin-leaderboard-container"><p style="color:#888;">Laden...</p></div>
            </div>
        </div>

        <!-- ALL PREDICTIONS TAB -->
        <div class="tab-content" id="tab-all-predictions">
            <div class="card">
                <h2>&#128203; Alle Voorspellingen</h2>
                <div id="all-predictions-container"><p style="color:#888;">Laden...</p></div>
            </div>
        </div>
    </div>

<script>
(function() {
    "use strict";

    var GROEPEN = %GROEPEN_JSON%;
    var adminGroupResults = {};
    var adminSelectedThirds = [];
    var adminKnockoutSelections = {};
    var adminCurrentStep = 1;

    // ============ TAB NAVIGATION ============
    document.querySelectorAll('.tab').forEach(function(tab) {
        tab.addEventListener('click', function() {
            document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
            document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
            tab.classList.add('active');
            document.getElementById('tab-' + tab.getAttribute('data-tab')).classList.add('active');
        });
    });

    // ============ ADMIN RESULTS INPUT (same UI as player) ============
    function adminGoToStep(step) {
        if (step === 2) {
            adminGroupResults = adminGetGroupResults();
            adminBuildThirdPlaces();
        }
        if (step === 3) {
            if (adminSelectedThirds.length !== 8) { alert('Selecteer precies 8 nummers 3!'); return; }
            adminBuildKnockout();
        }
        document.getElementById('admin-step-' + adminCurrentStep).classList.add('hidden');
        document.getElementById('admin-step-' + step).classList.remove('hidden');
        for (var i = 1; i <= 3; i++) {
            var ind = document.getElementById('admin-step-ind-' + i);
            ind.classList.remove('active', 'done');
            if (i < step) ind.classList.add('done');
            if (i === step) ind.classList.add('active');
        }
        adminCurrentStep = step;
    }

    function adminBuildGroups() {
        var container = document.getElementById('admin-groups-container');
        if (!container) return;
        container.innerHTML = '';
        var groups = Object.keys(GROEPEN);
        for (var g = 0; g < groups.length; g++) {
            var group = groups[g];
            var teams = GROEPEN[group];
            var card = document.createElement('div');
            card.className = 'group-card';
            var html = '<h3>Groep ' + group + '</h3>';
            html += '<ul class="sortable-list" id="admin-group-' + group + '">';
            for (var i = 0; i < teams.length; i++) {
                html += '<li draggable="true" data-team="' + teams[i] + '">';
                html += '<span class="position-badge pos-' + (i+1) + '">' + (i+1) + '</span>';
                html += '<span class="team-name">' + teams[i] + '</span>';
                html += '<span class="move-buttons">';
                html += '<button type="button" class="move-btn" data-dir="up" title="Omhoog">&#9650;</button>';
                html += '<button type="button" class="move-btn" data-dir="down" title="Omlaag">&#9660;</button>';
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
            e.preventDefault(); e.stopPropagation();
            var li = btn.closest('li');
            var dir = btn.getAttribute('data-dir');
            if (dir === 'up' && li.previousElementSibling) list.insertBefore(li, li.previousElementSibling);
            else if (dir === 'down' && li.nextElementSibling) list.insertBefore(li.nextElementSibling, li);
            updatePositionBadges(list);
        });
    }

    function initSortable(list) {
        var draggedItem = null;
        list.addEventListener('dragstart', function(e) {
            draggedItem = e.target.closest('li');
            if (draggedItem) draggedItem.classList.add('dragging');
        });
        list.addEventListener('dragend', function(e) {
            if (draggedItem) { draggedItem.classList.remove('dragging'); draggedItem = null; updatePositionBadges(list); }
        });
        list.addEventListener('dragover', function(e) {
            e.preventDefault();
            if (!draggedItem) return;
            var afterElement = getDragAfterElement(list, e.clientY);
            if (afterElement == null) list.appendChild(draggedItem);
            else list.insertBefore(draggedItem, afterElement);
        });
    }

    function getDragAfterElement(container, y) {
        var elements = container.querySelectorAll('li:not(.dragging)');
        var closest = null, closestOffset = Number.NEGATIVE_INFINITY;
        for (var i = 0; i < elements.length; i++) {
            var box = elements[i].getBoundingClientRect();
            var offset = y - box.top - box.height / 2;
            if (offset < 0 && offset > closestOffset) { closestOffset = offset; closest = elements[i]; }
        }
        return closest;
    }

    function updatePositionBadges(list) {
        var items = list.querySelectorAll('li');
        for (var i = 0; i < items.length; i++) {
            var badge = items[i].querySelector('.position-badge');
            badge.className = 'position-badge pos-' + (i + 1);
            badge.textContent = i + 1;
        }
    }

    function adminGetGroupResults() {
        var results = {};
        var groups = Object.keys(GROEPEN);
        for (var g = 0; g < groups.length; g++) {
            var group = groups[g];
            var list = document.getElementById('admin-group-' + group);
            if (!list) continue;
            var items = list.querySelectorAll('li');
            results[group] = [];
            for (var i = 0; i < items.length; i++) results[group].push(items[i].getAttribute('data-team'));
        }
        return results;
    }

    function adminBuildThirdPlaces() {
        var container = document.getElementById('admin-third-place-container');
        container.innerHTML = '';
        adminSelectedThirds = [];
        adminUpdateThirdCounter();
        var groups = Object.keys(adminGroupResults);
        for (var g = 0; g < groups.length; g++) {
            var group = groups[g];
            var teams = adminGroupResults[group];
            if (!teams || teams.length < 3) continue;
            var thirdPlace = teams[2];
            var div = document.createElement('div');
            div.className = 'third-place-option';
            div.id = 'admin-third-' + group;
            div.textContent = thirdPlace + ' (Groep ' + group + ')';
            div.setAttribute('data-group', group);
            div.setAttribute('data-team', thirdPlace);
            (function(grp) { div.addEventListener('click', function() { adminToggleThird(grp); }); })(group);
            container.appendChild(div);
        }
    }

    function adminToggleThird(group) {
        var div = document.getElementById('admin-third-' + group);
        var idx = adminSelectedThirds.indexOf(group);
        if (idx >= 0) { adminSelectedThirds.splice(idx, 1); div.classList.remove('selected'); }
        else {
            if (adminSelectedThirds.length >= 8) { alert('Maximaal 8!'); return; }
            adminSelectedThirds.push(group); div.classList.add('selected');
        }
        adminUpdateThirdCounter();
    }

    function adminUpdateThirdCounter() {
        document.getElementById('admin-third-counter').textContent = 'Geselecteerd: ' + adminSelectedThirds.length + ' / 8';
        document.getElementById('admin-btn-next-2').disabled = (adminSelectedThirds.length !== 8);
    }

    function adminBuildKnockout() {
        var container = document.getElementById('admin-knockout-container');
        container.innerHTML = '';
        adminKnockoutSelections = { r32: {}, r16: {}, qf: {}, sf: {}, final_round: {} };
        var winners = [], runnersUp = [], thirds = [];
        var groups = Object.keys(adminGroupResults);
        for (var g = 0; g < groups.length; g++) {
            var group = groups[g]; var teams = adminGroupResults[group];
            winners.push({ team: teams[0], group: group });
            runnersUp.push({ team: teams[1], group: group });
        }
        for (var t = 0; t < adminSelectedThirds.length; t++) {
            var grp = adminSelectedThirds[t];
            thirds.push({ team: adminGroupResults[grp][2], group: grp });
        }
        var r32Matches = [
            { team1: winners[0].team, team2: thirds.length > 0 ? thirds[0].team : 'TBD' },
            { team1: winners[1].team, team2: thirds.length > 1 ? thirds[1].team : 'TBD' },
            { team1: winners[2].team, team2: thirds.length > 2 ? thirds[2].team : 'TBD' },
            { team1: winners[3].team, team2: thirds.length > 3 ? thirds[3].team : 'TBD' },
            { team1: winners[4].team, team2: thirds.length > 4 ? thirds[4].team : 'TBD' },
            { team1: winners[5].team, team2: thirds.length > 5 ? thirds[5].team : 'TBD' },
            { team1: winners[6].team, team2: thirds.length > 6 ? thirds[6].team : 'TBD' },
            { team1: winners[7].team, team2: thirds.length > 7 ? thirds[7].team : 'TBD' },
            { team1: runnersUp[0].team, team2: runnersUp[1].team },
            { team1: runnersUp[2].team, team2: runnersUp[3].team },
            { team1: runnersUp[4].team, team2: runnersUp[5].team },
            { team1: runnersUp[6].team, team2: runnersUp[7].team },
            { team1: winners[8].team, team2: runnersUp[8].team },
            { team1: winners[9].team, team2: runnersUp[9].team },
            { team1: winners[10].team, team2: runnersUp[10].team },
            { team1: winners[11].team, team2: runnersUp[11].team }
        ];
        adminRenderRound(container, '1/16 Finales (Ronde van 32)', r32Matches, 'r32');
    }

    function adminRenderRound(container, title, matches, roundKey) {
        var div = document.createElement('div');
        div.className = 'knockout-round'; div.id = 'admin-round-' + roundKey;
        var html = '<h3>' + title + '</h3>';
        for (var i = 0; i < matches.length; i++) {
            var m = matches[i];
            html += '<div class="match-card">';
            html += '<div class="match-team" id="admin-' + roundKey + '-' + i + '-1" data-round="' + roundKey + '" data-match="' + i + '" data-side="1" data-team="' + escapeAttr(m.team1) + '">' + m.team1 + '</div>';
            html += '<span class="match-vs">VS</span>';
            html += '<div class="match-team" id="admin-' + roundKey + '-' + i + '-2" data-round="' + roundKey + '" data-match="' + i + '" data-side="2" data-team="' + escapeAttr(m.team2) + '">' + m.team2 + '</div>';
            html += '</div>';
        }
        div.innerHTML = html;
        container.appendChild(div);
        var teamDivs = div.querySelectorAll('.match-team');
        for (var t = 0; t < teamDivs.length; t++) teamDivs[t].addEventListener('click', adminHandleMatchClick);
    }

    function escapeAttr(str) { return str.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

    function adminHandleMatchClick(e) {
        var el = e.currentTarget;
        var roundKey = el.getAttribute('data-round');
        var matchIndex = parseInt(el.getAttribute('data-match'));
        var teamName = el.getAttribute('data-team');
        var el1 = document.getElementById('admin-' + roundKey + '-' + matchIndex + '-1');
        var el2 = document.getElementById('admin-' + roundKey + '-' + matchIndex + '-2');
        el1.classList.remove('selected'); el2.classList.remove('selected');
        el.classList.add('selected');
        adminKnockoutSelections[roundKey][matchIndex] = teamName;
        adminBuildNextRound(roundKey);
    }

    function adminBuildNextRound(roundKey) {
        var container = document.getElementById('admin-knockout-container');
        var expectedCounts = { r32: 16, r16: 8, qf: 4, sf: 2, final_round: 1 };
        var nextRounds = { r32: 'r16', r16: 'qf', qf: 'sf', sf: 'final_round' };
        var nextNames = { r32: '1/8 Finales (Ronde van 16)', r16: 'Kwartfinales', qf: 'Halve Finales', sf: '&#127942; FINALE' };
        var count = Object.keys(adminKnockoutSelections[roundKey]).length;
        if (count < expectedCounts[roundKey]) return;
        var nextKey = nextRounds[roundKey];
        if (!nextKey) return;
        var order = ['r16', 'qf', 'sf', 'final_round'];
        var startIdx = order.indexOf(nextKey);
        for (var i = startIdx; i < order.length; i++) {
            var existingEl = document.getElementById('admin-round-' + order[i]);
            if (existingEl) existingEl.remove();
            adminKnockoutSelections[order[i]] = {};
        }
        var winners = [];
        for (var j = 0; j < expectedCounts[roundKey]; j++) winners.push(adminKnockoutSelections[roundKey][j]);
        var nextMatches = [];
        for (var k = 0; k < winners.length; k += 2) nextMatches.push({ team1: winners[k], team2: winners[k + 1] });
        adminRenderRound(container, nextNames[roundKey], nextMatches, nextKey);
    }

    function adminSaveResults() {
        var groups = adminGetGroupResults();

        if (!adminKnockoutSelections.final_round || adminKnockoutSelections.final_round[0] === undefined) {
            alert('Vul alle knock-outwedstrijden in!'); return;
        }

        var data = {
            groepsfase: groups,
            beste_derdes: adminSelectedThirds.map(function(g) { return { groep: g, team: adminGroupResults[g][2] }; }),
            knockout: {
                ronde_van_32: adminKnockoutSelections.r32,
                ronde_van_16: adminKnockoutSelections.r16,
                kwartfinales: adminKnockoutSelections.qf,
                halve_finales: adminKnockoutSelections.sf,
                finale: adminKnockoutSelections.final_round[0]
            }
        };

        fetch('/api/admin/results', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        })
        .then(function(res) { return res.json(); })
        .then(function(result) {
            var status = document.getElementById('admin-save-status');
            status.classList.remove('hidden');
            if (result.success) {
                status.className = 'status-msg success';
                status.innerHTML = '&#9989; Resultaten opgeslagen! Punten worden automatisch herberekend voor alle spelers.';
                loadAdminLeaderboard();
            } else {
                status.className = 'status-msg error';
                status.textContent = 'Fout: ' + result.error;
            }
        })
        .catch(function(err) {
            var status = document.getElementById('admin-save-status');
            status.classList.remove('hidden');
            status.className = 'status-msg error';
            status.textContent = 'Fout: ' + err.message;
        });
    }

    // ============ ADMIN LEADERBOARD ============
    function loadAdminLeaderboard() {
        fetch('/api/scoreboard')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            var container = document.getElementById('admin-leaderboard-container');
            if (!data.players || data.players.length === 0) {
                container.innerHTML = '<p style="color:#888;">Nog geen voorspellingen.</p>'; return;
            }
            var html = '<table class="leaderboard"><thead><tr>';
            html += '<th>#</th><th style="text-align:left;">Speler</th><th>Kampioen</th>';
            html += '<th>Groep</th><th>Derdes</th><th>R32</th><th>R16</th><th>KF</th><th>HF</th><th>Fin+Win</th>';
            html += '<th>TOTAAL</th></tr></thead><tbody>';
            for (var i = 0; i < data.players.length; i++) {
                var p = data.players[i];
                html += '<tr><td>' + (i+1) + '</td>';
                html += '<td class="name">' + p.naam + '</td>';
                html += '<td>' + (p.kampioen || '?') + '</td>';
                html += '<td>' + (p.points.groep_positie + p.points.groep_winnaar + p.points.groep_tweede) + '</td>';
                html += '<td>' + p.points.beste_derdes + '</td>';
                html += '<td>' + p.points.r32 + '</td>';
                html += '<td>' + p.points.r16 + '</td>';
                html += '<td>' + p.points.qf + '</td>';
                html += '<td>' + p.points.sf + '</td>';
                html += '<td>' + (p.points.finalist + p.points.winnaar) + '</td>';
                html += '<td class="total">' + p.points.totaal + '</td></tr>';
            }
            html += '</tbody></table>';
            container.innerHTML = html;
        });
    }

    // ============ ALL PREDICTIONS ============
    function loadAllPredictions() {
        fetch('/api/predictions')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            var container = document.getElementById('all-predictions-container');
            var names = Object.keys(data);
            if (names.length === 0) { container.innerHTML = '<p style="color:#888;">Nog geen voorspellingen.</p>'; return; }
            var html = '<p style="color:#aaa;margin-bottom:12px;">' + names.length + ' voorspelling(en)</p>';
            for (var i = 0; i < names.length; i++) {
                var pred = data[names[i]];
                html += '<div class="player-detail-card"><h4>' + pred.naam + '</h4>';
                html += '<div class="info">Kampioen: <strong style="color:#ffd700;">' + (pred.knockout ? pred.knockout.finale : '?') + '</strong></div>';
                html += '<div class="info">Ingediend: ' + (pred.datum || '?') + '</div>';
                if (pred.groepsfase) {
                    html += '<div class="info">Groepswinnaars: ';
                    var groups = Object.keys(pred.groepsfase);
                    for (var g = 0; g < groups.length; g++) {
                        html += groups[g] + ':' + pred.groepsfase[groups[g]][0];
                        if (g < groups.length - 1) html += ', ';
                    }
                    html += '</div>';
                }
                html += '</div>';
            }
            container.innerHTML = html;
        });
    }

    // ============ EVENT LISTENERS ============
    document.getElementById('admin-btn-next-1').addEventListener('click', function() { adminGoToStep(2); });
    document.getElementById('admin-btn-back-2').addEventListener('click', function() { adminGoToStep(1); });
    document.getElementById('admin-btn-next-2').addEventListener('click', function() { adminGoToStep(3); });
    document.getElementById('admin-btn-back-3').addEventListener('click', function() { adminGoToStep(2); });
    document.getElementById('admin-btn-save').addEventListener('click', function() { adminSaveResults(); });

    // Init
    adminBuildGroups();
    loadAdminLeaderboard();
    loadAllPredictions();

    // Load existing results and pre-fill
    fetch('/api/admin/results')
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (!data || !data.groepsfase || Object.keys(data.groepsfase).length === 0) return;
        // Pre-fill group order
        var groups = Object.keys(data.groepsfase);
        for (var g = 0; g < groups.length; g++) {
            var group = groups[g];
            var savedOrder = data.groepsfase[group];
            var list = document.getElementById('admin-group-' + group);
            if (!list || !savedOrder) continue;
            // Reorder list items based on saved data
            for (var i = 0; i < savedOrder.length; i++) {
                var items = list.querySelectorAll('li');
                for (var j = 0; j < items.length; j++) {
                    if (items[j].getAttribute('data-team') === savedOrder[i]) {
                        list.appendChild(items[j]);
                        break;
                    }
                }
            }
            updatePositionBadges(list);
        }
    });

})();
</script>
</body>
</html>
"""


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    groepen_json = json.dumps(GROEPEN, ensure_ascii=False)
    html = HTML_TEMPLATE.replace('%GROEPEN_JSON%', groepen_json)
    return html


@app.route('/scoreboard')
def scoreboard():
    return render_template_string(SCOREBOARD_TEMPLATE)


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Onjuist wachtwoord!"
    return render_template_string(ADMIN_LOGIN_TEMPLATE, error=error)


@app.route('/admin')
@admin_required
def admin_dashboard():
    groepen_json = json.dumps(GROEPEN, ensure_ascii=False)
    html = ADMIN_TEMPLATE.replace('%GROEPEN_JSON%', groepen_json)
    return html


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))


# ============================================================
# API ROUTES
# ============================================================

@app.route('/api/submit', methods=['POST'])
def submit():
    try:
        data = request.get_json()
        naam = data.get('naam', '').strip()
        if not naam:
            return jsonify({"success": False, "error": "Naam is verplicht"})
        data['datum'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        all_predictions = load_data()
        all_predictions[naam] = data
        save_data(all_predictions)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    return jsonify(load_data())


@app.route('/api/scoreboard', methods=['GET'])
def get_scoreboard():
    """Publieke API - iedereen kan dit zien"""
    all_predictions = load_data()
    real_results = load_results()

    players = []
    for naam, pred in all_predictions.items():
        points = calculate_points(pred, real_results)
        kampioen = pred.get('knockout', {}).get('finale', '?')
        players.append({
            "naam": naam,
            "kampioen": kampioen,
            "points": points
        })

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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
