#!/usr/bin/env python3
"""
WK Voorspellingstool - Web App
==============================
Flask-gebaseerde webapp waarmee gebruikers via een link hun WK-voorspellingen
kunnen invullen. Inclusief groepsfase rangschikking en knock-outfase.

Installatie:
    pip install flask

Gebruik:
    python app.py
    
    Open http://localhost:5000 in je browser (of deploy naar een server)
"""

from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import json
import os
from datetime import datetime

app = Flask(__name__)

# Opslagbestand
DATA_FILE = "voorspellingen.json"

# WK 2026 Groepen (pas aan naar het juiste toernooi)
GROEPEN = {
    "A": ["Qatar", "Ecuador", "Senegal", "Nederland"],
    "B": ["Engeland", "Iran", "USA", "Wales"],
    "C": ["Argentinië", "Saudi-Arabië", "Mexico", "Polen"],
    "D": ["Frankrijk", "Australië", "Denemarken", "Tunesië"],
    "E": ["Spanje", "Costa Rica", "Duitsland", "Japan"],
    "F": ["België", "Canada", "Marokko", "Kroatië"],
    "G": ["Brazilië", "Servië", "Zwitserland", "Kameroen"],
    "H": ["Portugal", "Ghana", "Uruguay", "Zuid-Korea"],
}

# WK Bracket structuur (FIFA officieel)
BRACKET = [
    ("A", 0, "B", 1),  # 1A vs 2B
    ("C", 0, "D", 1),  # 1C vs 2D
    ("E", 0, "F", 1),  # 1E vs 2F
    ("G", 0, "H", 1),  # 1G vs 2H
    ("B", 0, "A", 1),  # 1B vs 2A
    ("D", 0, "C", 1),  # 1D vs 2C
    ("F", 0, "E", 1),  # 1F vs 2E
    ("H", 0, "G", 1),  # 1H vs 2G
]


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================
# HTML TEMPLATE
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚽ WK Voorspellingstool</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        
        h1 {
            text-align: center;
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }
        
        .subtitle {
            text-align: center;
            color: #aaa;
            margin-bottom: 30px;
            font-size: 1.1em;
        }
        
        .step-indicator {
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        
        .step {
            padding: 8px 16px;
            border-radius: 20px;
            background: rgba(255,255,255,0.1);
            font-size: 0.85em;
            transition: all 0.3s;
        }
        
        .step.active {
            background: #e94560;
            font-weight: bold;
        }
        
        .step.done {
            background: #2ecc71;
        }
        
        .card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
        }
        
        .card h2 {
            color: #e94560;
            margin-bottom: 16px;
            font-size: 1.4em;
        }
        
        .card h3 {
            color: #f0a500;
            margin-bottom: 12px;
        }
        
        .name-input {
            width: 100%;
            padding: 14px 20px;
            font-size: 1.1em;
            border: 2px solid rgba(255,255,255,0.2);
            border-radius: 10px;
            background: rgba(255,255,255,0.05);
            color: #fff;
            outline: none;
            transition: border-color 0.3s;
        }
        
        .name-input:focus {
            border-color: #e94560;
        }
        
        .group-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }
        
        .group-card {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 16px;
        }
        
        .group-card h3 {
            font-size: 1.1em;
            margin-bottom: 10px;
            color: #f0a500;
        }
        
        .sortable-list {
            list-style: none;
            padding: 0;
        }
        
        .sortable-list li {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 14px;
            margin-bottom: 6px;
            background: rgba(255,255,255,0.08);
            border-radius: 8px;
            cursor: grab;
            transition: all 0.2s;
            user-select: none;
        }
        
        .sortable-list li:hover {
            background: rgba(255,255,255,0.15);
        }
        
        .sortable-list li.dragging {
            opacity: 0.5;
            background: rgba(233, 69, 96, 0.3);
        }
        
        .position-badge {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8em;
            font-weight: bold;
            flex-shrink: 0;
        }
        
        .pos-1 { background: #ffd700; color: #000; }
        .pos-2 { background: #c0c0c0; color: #000; }
        .pos-3 { background: #cd7f32; color: #fff; }
        .pos-4 { background: #555; color: #fff; }
        
        .flag-emoji {
            font-size: 1.3em;
        }
        
        .match-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 16px;
            margin-bottom: 10px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            gap: 10px;
        }
        
        .match-team {
            flex: 1;
            text-align: center;
            padding: 10px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
            border: 2px solid transparent;
        }
        
        .match-team:hover {
            background: rgba(255,255,255,0.1);
        }
        
        .match-team.selected {
            background: rgba(46, 204, 113, 0.2);
            border-color: #2ecc71;
        }
        
        .match-vs {
            font-weight: bold;
            color: #e94560;
            font-size: 0.9em;
            flex-shrink: 0;
        }
        
        .knockout-round {
            margin-bottom: 24px;
        }
        
        .knockout-round h3 {
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        
        .btn {
            display: inline-block;
            padding: 14px 32px;
            font-size: 1.1em;
            font-weight: bold;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .btn-primary {
            background: #e94560;
            color: #fff;
        }
        
        .btn-primary:hover {
            background: #d63851;
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.4);
        }
        
        .btn-secondary {
            background: rgba(255,255,255,0.1);
            color: #fff;
            border: 1px solid rgba(255,255,255,0.2);
        }
        
        .btn-secondary:hover {
            background: rgba(255,255,255,0.2);
        }
        
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
        }
        
        .btn-group {
            display: flex;
            gap: 12px;
            justify-content: center;
            margin-top: 24px;
            flex-wrap: wrap;
        }
        
        .hidden {
            display: none;
        }
        
        .success-screen {
            text-align: center;
            padding: 40px 20px;
        }
        
        .success-screen h2 {
            color: #2ecc71;
            font-size: 2em;
            margin-bottom: 16px;
        }
        
        .success-screen .trophy {
            font-size: 4em;
            margin-bottom: 20px;
        }
        
        .champion-name {
            font-size: 1.5em;
            color: #ffd700;
            margin: 16px 0;
        }
        
        .drag-hint {
            color: #888;
            font-size: 0.85em;
            margin-bottom: 12px;
            font-style: italic;
        }
        
        /* Admin page */
        .predictions-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }
        
        .predictions-table th,
        .predictions-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        
        .predictions-table th {
            color: #f0a500;
        }
        
        .predictions-table tr:hover td {
            background: rgba(255,255,255,0.05);
        }

        @media (max-width: 600px) {
            h1 { font-size: 1.8em; }
            .match-card { flex-direction: column; }
            .match-team { width: 100%; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚽ WK Voorspellingen</h1>
        <p class="subtitle">Vul je voorspellingen in voor het WK!</p>
        
        <!-- Step Indicator -->
        <div class="step-indicator">
            <div class="step active" id="step-ind-1">1. Naam</div>
            <div class="step" id="step-ind-2">2. Groepsfase</div>
            <div class="step" id="step-ind-3">3. Knock-out</div>
            <div class="step" id="step-ind-4">4. Klaar!</div>
        </div>

        <!-- STEP 1: Name -->
        <div id="step-1" class="card">
            <h2>👤 Wie ben je?</h2>
            <input type="text" class="name-input" id="player-name" placeholder="Vul je naam in..." autocomplete="off">
            <div class="btn-group">
                <button class="btn btn-primary" onclick="goToStep(2)">Volgende →</button>
            </div>
        </div>

        <!-- STEP 2: Group Stage -->
        <div id="step-2" class="card hidden">
            <h2>📊 Groepsfase</h2>
            <p class="drag-hint">Sleep de landen in de juiste volgorde (1 = groepswinnaar, 4 = laatste)</p>
            <div class="group-grid" id="groups-container">
                <!-- Generated by JS -->
            </div>
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="goToStep(1)">← Terug</button>
                <button class="btn btn-primary" onclick="goToStep(3)">Volgende →</button>
            </div>
        </div>

        <!-- STEP 3: Knockout -->
        <div id="step-3" class="card hidden">
            <h2>🏆 Knock-outfase</h2>
            <p class="drag-hint">Klik op het team dat je denkt dat wint</p>
            <div id="knockout-container">
                <!-- Generated by JS -->
            </div>
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="goToStep(2)">← Terug</button>
                <button class="btn btn-primary" onclick="submitPrediction()">✅ Voorspelling Indienen</button>
            </div>
        </div>

        <!-- STEP 4: Success -->
        <div id="step-4" class="card hidden">
            <div class="success-screen">
                <div class="trophy">🏆</div>
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
        // Data from server
        const GROEPEN = {{ groepen | tojson }};
        const BRACKET = {{ bracket | tojson }};
        
        let currentStep = 1;
        let groupPredictions = {};
        let knockoutPredictions = {};

        // ============ STEP NAVIGATION ============
        function goToStep(step) {
            if (step === 2 && !document.getElementById('player-name').value.trim()) {
                alert('Vul je naam in!');
                return;
            }
            
            document.getElementById(`step-${currentStep}`).classList.add('hidden');
            document.getElementById(`step-${step}`).classList.remove('hidden');
            
            // Update indicators
            for (let i = 1; i <= 4; i++) {
                const ind = document.getElementById(`step-ind-${i}`);
                ind.classList.remove('active', 'done');
                if (i < step) ind.classList.add('done');
                if (i === step) ind.classList.add('active');
            }
            
            currentStep = step;
            
            if (step === 3) {
                buildKnockout();
            }
            
            window.scrollTo(0, 0);
        }

        // ============ GROUP STAGE ============
        function buildGroups() {
            const container = document.getElementById('groups-container');
            container.innerHTML = '';
            
            for (const [group, teams] of Object.entries(GROEPEN)) {
                const card = document.createElement('div');
                card.className = 'group-card';
                card.innerHTML = `
                    <h3>Groep ${group}</h3>
                    <ul class="sortable-list" id="group-${group}">
                        ${teams.map((team, i) => `
                            <li draggable="true" data-team="${team}">
                                <span class="position-badge pos-${i+1}">${i+1}</span>
                                <span>${team}</span>
                            </li>
                        `).join('')}
                    </ul>
                `;
                container.appendChild(card);
                
                // Initialize drag and drop
                initSortable(card.querySelector('.sortable-list'));
            }
        }

        function initSortable(list) {
            let draggedItem = null;
            
            list.addEventListener('dragstart', (e) => {
                draggedItem = e.target.closest('li');
                if (draggedItem) {
                    draggedItem.classList.add('dragging');
                }
            });
            
            list.addEventListener('dragend', (e) => {
                if (draggedItem) {
                    draggedItem.classList.remove('dragging');
                    draggedItem = null;
                    updatePositionBadges(list);
                }
            });
            
            list.addEventListener('dragover', (e) => {
                e.preventDefault();
                const afterElement = getDragAfterElement(list, e.clientY);
                if (draggedItem) {
                    if (afterElement == null) {
                        list.appendChild(draggedItem);
                    } else {
                        list.insertBefore(draggedItem, afterElement);
                    }
                }
            });

            // Touch support
            let touchDragItem = null;
            let touchStartY = 0;
            
            list.addEventListener('touchstart', (e) => {
                touchDragItem = e.target.closest('li');
                if (touchDragItem) {
                    touchStartY = e.touches[0].clientY;
                    touchDragItem.classList.add('dragging');
                }
            });

            list.addEventListener('touchmove', (e) => {
                e.preventDefault();
                if (!touchDragItem) return;
                const touchY = e.touches[0].clientY;
                const afterElement = getDragAfterElement(list, touchY);
                if (afterElement == null) {
                    list.appendChild(touchDragItem);
                } else {
                    list.insertBefore(touchDragItem, afterElement);
                }
            });

            list.addEventListener('touchend', (e) => {
                if (touchDragItem) {
                    touchDragItem.classList.remove('dragging');
                    touchDragItem = null;
                    updatePositionBadges(list);
                }
            });
        }

        function getDragAfterElement(container, y) {
            const draggableElements = [...container.querySelectorAll('li:not(.dragging)')];
            return draggableElements.reduce((closest, child) => {
                const box = child.getBoundingClientRect();
                const offset = y - box.top - box.height / 2;
                if (offset < 0 && offset > closest.offset) {
                    return { offset: offset, element: child };
                } else {
                    return closest;
                }
            }, { offset: Number.NEGATIVE_INFINITY }).element;
        }

        function updatePositionBadges(list) {
            const items = list.querySelectorAll('li');
            items.forEach((item, i) => {
                const badge = item.querySelector('.position-badge');
                badge.className = `position-badge pos-${i+1}`;
                badge.textContent = i + 1;
            });
        }

        function getGroupResults() {
            const results = {};
            for (const group of Object.keys(GROEPEN)) {
                const list = document.getElementById(`group-${group}`);
                const items = list.querySelectorAll('li');
                results[group] = Array.from(items).map(li => li.dataset.team);
            }
            return results;
        }

        // ============ KNOCKOUT STAGE ============
        function buildKnockout() {
            groupPredictions = getGroupResults();
            const container = document.getElementById('knockout-container');
            container.innerHTML = '';
            knockoutPredictions = {};
            
            // Build R16 matches
            const r16Matches = BRACKET.map(([g1, p1, g2, p2]) => ({
                team1: groupPredictions[g1][p1],
                team2: groupPredictions[g2][p2]
            }));
            
            const rounds = [
                { name: "Achtste Finales", matches: r16Matches, key: "r16" },
            ];
            
            buildRound(container, "🏅 Achtste Finales", r16Matches, "r16", () => {
                // Build QF
                const qfDiv = document.getElementById('round-qf');
                if (qfDiv) qfDiv.remove();
                const sfDiv = document.getElementById('round-sf');
                if (sfDiv) sfDiv.remove();
                const fDiv = document.getElementById('round-final');
                if (fDiv) fDiv.remove();
                
                const r16Winners = getWinners("r16", 8);
                if (!r16Winners) return;
                
                const qfMatches = [
                    { team1: r16Winners[0], team2: r16Winners[1] },
                    { team1: r16Winners[2], team2: r16Winners[3] },
                    { team1: r16Winners[4], team2: r16Winners[5] },
                    { team1: r16Winners[6], team2: r16Winners[7] },
                ];
                buildRound(container, "🥇 Kwartfinales", qfMatches, "qf", () => {
                    const sfDivInner = document.getElementById('round-sf');
                    if (sfDivInner) sfDivInner.remove();
                    const fDivInner = document.getElementById('round-final');
                    if (fDivInner) fDivInner.remove();
                    
                    const qfWinners = getWinners("qf", 4);
                    if (!qfWinners) return;
                    
                    const sfMatches = [
                        { team1: qfWinners[0], team2: qfWinners[1] },
                        { team1: qfWinners[2], team2: qfWinners[3] },
                    ];
                    buildRound(container, "⭐ Halve Finales", sfMatches, "sf", () => {
                        const fDivInner2 = document.getElementById('round-final');
                        if (fDivInner2) fDivInner2.remove();
                        
                        const sfWinners = getWinners("sf", 2);
                        if (!sfWinners) return;
                        
                        const finalMatch = [
                            { team1: sfWinners[0], team2: sfWinners[1] }
                        ];
                        buildRound(container, "🏆 FINALE", finalMatch, "final", () => {});
                    });
                });
            });
        }

        function buildRound(container, title, matches, roundKey, onComplete) {
            const roundDiv = document.createElement('div');
            roundDiv.className = 'knockout-round';
            roundDiv.id = `round-${roundKey}`;
            roundDiv.innerHTML = `<h3>${title}</h3>`;
            
            matches.forEach((match, i) => {
                const matchDiv = document.createElement('div');
                matchDiv.className = 'match-card';
                matchDiv.innerHTML = `
                    <div class="match-team" id="${roundKey}-${i}-1" onclick="selectWinner('${roundKey}', ${i}, 1, '${match.team1}', ${JSON.stringify(onComplete.toString())})">
                        ${match.team1}
                    </div>
                    <span class="match-vs">VS</span>
                    <div class="match-team" id="${roundKey}-${i}-2" onclick="selectWinner('${roundKey}', ${i}, 2, '${match.team2}', null)">
                        ${match.team2}
                    </div>
                `;
                roundDiv.appendChild(matchDiv);
            });
            
            container.appendChild(roundDiv);
            
            // Store callback
            window[`callback_${roundKey}`] = onComplete;
        }

        function selectWinner(roundKey, matchIndex, teamNum, teamName) {
            // Update visual
            const el1 = document.getElementById(`${roundKey}-${matchIndex}-1`);
            const el2 = document.getElementById(`${roundKey}-${matchIndex}-2`);
            el1.classList.remove('selected');
            el2.classList.remove('selected');
            document.getElementById(`${roundKey}-${matchIndex}-${teamNum}`).classList.add('selected');
            
            // Store
            if (!knockoutPredictions[roundKey]) knockoutPredictions[roundKey] = {};
            knockoutPredictions[roundKey][matchIndex] = teamName;
            
            // Trigger next round build
            const callback = window[`callback_${roundKey}`];
            if (callback) callback();
        }

        function getWinners(roundKey, expectedCount) {
            const preds = knockoutPredictions[roundKey];
            if (!preds || Object.keys(preds).length < expectedCount) return null;
            const winners = [];
            for (let i = 0; i < expectedCount; i++) {
                if (!preds[i]) return null;
                winners.push(preds[i]);
            }
            return winners;
        }

        // ============ SUBMIT ============
        function submitPrediction() {
            const name = document.getElementById('player-name').value.trim();
            const groups = getGroupResults();
            
            // Validate knockout is complete
            const finalWinner = knockoutPredictions.final && knockoutPredictions.final[0];
            if (!finalWinner) {
                alert('Vul alle knock-outwedstrijden in! Selecteer een winnaar voor elke wedstrijd.');
                return;
            }
            
            const data = {
                naam: name,
                groepsfase: groups,
                knockout: {
                    achtste_finales: knockoutPredictions.r16 || {},
                    kwartfinales: knockoutPredictions.qf || {},
                    halve_finales: knockoutPredictions.sf || {},
                    finale: finalWinner
                }
            };
            
            fetch('/api/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(res => res.json())
            .then(result => {
                if (result.success) {
                    document.getElementById('confirm-name').textContent = name;
                    document.getElementById('confirm-champion').textContent = finalWinner;
                    goToStep(4);
                } else {
                    alert('Er ging iets mis: ' + result.error);
                }
            })
            .catch(err => {
                alert('Fout bij verzenden: ' + err.message);
            });
        }

        // Initialize
        buildGroups();
    </script>
</body>
</html>
"""

# ============================================================
# RESULTS PAGE TEMPLATE
# ============================================================
RESULTS_TEMPLATE = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📋 WK Voorspellingen - Overzicht</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        .container { max-width: 1000px; margin: 0 auto; }
        h1 { text-align: center; font-size: 2.2em; margin-bottom: 30px; }
        .back-btn {
            display: inline-block;
            padding: 10px 20px;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            color: #fff;
            text-decoration: none;
            margin-bottom: 20px;
            transition: background 0.3s;
        }
        .back-btn:hover { background: rgba(255,255,255,0.2); }
        .prediction-card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
        }
        .prediction-card h3 { color: #e94560; margin-bottom: 8px; }
        .prediction-card .champion { color: #ffd700; font-size: 1.2em; margin-bottom: 8px; }
        .prediction-card .details { color: #aaa; font-size: 0.9em; }
        .prediction-card .groups-summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 8px;
            margin-top: 12px;
            font-size: 0.85em;
            color: #ccc;
        }
        .no-predictions {
            text-align: center;
            color: #888;
            font-size: 1.2em;
            padding: 40px;
        }
        .toggle-details {
            cursor: pointer;
            color: #e94560;
            font-size: 0.9em;
            margin-top: 8px;
            display: inline-block;
        }
        .details-content { display: none; margin-top: 12px; }
        .details-content.show { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 Alle Voorspellingen</h1>
        <a href="/" class="back-btn">← Terug naar invullen</a>
        
        {% if predictions %}
            <p style="color: #aaa; margin-bottom: 20px;">{{ predictions|length }} voorspelling(en) ingediend</p>
            {% for name, pred in predictions.items() %}
            <div class="prediction-card">
                <h3>{{ pred.naam }}</h3>
                <div class="champion">🏆 Kampioen: {{ pred.knockout.finale }}</div>
                <div class="details">Ingediend: {{ pred.datum }}</div>
                <span class="toggle-details" onclick="toggleDetails('details-{{ loop.index }}')">▶ Toon details</span>
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
                <p>😔 Nog geen voorspellingen ingediend.</p>
                <p style="margin-top: 10px;"><a href="/" style="color: #e94560;">Wees de eerste!</a></p>
            </div>
        {% endif %}
    </div>
    <script>
        function toggleDetails(id) {
            document.getElementById(id).classList.toggle('show');
        }
    </script>
</body>
</html>
"""


# ============================================================
# ROUTES
# ============================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, groepen=GROEPEN, bracket=BRACKET)


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


# ============================================================
# RUN
# ============================================================
if __name__ == '__main__':
    print("=" * 50)
    print("  ⚽ WK Voorspellingstool is gestart!")
    print("  📱 Open: http://localhost:5000")
    print("  📋 Resultaten: http://localhost:5000/resultaten")
    print("=" * 50)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
