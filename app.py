#!/usr/bin/env python3
"""
WK 2026 Voorspellingstool - Web App (48 teams, 12 groepen)
Met puntensysteem, individuele resultaatpagina, en admin overzicht
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
    "groep_juiste_positie": 1,       # Per team op juiste positie in groep
    "groep_juiste_winnaar": 2,       # Juiste groepswinnaar (#1)
    "groep_juiste_tweede": 1,        # Juiste #2
    "beste_derde_juist": 2,          # Juiste beste derde
    "r32_juist": 3,                  # 1/16e finale juiste winnaar
    "r16_juist": 5,                  # 1/8e finale juiste winnaar
    "qf_juist": 7,                   # Kwartfinale juiste winnaar
    "sf_juist": 10,                  # Halve finale juiste winnaar
    "finalist_juist": 12,            # Juiste finalist
    "winnaar_juist": 15,             # Juiste wereldkampioen
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

        # Juiste groepswinnaar
        if len(real_order) > 0 and len(pred_order) > 0 and pred_order[0] == real_order[0]:
            points["groep_winnaar"] += PUNTEN["groep_juiste_winnaar"]
            points["details"].append(f"Groep {group}: juiste winnaar ({pred_order[0]}) +{PUNTEN['groep_juiste_winnaar']}pt")

        # Juiste tweede
        if len(real_order) > 1 and len(pred_order) > 1 and pred_order[1] == real_order[1]:
            points["groep_tweede"] += PUNTEN["groep_juiste_tweede"]
            points["details"].append(f"Groep {group}: juiste 2e ({pred_order[1]}) +{PUNTEN['groep_juiste_tweede']}pt")

        # Juiste positie per team
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

    # Finalisten check
    real_sf = real_knockout.get("halve_finales", {})
    pred_sf = pred_knockout.get("halve_finales", {})
    if real_sf and pred_sf:
        real_finalists = set(real_sf.values()) if isinstance(real_sf, dict) else set()
        pred_finalists = set(pred_sf.values()) if isinstance(pred_sf, dict) else set()
        correct_finalists = len(real_finalists & pred_finalists)
        points["finalist"] = correct_finalists * PUNTEN["finalist_juist"]
        if correct_finalists > 0:
            points["details"].append(f"Juiste finalisten: {correct_finalists} +{points['finalist']}pt")

    # Totaal
    points["totaal"] = (
        points["groep_positie"] + points["groep_winnaar"] + points["groep_tweede"] +
        points["beste_derdes"] + points["r32"] + points["r16"] +
        points["qf"] + points["sf"] + points["finalist"] + points["winnaar"]
    )

    return points


# ============================================================
# HTML TEMPLATES
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
        .nav-links { text-align: center; margin-bottom: 20px; }
        .nav-links a { color: #aaa; text-decoration: none; margin: 0 10px; padding: 8px 16px; border-radius: 8px; background: rgba(255,255,255,0.05); transition: all 0.3s; }
        .nav-links a:hover { color: #fff; background: rgba(255,255,255,0.15); }
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
            <a href="/mijn-resultaat">&#128202; Mijn Resultaat</a>
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
                    <button class="btn btn-primary" onclick="window.location.href='/mijn-resultaat'">Bekijk Mijn Resultaat</button>
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
            if (selectedThirds.length !== 8) {
                alert('Selecteer precies 8 nummers 3!');
                return;
            }
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
                html += '</span>';
                html += '</li>';
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
            var li = btn.closest('li');
            var dir = btn.getAttribute('data-dir');
            if (dir === 'up' && li.previousElementSibling) {
                list.insertBefore(li, li.previousElementSibling);
            } else if (dir === 'down' && li.nextElementSibling) {
                list.insertBefore(li.nextElementSibling, li);
            }
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
            if (draggedItem) {
                draggedItem.classList.remove('dragging');
                draggedItem = null;
                updatePositionBadges(list);
            }
        });
        list.addEventListener('dragover', function(e) {
            e.preventDefault();
            if (!draggedItem) return;
            var afterElement = getDragAfterElement(list, e.clientY);
            if (afterElement == null) { list.appendChild(draggedItem); }
            else { list.insertBefore(draggedItem, afterElement); }
        });
    }

    function getDragAfterElement(container, y) {
        var elements = container.querySelectorAll('li:not(.dragging)');
        var closest = null;
        var closestOffset = Number.NEGATIVE_INFINITY;
        for (var i = 0; i < elements.length; i++) {
            var box = elements[i].getBoundingClientRect();
            var offset = y - box.top - box.height / 2;
            if (offset < 0 && offset > closestOffset) {
                closestOffset = offset;
                closest = elements[i];
            }
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
            for (var i = 0; i < items.length; i++) {
                results[group].push(items[i].getAttribute('data-team'));
            }
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
            (function(grp) {
                div.addEventListener('click', function() { toggleThird(grp); });
            })(group);
            container.appendChild(div);
        }
    }

    function toggleThird(group) {
        var div = document.getElementById('third-' + group);
        var idx = selectedThirds.indexOf(group);
        if (idx >= 0) {
            selectedThirds.splice(idx, 1);
            div.classList.remove('selected');
        } else {
            if (selectedThirds.length >= 8) {
                alert('Je kunt maximaal 8 nummers 3 selecteren!');
                return;
            }
            selectedThirds.push(group);
            div.classList.add('selected');
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

        var winners = [];
        var runnersUp = [];
        var thirds = [];

        var groups = Object.keys(groupPredictions);
        for (var g = 0; g < groups.length; g++) {
            var group = groups[g];
            var teams = groupPredictions[group];
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
        div.className = 'knockout-round';
        div.id = 'round-' + roundKey;
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
        for (var t = 0; t < teamDivs.length; t++) {
            teamDivs[t].addEventListener('click', handleMatchClick);
        }
    }

    function escapeAttr(str) {
        return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function handleMatchClick(e) {
        var el = e.currentTarget;
        var roundKey = el.getAttribute('data-round');
        var matchIndex = parseInt(el.getAttribute('data-match'));
        var teamName = el.getAttribute('data-team');

        var el1 = document.getElementById(roundKey + '-' + matchIndex + '-1');
        var el2 = document.getElementById(roundKey + '-' + matchIndex + '-2');
        el1.classList.remove('selected');
        el2.classList.remove('selected');
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
        for (var j = 0; j < expectedCounts[roundKey]; j++) {
            winners.push(knockoutSelections[roundKey][j]);
        }

        var nextMatches = [];
        for (var k = 0; k < winners.length; k += 2) {
            nextMatches.push({ team1: winners[k], team2: winners[k + 1] });
        }

        renderRound(container, nextNames[roundKey], nextMatches, nextKey);
    }

    function submitPrediction() {
        var name = document.getElementById('player-name').value.trim();
        var groups = getGroupResults();

        if (!knockoutSelections.final_round || knockoutSelections.final_round[0] === undefined) {
            alert('Vul alle knock-outwedstrijden in! Selecteer een winnaar voor elke wedstrijd.');
            return;
        }

        var data = {
            naam: name,
            groepsfase: groups,
            beste_derdes: selectedThirds.map(function(g) { return { groep: g, team: groupPredictions[g][2] }; }),
            knockout: {
                ronde_van_32: knockoutSelections.r32,
                ronde_van_16: knockoutSelections.r16,
                kwartfinales: knockoutSelections.qf,
                halve_finales: knockoutSelections.sf,
                finale: knockoutSelections.final_round[0]
            }
        };

        fetch('/api/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
        .then(function(res) { return res.json(); })
        .then(function(result) {
            if (result.success) {
                document.getElementById('confirm-name').textContent = name;
                document.getElementById('confirm-champion').textContent = knockoutSelections.final_round[0];
                goToStep(5);
            } else {
                alert('Er ging iets mis: ' + result.error);
            }
        })
        .catch(function(err) {
            alert('Fout bij verzenden: ' + err.message);
        });
    }

    // Event Listeners
    document.getElementById('btn-next-1').addEventListener('click', function() { goToStep(2); });
    document.getElementById('btn-back-2').addEventListener('click', function() { goToStep(1); });
    document.getElementById('btn-next-2').addEventListener('click', function() { goToStep(3); });
    document.getElementById('btn-back-3').addEventListener('click', function() { goToStep(2); });
    document.getElementById('btn-to-knockout').addEventListener('click', function() { goToStep(4); });
    document.getElementById('btn-back-4').addEventListener('click', function() { goToStep(3); });
    document.getElementById('btn-submit').addEventListener('click', function() { submitPrediction(); });

    document.getElementById('player-name').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') { goToStep(2); }
    });
    document.getElementById('player-name').addEventListener('input', function() {
        document.getElementById('name-error').classList.remove('show');
    });

    buildGroups();
})();
</script>
</body>
</html>
"""

# ============================================================
# MIJN RESULTAAT PAGE - Speler ziet enkel eigen resultaat
# ============================================================
MY_RESULT_TEMPLATE = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mijn Resultaat - WK 2026</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh; color: #fff; padding: 20px;
        }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { text-align: center; font-size: 2em; margin-bottom: 10px; }
        .subtitle { text-align: center; color: #aaa; margin-bottom: 30px; }
        .card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px; padding: 24px; margin-bottom: 20px; backdrop-filter: blur(10px);
        }
        .card h2 { color: #e94560; margin-bottom: 16px; }
        .card h3 { color: #f0a500; margin-bottom: 12px; }
        .name-input {
            width: 100%; padding: 14px 20px; font-size: 1.1em;
            border: 2px solid rgba(255,255,255,0.2); border-radius: 10px;
            background: rgba(255,255,255,0.05); color: #fff; outline: none;
            margin-bottom: 10px;
        }
        .name-input:focus { border-color: #e94560; }
        .name-input::placeholder { color: rgba(255,255,255,0.4); }
        .btn {
            display: inline-block; padding: 14px 32px; font-size: 1.1em;
            font-weight: bold; border: none; border-radius: 10px;
            cursor: pointer; transition: all 0.3s;
        }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-primary:hover { background: #d63851; transform: translateY(-2px); }
        .btn-secondary { background: rgba(255,255,255,0.1); color: #fff; border: 1px solid rgba(255,255,255,0.2); text-decoration: none; }
        .btn-secondary:hover { background: rgba(255,255,255,0.2); }
        .btn-group { display: flex; gap: 12px; justify-content: center; margin-top: 24px; flex-wrap: wrap; }
        .points-overview { margin: 20px 0; }
        .points-row {
            display: flex; justify-content: space-between; align-items: center;
            padding: 12px 16px; margin-bottom: 8px;
            background: rgba(255,255,255,0.05); border-radius: 8px;
            border-left: 3px solid rgba(255,255,255,0.2);
        }
        .points-row.has-points { border-left-color: #2ecc71; }
        .points-row .label { color: #ccc; }
        .points-row .value { font-weight: bold; font-size: 1.2em; }
        .points-row .value.positive { color: #2ecc71; }
        .total-row {
            display: flex; justify-content: space-between; align-items: center;
            padding: 16px 20px; margin-top: 16px;
            background: rgba(233, 69, 96, 0.15); border-radius: 12px;
            border: 2px solid #e94560; font-size: 1.2em;
        }
        .total-row .value { font-size: 1.8em; color: #ffd700; font-weight: bold; }
        .champion-display { text-align: center; padding: 20px; background: rgba(255,215,0,0.1); border-radius: 12px; margin-bottom: 20px; border: 1px solid rgba(255,215,0,0.3); }
        .champion-display .trophy { font-size: 2em; }
        .champion-display .team { font-size: 1.5em; color: #ffd700; font-weight: bold; margin-top: 8px; }
        .details-list { margin-top: 12px; }
        .details-list li { color: #aaa; margin-bottom: 4px; font-size: 0.9em; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .no-result { text-align: center; padding: 40px; color: #888; }
        .no-result p { margin-bottom: 12px; }
        .ranking-badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.9em; margin-bottom: 12px; }
        .rank-1 { background: #ffd700; color: #000; }
        .rank-2 { background: #c0c0c0; color: #000; }
        .rank-3 { background: #cd7f32; color: #fff; }
        .rank-other { background: rgba(255,255,255,0.1); color: #aaa; }
        .hidden { display: none; }
        .nav-links { text-align: center; margin-bottom: 20px; }
        .nav-links a { color: #aaa; text-decoration: none; margin: 0 10px; padding: 8px 16px; border-radius: 8px; background: rgba(255,255,255,0.05); transition: all 0.3s; }
        .nav-links a:hover { color: #fff; background: rgba(255,255,255,0.15); }
    </style>
</head>
<body>
    <div class="container">
        <h1>&#128202; Mijn Resultaat</h1>
        <p class="subtitle">Bekijk je eigen score en voorspellingen</p>
        <div class="nav-links">
            <a href="/">&#9917; Voorspelling invullen</a>
            <a href="/admin">&#128272; Admin</a>
        </div>

        <div class="card" id="lookup-card">
            <h2>&#128269; Zoek je resultaat</h2>
            <p style="color: #aaa; margin-bottom: 12px;">Vul je naam in zoals je die hebt gebruikt bij het indienen:</p>
            <input type="text" class="name-input" id="lookup-name" placeholder="Jouw naam..." autocomplete="off">
            <div class="btn-group">
                <button class="btn btn-primary" id="btn-lookup" type="button">Bekijk Resultaat</button>
            </div>
        </div>

        <div class="card hidden" id="result-card">
            <div id="result-content"></div>
        </div>
    </div>

<script>
document.getElementById('btn-lookup').addEventListener('click', lookupResult);
document.getElementById('lookup-name').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') lookupResult();
});

function lookupResult() {
    var name = document.getElementById('lookup-name').value.trim();
    if (!name) { alert('Vul je naam in!'); return; }

    fetch('/api/my-result?naam=' + encodeURIComponent(name))
    .then(function(res) { return res.json(); })
    .then(function(data) {
        var resultCard = document.getElementById('result-card');
        var content = document.getElementById('result-content');

        if (!data.found) {
            content.innerHTML = '<div class="no-result"><p>&#128533; Geen voorspelling gevonden voor "<strong>' + name + '</strong>"</p><p>Controleer je naam of <a href="/" style="color: #e94560;">vul eerst je voorspelling in</a>.</p></div>';
        } else {
            var pred = data.prediction;
            var points = data.points;
            var rank = data.rank;
            var total_players = data.total_players;

            var rankClass = rank === 1 ? 'rank-1' : rank === 2 ? 'rank-2' : rank === 3 ? 'rank-3' : 'rank-other';
            var rankText = rank ? '#' + rank + ' van ' + total_players + ' spelers' : 'Nog geen ranking';

            var html = '<span class="ranking-badge ' + rankClass + '">' + rankText + '</span>';
            html += '<div class="champion-display"><div class="trophy">&#127942;</div><div class="team">' + (pred.knockout ? pred.knockout.finale : '?') + '</div><div style="color:#aaa;font-size:0.9em;margin-top:4px;">Jouw voorspelde kampioen</div></div>';

            html += '<h3>&#127919; Puntenoverzicht</h3>';
            html += '<div class="points-overview">';

            var categories = [
                {label: "Groepsfase - juiste posities", value: points.groep_positie, pts: "x1pt"},
                {label: "Groepswinnaar juist", value: points.groep_winnaar, pts: "x2pt"},
                {label: "Juiste 2e in groep", value: points.groep_tweede, pts: "x1pt"},
                {label: "Beste derdes juist", value: points.beste_derdes, pts: "x2pt"},
                {label: "1/16e finale", value: points.r32, pts: "x3pt"},
                {label: "1/8e finale", value: points.r16, pts: "x5pt"},
                {label: "Kwartfinale", value: points.qf, pts: "x7pt"},
                {label: "Halve finale", value: points.sf, pts: "x10pt"},
                {label: "Juiste finalist", value: points.finalist, pts: "x12pt"},
                {label: "Juiste kampioen", value: points.winnaar, pts: "x15pt"}
            ];

            for (var i = 0; i < categories.length; i++) {
                var cat = categories[i];
                var hasPoints = cat.value > 0;
                html += '<div class="points-row' + (hasPoints ? ' has-points' : '') + '">';
                html += '<span class="label">' + cat.label + ' <small style="color:#666">(' + cat.pts + ')</small></span>';
                html += '<span class="value' + (hasPoints ? ' positive' : '') + '">' + cat.value + ' pt</span>';
                html += '</div>';
            }

            html += '</div>';
            html += '<div class="total-row"><span>TOTAAL</span><span class="value">' + points.totaal + ' pt</span></div>';

            if (points.details && points.details.length > 0) {
                html += '<h3 style="margin-top:20px;">&#128221; Details</h3>';
                html += '<ul class="details-list">';
                for (var d = 0; d < points.details.length; d++) {
                    html += '<li>' + points.details[d] + '</li>';
                }
                html += '</ul>';
            }

            if (!data.results_available) {
                html += '<p style="color:#f0a500;margin-top:20px;text-align:center;">&#9888; De admin heeft nog geen (volledige) echte resultaten ingevuld. Punten worden bijgewerkt naarmate het toernooi vordert.</p>';
            }
        }
        content.innerHTML = html;
        resultCard.classList.remove('hidden');
    })
    .catch(function(err) {
        alert('Fout: ' + err.message);
    });
}
</script>
</body>
</html>
"""

# ============================================================
# ADMIN LOGIN PAGE
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
            background: rgba(255,255,255,0.05); color: #fff; outline: none;
            margin-bottom: 16px;
        }
        .name-input:focus { border-color: #e94560; }
        .name-input::placeholder { color: rgba(255,255,255,0.4); }
        .btn {
            width: 100%; padding: 14px; font-size: 1.1em;
            font-weight: bold; border: none; border-radius: 10px;
            cursor: pointer; background: #e94560; color: #fff;
        }
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
        <div class="back-link"><a href="/">&larr; Terug naar voorspellingen</a></div>
    </div>
</body>
</html>
"""

# ============================================================
# ADMIN DASHBOARD - Overzicht alle spelers + punten + echte resultaten invullen
# ============================================================
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard - WK 2026</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh; color: #fff; padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
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
        .card h3 { color: #f0a500; margin-bottom: 12px; }
        .tabs { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab {
            padding: 10px 20px; border-radius: 8px; cursor: pointer;
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            transition: all 0.3s; color: #aaa;
        }
        .tab:hover { background: rgba(255,255,255,0.1); color: #fff; }
        .tab.active { background: #e94560; color: #fff; border-color: #e94560; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .leaderboard { width: 100%; border-collapse: collapse; margin-top: 12px; }
        .leaderboard th {
            background: rgba(233, 69, 96, 0.2); padding: 12px 16px;
            text-align: left; border-bottom: 2px solid rgba(255,255,255,0.1);
            font-size: 0.9em;
        }
        .leaderboard td {
            padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .leaderboard tr:hover { background: rgba(255,255,255,0.05); }
        .leaderboard .rank { font-weight: bold; color: #ffd700; }
        .leaderboard .total { font-weight: bold; font-size: 1.2em; color: #2ecc71; }
        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; margin-bottom: 6px; color: #ccc; font-size: 0.9em; }
        .form-group input, .form-group select {
            width: 100%; padding: 10px 14px; font-size: 1em;
            border: 1px solid rgba(255,255,255,0.2); border-radius: 8px;
            background: rgba(255,255,255,0.05); color: #fff; outline: none;
        }
        .form-group input:focus { border-color: #e94560; }
        .btn {
            display: inline-block; padding: 12px 24px; font-size: 1em;
            font-weight: bold; border: none; border-radius: 8px;
            cursor: pointer; transition: all 0.3s;
        }
        .btn-primary { background: #e94560; color: #fff; }
        .btn-primary:hover { background: #d63851; }
        .btn-success { background: #2ecc71; color: #fff; }
        .btn-success:hover { background: #27ae60; }
        .btn-danger { background: #e74c3c; color: #fff; }
        .btn-danger:hover { background: #c0392b; }
        .btn-group { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 16px; }
        .group-input-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
        .group-input-card {
            background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px; padding: 16px;
        }
        .group-input-card h4 { color: #f0a500; margin-bottom: 10px; }
        .group-input-card .team-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .group-input-card .team-row span { min-width: 24px; font-weight: bold; color: #888; }
        .group-input-card .team-row input { flex: 1; padding: 6px 10px; font-size: 0.9em;
            border: 1px solid rgba(255,255,255,0.15); border-radius: 6px;
            background: rgba(255,255,255,0.05); color: #fff; outline: none; }
        .knockout-input { margin-bottom: 16px; }
        .knockout-input h4 { color: #f0a500; margin-bottom: 8px; }
        .knockout-input .match-row {
            display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
        }
        .knockout-input .match-row label { min-width: 100px; color: #888; font-size: 0.85em; }
        .knockout-input .match-row input {
            flex: 1; padding: 6px 10px; font-size: 0.9em;
            border: 1px solid rgba(255,255,255,0.15); border-radius: 6px;
            background: rgba(255,255,255,0.05); color: #fff; outline: none;
        }
        .status-msg { padding: 12px; border-radius: 8px; margin-top: 12px; display: none; }
        .status-msg.success { display: block; background: rgba(46, 204, 113, 0.2); border: 1px solid #2ecc71; }
        .status-msg.error { display: block; background: rgba(231, 76, 60, 0.2); border: 1px solid #e74c3c; }
        .punten-info { background: rgba(255,215,0,0.1); border: 1px solid rgba(255,215,0,0.3); border-radius: 12px; padding: 16px; margin-bottom: 20px; }
        .punten-info h3 { color: #ffd700; margin-bottom: 8px; }
        .punten-info ul { list-style: none; }
        .punten-info li { padding: 4px 0; color: #ccc; font-size: 0.9em; }
        .punten-info li strong { color: #fff; }
        .player-details { margin-top: 12px; }
        .player-detail-card {
            background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px; padding: 16px; margin-bottom: 12px;
        }
        .player-detail-card h4 { color: #e94560; margin-bottom: 8px; }
        .player-detail-card .info { color: #aaa; font-size: 0.85em; margin-bottom: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>&#128272; Admin Dashboard</h1>
        <p class="subtitle">Beheer echte resultaten en bekijk alle voorspellingen</p>
        <div class="nav-links">
            <a href="/">&#9917; Voorspelling invullen</a>
            <a href="/mijn-resultaat">&#128202; Mijn Resultaat</a>
            <a href="/admin/logout">&#128682; Uitloggen</a>
        </div>

        <div class="tabs">
            <div class="tab active" data-tab="leaderboard">&#127942; Rangschikking</div>
            <div class="tab" data-tab="results-input">&#9989; Echte Resultaten</div>
            <div class="tab" data-tab="all-predictions">&#128203; Alle Voorspellingen</div>
            <div class="tab" data-tab="punten-info">&#128218; Puntensysteem</div>
        </div>

        <!-- LEADERBOARD TAB -->
        <div class="tab-content active" id="tab-leaderboard">
            <div class="card">
                <h2>&#127942; Rangschikking</h2>
                <div id="leaderboard-container">
                    <p style="color:#888;">Laden...</p>
                </div>
            </div>
        </div>

        <!-- RESULTS INPUT TAB -->
        <div class="tab-content" id="tab-results-input">
            <div class="card">
                <h2>&#9989; Echte Resultaten Invullen</h2>
                <p style="color:#aaa;margin-bottom:16px;">Vul hier de echte resultaten in naarmate het toernooi vordert. De punten worden automatisch berekend.</p>

                <h3>Groepsfase - Eindstanden</h3>
                <p style="color:#888;font-size:0.85em;margin-bottom:12px;">Vul per groep de eindrangschikking in (1e, 2e, 3e, 4e)</p>
                <div class="group-input-grid" id="group-results-input"></div>

                <h3 style="margin-top:24px;">Beste Derdes</h3>
                <p style="color:#888;font-size:0.85em;margin-bottom:12px;">Vul de 8 beste nummers 3 in (team naam)</p>
                <div id="thirds-results-input" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;"></div>

                <h3 style="margin-top:24px;">Knock-out Resultaten</h3>
                <div id="knockout-results-input"></div>

                <div class="btn-group">
                    <button class="btn btn-success" id="btn-save-results" type="button">&#128190; Resultaten Opslaan</button>
                </div>
                <div class="status-msg" id="save-status"></div>
            </div>
        </div>

        <!-- ALL PREDICTIONS TAB -->
        <div class="tab-content" id="tab-all-predictions">
            <div class="card">
                <h2>&#128203; Alle Voorspellingen</h2>
                <div id="all-predictions-container">
                    <p style="color:#888;">Laden...</p>
                </div>
            </div>
        </div>

        <!-- PUNTEN INFO TAB -->
        <div class="tab-content" id="tab-punten-info">
            <div class="card">
                <div class="punten-info">
                    <h3>&#128218; Puntensysteem</h3>
                    <ul>
                        <li><strong>1 punt</strong> - Per team op juiste positie in groep</li>
                        <li><strong>2 punten</strong> - Juiste groepswinnaar (#1)</li>
                        <li><strong>1 punt</strong> - Juiste #2 in de groep</li>
                        <li><strong>2 punten</strong> - Per juiste beste derde</li>
                        <li><strong>3 punten</strong> - 1/16e finale: juist team door</li>
                        <li><strong>5 punten</strong> - 1/8e finale: juist team door</li>
                        <li><strong>7 punten</strong> - Kwartfinale: juist team door</li>
                        <li><strong>10 punten</strong> - Halve finale: juist team door</li>
                        <li><strong>12 punten</strong> - Juiste finalist</li>
                        <li><strong>15 punten</strong> - Juiste wereldkampioen</li>
                    </ul>
                </div>
                <h3>Maximaal Haalbare Punten</h3>
                <p style="color:#aaa;margin-top:8px;">
                    Groepsfase posities: 48 teams x 1pt = <strong>48pt</strong><br>
                    Groepswinnaars: 12 x 2pt = <strong>24pt</strong><br>
                    Juiste 2e: 12 x 1pt = <strong>12pt</strong><br>
                    Beste derdes: 8 x 2pt = <strong>16pt</strong><br>
                    1/16e finale: 16 x 3pt = <strong>48pt</strong><br>
                    1/8e finale: 8 x 5pt = <strong>40pt</strong><br>
                    Kwartfinale: 4 x 7pt = <strong>28pt</strong><br>
                    Halve finale: 2 x 10pt = <strong>20pt</strong><br>
                    Finalisten: 2 x 12pt = <strong>24pt</strong><br>
                    Kampioen: 1 x 15pt = <strong>15pt</strong><br><br>
                    <strong style="color:#ffd700;font-size:1.2em;">TOTAAL MAXIMUM: 275 punten</strong>
                </p>
            </div>
        </div>
    </div>

<script>
var GROEPEN = %GROEPEN_JSON%;

// Tab navigation
document.querySelectorAll('.tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
        document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
        document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
        tab.classList.add('active');
        document.getElementById('tab-' + tab.getAttribute('data-tab')).classList.add('active');
    });
});

// Load leaderboard
function loadLeaderboard() {
    fetch('/api/admin/leaderboard')
    .then(function(res) { return res.json(); })
    .then(function(data) {
        var container = document.getElementById('leaderboard-container');
        if (!data.players || data.players.length === 0) {
            container.innerHTML = '<p style="color:#888;">Nog geen voorspellingen ingediend.</p>';
            return;
        }
        var html = '<table class="leaderboard"><thead><tr>';
        html += '<th>#</th><th>Speler</th><th>Kampioen</th>';
        html += '<th>Groep</th><th>R32</th><th>R16</th><th>KF</th><th>HF</th><th>Fin</th><th>Win</th>';
        html += '<th>TOTAAL</th></tr></thead><tbody>';

        for (var i = 0; i < data.players.length; i++) {
            var p = data.players[i];
            html += '<tr>';
            html += '<td class="rank">' + (i+1) + '</td>';
            html += '<td>' + p.naam + '</td>';
            html += '<td>' + (p.kampioen || '?') + '</td>';
            html += '<td>' + (p.points.groep_positie + p.points.groep_winnaar + p.points.groep_tweede) + '</td>';
            html += '<td>' + p.points.r32 + '</td>';
            html += '<td>' + p.points.r16 + '</td>';
            html += '<td>' + p.points.qf + '</td>';
            html += '<td>' + p.points.sf + '</td>';
            html += '<td>' + p.points.finalist + '</td>';
            html += '<td>' + p.points.winnaar + '</td>';
            html += '<td class="total">' + p.points.totaal + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table>';
        container.innerHTML = html;
    });
}

// Load all predictions
function loadAllPredictions() {
    fetch('/api/predictions')
    .then(function(res) { return res.json(); })
    .then(function(data) {
        var container = document.getElementById('all-predictions-container');
        var names = Object.keys(data);
        if (names.length === 0) {
            container.innerHTML = '<p style="color:#888;">Nog geen voorspellingen.</p>';
            return;
        }
        var html = '<p style="color:#aaa;margin-bottom:12px;">' + names.length + ' voorspelling(en)</p>';
        html += '<div class="player-details">';
        for (var i = 0; i < names.length; i++) {
            var pred = data[names[i]];
            html += '<div class="player-detail-card">';
            html += '<h4>' + pred.naam + '</h4>';
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
        html += '</div>';
        container.innerHTML = html;
    });
}

// Build results input form
function buildResultsForm() {
    // Groups
    var groupContainer = document.getElementById('group-results-input');
    var groupHtml = '';
    var groups = Object.keys(GROEPEN);
    for (var g = 0; g < groups.length; g++) {
        var group = groups[g];
        groupHtml += '<div class="group-input-card"><h4>Groep ' + group + '</h4>';
        for (var pos = 1; pos <= 4; pos++) {
            groupHtml += '<div class="team-row"><span>' + pos + '.</span>';
            groupHtml += '<input type="text" id="real-group-' + group + '-' + pos + '" placeholder="' + pos + 'e plaats..."></div>';
        }
        groupHtml += '</div>';
    }
    groupContainer.innerHTML = groupHtml;

    // Best thirds
    var thirdsContainer = document.getElementById('thirds-results-input');
    var thirdsHtml = '';
    for (var t = 1; t <= 8; t++) {
        thirdsHtml += '<div class="form-group"><label>Beste #3 nr.' + t + '</label>';
        thirdsHtml += '<input type="text" id="real-third-' + t + '" placeholder="Team naam..."></div>';
    }
    thirdsContainer.innerHTML = thirdsHtml;

    // Knockout
    var knockoutContainer = document.getElementById('knockout-results-input');
    var knockoutHtml = '';
    var rounds = [
        {key: 'r32', label: '1/16e finale (Ronde van 32)', count: 16},
        {key: 'r16', label: '1/8e finale (Ronde van 16)', count: 8},
        {key: 'qf', label: 'Kwartfinale', count: 4},
        {key: 'sf', label: 'Halve finale', count: 2},
        {key: 'finale', label: 'Finale', count: 1}
    ];
    for (var r = 0; r < rounds.length; r++) {
        var round = rounds[r];
        knockoutHtml += '<div class="knockout-input"><h4>' + round.label + '</h4>';
        for (var m = 0; m < round.count; m++) {
            knockoutHtml += '<div class="match-row"><label>Winnaar ' + (m+1) + ':</label>';
            knockoutHtml += '<input type="text" id="real-' + round.key + '-' + m + '" placeholder="Winnaar..."></div>';
        }
        knockoutHtml += '</div>';
    }
    knockoutContainer.innerHTML = knockoutHtml;

    // Load existing results
    loadExistingResults();
}

function loadExistingResults() {
    fetch('/api/admin/results')
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (!data || Object.keys(data).length === 0) return;

        // Fill groups
        var groups = data.groepsfase || {};
        for (var group in groups) {
            var teams = groups[group];
            for (var i = 0; i < teams.length; i++) {
                var input = document.getElementById('real-group-' + group + '-' + (i+1));
                if (input) input.value = teams[i];
            }
        }

        // Fill thirds
        var thirds = data.beste_derdes || [];
        for (var t = 0; t < thirds.length; t++) {
            var input = document.getElementById('real-third-' + (t+1));
            if (input) {
                input.value = typeof thirds[t] === 'object' ? thirds[t].team : thirds[t];
            }
        }

        // Fill knockout
        var knockout = data.knockout || {};
        var roundKeys = ['ronde_van_32', 'ronde_van_16', 'kwartfinales', 'halve_finales'];
        var inputKeys = ['r32', 'r16', 'qf', 'sf'];
        for (var r = 0; r < roundKeys.length; r++) {
            var roundData = knockout[roundKeys[r]] || {};
            for (var match in roundData) {
                var input = document.getElementById('real-' + inputKeys[r] + '-' + match);
                if (input) input.value = roundData[match];
            }
        }

        // Finale
        if (knockout.finale) {
            var finaleInput = document.getElementById('real-finale-0');
            if (finaleInput) finaleInput.value = knockout.finale;
        }
    });
}

function saveResults() {
    var results = { groepsfase: {}, beste_derdes: [], knockout: {} };

    // Groups
    var groups = Object.keys(GROEPEN);
    for (var g = 0; g < groups.length; g++) {
        var group = groups[g];
        var teams = [];
        for (var pos = 1; pos <= 4; pos++) {
            var input = document.getElementById('real-group-' + group + '-' + pos);
            var val = input ? input.value.trim() : '';
            if (val) teams.push(val);
        }
        if (teams.length > 0) results.groepsfase[group] = teams;
    }

    // Thirds
    for (var t = 1; t <= 8; t++) {
        var input = document.getElementById('real-third-' + t);
        var val = input ? input.value.trim() : '';
        if (val) results.beste_derdes.push({team: val});
    }

    // Knockout
    var rounds = [
        {inputKey: 'r32', dataKey: 'ronde_van_32', count: 16},
        {inputKey: 'r16', dataKey: 'ronde_van_16', count: 8},
        {inputKey: 'qf', dataKey: 'kwartfinales', count: 4},
        {inputKey: 'sf', dataKey: 'halve_finales', count: 2}
    ];
    for (var r = 0; r < rounds.length; r++) {
        var round = rounds[r];
        results.knockout[round.dataKey] = {};
        for (var m = 0; m < round.count; m++) {
            var input = document.getElementById('real-' + round.inputKey + '-' + m);
            var val = input ? input.value.trim() : '';
            if (val) results.knockout[round.dataKey][m] = val;
        }
    }

    // Finale
    var finaleInput = document.getElementById('real-finale-0');
    results.knockout.finale = finaleInput ? finaleInput.value.trim() : '';

    fetch('/api/admin/results', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(results)
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        var status = document.getElementById('save-status');
        if (data.success) {
            status.className = 'status-msg success';
            status.textContent = '\u2705 Resultaten succesvol opgeslagen! Punten worden automatisch herberekend.';
            loadLeaderboard();
        } else {
            status.className = 'status-msg error';
            status.textContent = '\u274c Fout: ' + data.error;
        }
    })
    .catch(function(err) {
        var status = document.getElementById('save-status');
        status.className = 'status-msg error';
        status.textContent = '\u274c Fout bij opslaan: ' + err.message;
    });
}

document.getElementById('btn-save-results').addEventListener('click', saveResults);

// Init
loadLeaderboard();
loadAllPredictions();
buildResultsForm();
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


@app.route('/mijn-resultaat')
def mijn_resultaat():
    return render_template_string(MY_RESULT_TEMPLATE)


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


@app.route('/api/my-result', methods=['GET'])
def get_my_result():
    """Speler kan ENKEL eigen resultaat zien"""
    naam = request.args.get('naam', '').strip()
    if not naam:
        return jsonify({"found": False})

    all_predictions = load_data()
    real_results = load_results()

    # Zoek case-insensitive
    found_key = None
    for key in all_predictions:
        if key.lower() == naam.lower():
            found_key = key
            break

    if not found_key:
        return jsonify({"found": False})

    prediction = all_predictions[found_key]
    points = calculate_points(prediction, real_results)

    # Bereken ranking
    all_points = []
    for key, pred in all_predictions.items():
        p = calculate_points(pred, real_results)
        all_points.append({"naam": key, "totaal": p["totaal"]})

    all_points.sort(key=lambda x: x["totaal"], reverse=True)
    rank = 1
    for i, item in enumerate(all_points):
        if item["naam"] == found_key:
            rank = i + 1
            break

    return jsonify({
        "found": True,
        "prediction": prediction,
        "points": points,
        "rank": rank,
        "total_players": len(all_points),
        "results_available": bool(real_results)
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


@app.route('/api/admin/leaderboard', methods=['GET'])
def admin_leaderboard():
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
    return jsonify({"players": players})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
