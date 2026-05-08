#!/usr/bin/env python3
"""
WK 2026 Voorspellingstool - Web App (48 teams, 12 groepen)
"""

from flask import Flask, render_template_string, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)

DATA_FILE = "voorspellingen.json"

# WK 2026 Groepen
GROEPEN = {
    "A": ["Mexico", "Zuid-Afrika", "Zuid-Korea", "Winnaar UEFA playoff D"],
    "B": ["Canada", "Winnaar UEFA playoff A", "Qatar", "Zwitserland"],
    "C": ["Brazilië", "Marokko", "Haïti", "Schotland"],
    "D": ["Verenigde Staten", "Paraguay", "Australië", "Winnaar UEFA playoff C"],
    "E": ["Duitsland", "Curaçao", "Ivoorkust", "Ecuador"],
    "F": ["Nederland", "Japan", "Winnaar UEFA playoff B", "Tunesië"],
    "G": ["België", "Egypte", "Iran", "Nieuw-Zeeland"],
    "H": ["Spanje", "Kaapverdië", "Saudi-Arabië", "Uruguay"],
    "I": ["Frankrijk", "Senegal", "Winnaar IC playoff 2", "Noorwegen"],
    "J": ["Argentinië", "Algerije", "Oostenrijk", "Jordanië"],
    "K": ["Portugal", "Winnaar IC playoff 1", "Oezbekistan", "Colombia"],
    "L": ["Engeland", "Kroatië", "Ghana", "Panama"],
}

# WK 2026 Knock-out structuur (FIFA officieel voor 48 teams):
# 1/16 finales: top 2 per groep + 8 beste nummers 3 = 32 teams
# De bracket voor de 1/16 finales (vereenvoudigd):
# We laten gebruikers kiezen welke #3s doorgaan en dan de hele bracket invullen


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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
        }
        .name-input:focus { border-color: #e94560; }
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
        }
        .sortable-list li:hover { background: rgba(255,255,255,0.15); }
        .sortable-list li.dragging { opacity: 0.5; background: rgba(233, 69, 96, 0.3); }
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
        .third-place-option.disabled { opacity: 0.4; cursor: not-allowed; }
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
            <div class="btn-group">
                <button class="btn btn-primary" onclick="goToStep(2)">Volgende &#8594;</button>
            </div>
        </div>

        <!-- STEP 2: Group Stage -->
        <div id="step-2" class="card hidden">
            <h2>&#128202; Groepsfase</h2>
            <p class="drag-hint">Sleep de landen in de juiste volgorde (1 = groepswinnaar, 4 = laatste)</p>
            <div class="group-grid" id="groups-container"></div>
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="goToStep(1)">&#8592; Terug</button>
                <button class="btn btn-primary" onclick="goToStep(3)">Volgende &#8594;</button>
            </div>
        </div>

        <!-- STEP 3: Best Third Places -->
        <div id="step-3" class="card hidden">
            <h2>&#127941; Beste Nummers 3</h2>
            <p class="drag-hint">Selecteer welke 8 nummers 3 doorgaan naar de knock-outfase</p>
            <p class="counter" id="third-counter">Geselecteerd: 0 / 8</p>
            <div class="third-place-grid" id="third-place-container"></div>
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="goToStep(2)">&#8592; Terug</button>
                <button class="btn btn-primary" id="btn-to-knockout" onclick="goToStep(4)" disabled>Volgende &#8594;</button>
            </div>
        </div>

        <!-- STEP 4: Knockout -->
        <div id="step-4" class="card hidden">
            <h2>&#127942; Knock-outfase</h2>
            <p class="drag-hint">Klik op het team dat je denkt dat wint</p>
            <div id="knockout-container"></div>
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="goToStep(3)">&#8592; Terug</button>
                <button class="btn btn-primary" onclick="submitPrediction()">&#9989; Voorspelling Indienen</button>
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
                    <button class="btn btn-primary" onclick="window.location.href='/resultaten'">Bekijk Alle Voorspellingen</button>
                </div>
            </div>
        </div>
    </div>

<script>
const GROEPEN = %GROEPEN_JSON%;

let currentStep = 1;
let groupPredictions = {};
let selectedThirds = [];
let knockoutSelections = {};

// ============ NAVIGATION ============
function goToStep(step) {
    if (step === 2 && !document.getElementById('player-name').value.trim()) {
        alert('Vul je naam in!');
        return;
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
    for (let i = 1; i <= 5; i++) {
        const ind = document.getElementById('step-ind-' + i);
        ind.classList.remove('active', 'done');
        if (i < step) ind.classList.add('done');
        if (i === step) ind.classList.add('active');
    }
    currentStep = step;
    window.scrollTo(0, 0);
}

// ============ GROUP STAGE ============
function buildGroups() {
    const container = document.getElementById('groups-container');
    container.innerHTML = '';
    for (const [group, teams] of Object.entries(GROEPEN)) {
        const card = document.createElement('div');
        card.className = 'group-card';
        let html = '<h3>Groep ' + group + '</h3>';
        html += '<ul class="sortable-list" id="group-' + group + '">';
        for (let i = 0; i < teams.length; i++) {
            html += '<li draggable="true" data-team="' + teams[i] + '">';
            html += '<span class="position-badge pos-' + (i+1) + '">' + (i+1) + '</span>';
            html += '<span>' + teams[i] + '</span></li>';
        }
        html += '</ul>';
        card.innerHTML = html;
        container.appendChild(card);
        initSortable(card.querySelector('.sortable-list'));
    }
}

function initSortable(list) {
    let draggedItem = null;
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
        const afterElement = getDragAfterElement(list, e.clientY);
        if (draggedItem) {
            if (afterElement == null) { list.appendChild(draggedItem); }
            else { list.insertBefore(draggedItem, afterElement); }
        }
    });
    let touchDragItem = null;
    list.addEventListener('touchstart', function(e) {
        touchDragItem = e.target.closest('li');
        if (touchDragItem) touchDragItem.classList.add('dragging');
    });
    list.addEventListener('touchmove', function(e) {
        e.preventDefault();
        if (!touchDragItem) return;
        const touchY = e.touches[0].clientY;
        const afterElement = getDragAfterElement(list, touchY);
        if (afterElement == null) { list.appendChild(touchDragItem); }
        else { list.insertBefore(touchDragItem, afterElement); }
    });
    list.addEventListener('touchend', function(e) {
        if (touchDragItem) {
            touchDragItem.classList.remove('dragging');
            touchDragItem = null;
            updatePositionBadges(list);
        }
    });
}

function getDragAfterElement(container, y) {
    const elements = Array.from(container.querySelectorAll('li:not(.dragging)'));
    let closest = { offset: Number.NEGATIVE_INFINITY, element: null };
    for (let i = 0; i < elements.length; i++) {
        const box = elements[i].getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
            closest = { offset: offset, element: elements[i] };
        }
    }
    return closest.element;
}

function updatePositionBadges(list) {
    const items = list.querySelectorAll('li');
    for (let i = 0; i < items.length; i++) {
        const badge = items[i].querySelector('.position-badge');
        badge.className = 'position-badge pos-' + (i + 1);
        badge.textContent = i + 1;
    }
}

function getGroupResults() {
    const results = {};
    for (const group of Object.keys(GROEPEN)) {
        const list = document.getElementById('group-' + group);
        const items = list.querySelectorAll('li');
        results[group] = [];
        for (let i = 0; i < items.length; i++) {
            results[group].push(items[i].getAttribute('data-team'));
        }
    }
    return results;
}

// ============ BEST THIRD PLACES ============
function buildThirdPlaces() {
    const container = document.getElementById('third-place-container');
    container.innerHTML = '';
    selectedThirds = [];
    updateThirdCounter();

    for (const [group, teams] of Object.entries(groupPredictions)) {
        const thirdPlace = teams[2]; // Index 2 = nummer 3
        const div = document.createElement('div');
        div.className = 'third-place-option';
        div.id = 'third-' + group;
        div.textContent = thirdPlace + ' (Groep ' + group + ')';
        div.setAttribute('data-group', group);
        div.setAttribute('data-team', thirdPlace);
        div.onclick = function() { toggleThird(group); };
        container.appendChild(div);
    }
}

function toggleThird(group) {
    const div = document.getElementById('third-' + group);
    const idx = selectedThirds.indexOf(group);

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

// ============ KNOCKOUT STAGE ============
function buildKnockout() {
    const container = document.getElementById('knockout-container');
    container.innerHTML = '';
    knockoutSelections = { r32: {}, r16: {}, qf: {}, sf: {}, final: {} };

    // Collect the 32 teams:
    // 12 group winners (pos 1) + 12 runners-up (pos 2) + 8 best thirds = 32
    const winners = [];
    const runnersUp = [];
    const thirds = [];

    for (const [group, teams] of Object.entries(groupPredictions)) {
        winners.push({ team: teams[0], group: group, pos: 1 });
        runnersUp.push({ team: teams[1], group: group, pos: 2 });
    }
    for (const group of selectedThirds) {
        thirds.push({ team: groupPredictions[group][2], group: group, pos: 3 });
    }

    // WK 2026 bracket (vereenvoudigde versie):
    // 1/16 finales (round of 32): 16 wedstrijden
    // Groepswinnaars vs Beste #3 of Runners-up vs Runners-up
    // Officieel FIFA bracket (vereenvoudigd):
    const r32Matches = [
        { team1: winners[0].team, team2: thirds.length > 0 ? thirds[0].team : 'TBD' },   // 1A vs 3rd
        { team1: winners[1].team, team2: thirds.length > 1 ? thirds[1].team : 'TBD' },   // 1B vs 3rd
        { team1: winners[2].team, team2: thirds.length > 2 ? thirds[2].team : 'TBD' },   // 1C vs 3rd
        { team1: winners[3].team, team2: thirds.length > 3 ? thirds[3].team : 'TBD' },   // 1D vs 3rd
        { team1: winners[4].team, team2: thirds.length > 4 ? thirds[4].team : 'TBD' },   // 1E vs 3rd
        { team1: winners[5].team, team2: thirds.length > 5 ? thirds[5].team : 'TBD' },   // 1F vs 3rd
        { team1: winners[6].team, team2: thirds.length > 6 ? thirds[6].team : 'TBD' },   // 1G vs 3rd
        { team1: winners[7].team, team2: thirds.length > 7 ? thirds[7].team : 'TBD' },   // 1H vs 3rd
        { team1: runnersUp[0].team, team2: runnersUp[1].team },   // 2A vs 2B
        { team1: runnersUp[2].team, team2: runnersUp[3].team },   // 2C vs 2D
        { team1: runnersUp[4].team, team2: runnersUp[5].team },   // 2E vs 2F
        { team1: runnersUp[6].team, team2: runnersUp[7].team },   // 2G vs 2H
        { team1: winners[8].team, team2: runnersUp[8].team },     // 1I vs 2I (alt)
        { team1: winners[9].team, team2: runnersUp[9].team },     // 1J vs 2J (alt)
        { team1: winners[10].team, team2: runnersUp[10].team },   // 1K vs 2K (alt)
        { team1: winners[11].team, team2: runnersUp[11].team },   // 1L vs 2L (alt)
    ];

    renderRound(container, '1/16 Finales (Ronde van 32)', r32Matches, 'r32');
}

function renderRound(container, title, matches, roundKey) {
    const div = document.createElement('div');
    div.className = 'knockout-round';
    div.id = 'round-' + roundKey;
    let html = '<h3>' + title + '</h3>';
    for (let i = 0; i < matches.length; i++) {
        const m = matches[i];
        const t1safe = m.team1.replace(/'/g, "\\'");
        const t2safe = m.team2.replace(/'/g, "\\'");
        html += '<div class="match-card">';
        html += '<div class="match-team" id="' + roundKey + '-' + i + '-1" onclick="selectWinner(\'' + roundKey + '\', ' + i + ', 1, \'' + t1safe + '\')">' + m.team1 + '</div>';
        html += '<span class="match-vs">VS</span>';
        html += '<div class="match-team" id="' + roundKey + '-' + i + '-2" onclick="selectWinner(\'' + roundKey + '\', ' + i + ', 2, \'' + t2safe + '\')">' + m.team2 + '</div>';
        html += '</div>';
    }
    div.innerHTML = html;
    container.appendChild(div);
}

function selectWinner(roundKey, matchIndex, teamNum, teamName) {
    const el1 = document.getElementById(roundKey + '-' + matchIndex + '-1');
    const el2 = document.getElementById(roundKey + '-' + matchIndex + '-2');
    el1.classList.remove('selected');
    el2.classList.remove('selected');
    document.getElementById(roundKey + '-' + matchIndex + '-' + teamNum).classList.add('selected');
    knockoutSelections[roundKey][matchIndex] = teamName;
    buildNextRound(roundKey);
}

function buildNextRound(roundKey) {
    const container = document.getElementById('knockout-container');
    const expectedCounts = { r32: 16, r16: 8, qf: 4, sf: 2, final: 1 };
    const nextRounds = { r32: 'r16', r16: 'qf', qf: 'sf', sf: 'final' };
    const nextNames = { r32: '1/8 Finales (Ronde van 16)', r16: 'Kwartfinales', qf: 'Halve Finales', sf: '&#127942; FINALE' };

    const count = Object.keys(knockoutSelections[roundKey]).length;
    if (count < expectedCounts[roundKey]) return;

    const nextKey = nextRounds[roundKey];
    if (!nextKey) return;

    // Remove existing next rounds
    const order = ['r16', 'qf', 'sf', 'final'];
    const startIdx = order.indexOf(nextKey);
    for (let i = startIdx; i < order.length; i++) {
        removeRound(order[i]);
        knockoutSelections[order[i]] = {};
    }

    const winners = getWinnersArray(roundKey, expectedCounts[roundKey]);
    const nextMatches = [];
    for (let i = 0; i < winners.length; i += 2) {
        nextMatches.push({ team1: winners[i], team2: winners[i + 1] });
    }

    renderRound(container, nextNames[roundKey], nextMatches, nextKey);
}

function removeRound(roundKey) {
    const el = document.getElementById('round-' + roundKey);
    if (el) el.remove();
}

function getWinnersArray(roundKey, count) {
    const winners = [];
    for (let i = 0; i < count; i++) {
        winners.push(knockoutSelections[roundKey][i]);
    }
    return winners;
}

// ============ SUBMIT ============
function submitPrediction() {
    const name = document.getElementById('player-name').value.trim();
    const groups = getGroupResults();

    if (!knockoutSelections.final || knockoutSelections.final[0] === undefined) {
        alert('Vul alle knock-outwedstrijden in! Selecteer een winnaar voor elke wedstrijd.');
        return;
    }

    const data = {
        naam: name,
        groepsfase: groups,
        beste_derdes: selectedThirds.map(function(g) { return { groep: g, team: groupPredictions[g][2] }; }),
        knockout: {
            ronde_van_32: knockoutSelections.r32,
            ronde_van_16: knockoutSelections.r16,
            kwartfinales: knockoutSelections.qf,
            halve_finales: knockoutSelections.sf,
            finale: knockoutSelections.final[0]
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
            document.getElementById('confirm-champion').textContent = knockoutSelections.final[0];
            goToStep(5);
        } else {
            alert('Er ging iets mis: ' + result.error);
        }
    })
    .catch(function(err) {
        alert('Fout bij verzenden: ' + err.message);
    });
}

// Initialize
buildGroups();
</script>
</body>
</html>
"""

RESULTS_TEMPLATE = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WK 2026 Voorspellingen - Overzicht</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh; color: #fff; padding: 20px;
        }
        .container { max-width: 1000px; margin: 0 auto; }
        h1 { text-align: center; font-size: 2.2em; margin-bottom: 30px; }
        .back-btn {
            display: inline-block; padding: 10px 20px;
            background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px; color: #fff; text-decoration: none; margin-bottom: 20px;
        }
        .back-btn:hover { background: rgba(255,255,255,0.2); }
        .prediction-card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 20px; margin-bottom: 16px;
        }
        .prediction-card h3 { color: #e94560; margin-bottom: 8px; }
        .prediction-card .champion { color: #ffd700; font-size: 1.2em; margin-bottom: 8px; }
        .prediction-card .details { color: #aaa; font-size: 0.9em; }
        .groups-summary {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 8px; margin-top: 12px; font-size: 0.85em; color: #ccc;
        }
        .no-predictions { text-align: center; color: #888; font-size: 1.2em; padding: 40px; }
        .toggle-details { cursor: pointer; color: #e94560; font-size: 0.9em; margin-top: 8px; display: inline-block; }
        .details-content { display: none; margin-top: 12px; }
        .details-content.show { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h1>&#128203; WK 2026 - Alle Voorspellingen</h1>
        <a href="/" class="back-btn">&#8592; Terug naar invullen</a>
        {% if predictions %}
            <p style="color: #aaa; margin-bottom: 20px;">{{ predictions|length }} voorspelling(en) ingediend</p>
            {% for name, pred in predictions.items() %}
            <div class="prediction-card">
                <h3>{{ pred.naam }}</h3>
                <div class="champion">&#127942; Kampioen: {{ pred.knockout.finale }}</div>
                <div class="details">Ingediend: {{ pred.datum }}</div>
                <span class="toggle-details" onclick="document.getElementById('details-{{ loop.index }}').classList.toggle('show')">&#9654; Toon details</span>
                <div class="details-content" id="details-{{ loop.index }}">
                    <div class="groups-summary">
                        {% for group, teams in pred.groepsfase.items() %}
                        <div><strong>Groep {{ group }}:</strong> {{ teams | join(' > ') }}</div>
                        {% endfor %}
                    </div>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <div class="no-predictions">
                <p>Nog geen voorspellingen ingediend.</p>
                <p style="margin-top: 10px;"><a href="/" style="color: #e94560;">Wees de eerste!</a></p>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""


@app.route('/')
def index():
    groepen_json = json.dumps(GROEPEN, ensure_ascii=False)
    html = HTML_TEMPLATE.replace('%GROEPEN_JSON%', groepen_json)
    return html


@app.route('/resultaten')
def resultaten():
    predictions = load_data()
    return render_template_string(RESULTS_TEMPLATE, predictions=predictions)


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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
