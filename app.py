#!/usr/bin/env python3
"""
AZ St Blasius - WK 2026 Voorspellingstool
Met officieel WK 2026 knock-out schema en SQLite database
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

R32_SCHEMA = [
    {"thuis": "2A", "uit": "2B"},
    {"thuis": "1C", "uit": "2F"},
    {"thuis": "1E", "uit": "3_ABCDF"},
    {"thuis": "1F", "uit": "2C"},
    {"thuis": "2E", "uit": "2I"},
    {"thuis": "1I", "uit": "3_CDFGH"},
    {"thuis": "1A", "uit": "3_CEFHI"},
    {"thuis": "1L", "uit": "3_EHIJK"},
    {"thuis": "1G", "uit": "3_AEHIJ"},
    {"thuis": "1D", "uit": "3_BEFIJ"},
    {"thuis": "1H", "uit": "2J"},
    {"thuis": "2K", "uit": "2L"},
    {"thuis": "1B", "uit": "3_EFGIJ"},
    {"thuis": "2D", "uit": "2G"},
    {"thuis": "1J", "uit": "2H"},
    {"thuis": "1K", "uit": "3_DEIJL"},
]

DERDE_SLOTS = [
    {"id": "3_ABCDF", "options": ["A", "B", "C", "D", "F"], "label": "Derde uit A/B/C/D/F", "tegen": "Eerste groep E"},
    {"id": "3_CDFGH", "options": ["C", "D", "F", "G", "H"], "label": "Derde uit C/D/F/G/H", "tegen": "Eerste groep I"},
    {"id": "3_CEFHI", "options": ["C", "E", "F", "H", "I"], "label": "Derde uit C/E/F/H/I", "tegen": "Eerste groep A"},
    {"id": "3_EHIJK", "options": ["E", "H", "I", "J", "K"], "label": "Derde uit E/H/I/J/K", "tegen": "Eerste groep L"},
    {"id": "3_AEHIJ", "options": ["A", "E", "H", "I", "J"], "label": "Derde uit A/E/H/I/J", "tegen": "Eerste groep G"},
    {"id": "3_BEFIJ", "options": ["B", "E", "F", "I", "J"], "label": "Derde uit B/E/F/I/J", "tegen": "Eerste groep D"},
    {"id": "3_EFGIJ", "options": ["E", "F", "G", "I", "J"], "label": "Derde uit E/F/G/I/J", "tegen": "Eerste groep B"},
    {"id": "3_DEIJL", "options": ["D", "E", "I", "J", "L"], "label": "Derde uit D/E/I/J/L", "tegen": "Eerste groep K"},
]

PUNTEN = {
    "groep_juiste_positie": 1, "groep_juiste_winnaar": 2, "groep_juiste_tweede": 1,
    "beste_derde_juist": 2, "r32_juist": 3, "r16_juist": 5, "qf_juist": 7,
    "sf_juist": 10, "finalist_juist": 12, "winnaar_juist": 15,
}

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS voorspellingen (naam TEXT PRIMARY KEY, data TEXT NOT NULL, datum TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS echte_resultaten (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL, datum TEXT NOT NULL)")
    conn.commit(); conn.close()

def load_data():
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT naam, data FROM voorspellingen"); rows = c.fetchall(); conn.close()
    return {naam: json.loads(data) for naam, data in rows}

def save_prediction(naam, data):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    datum = datetime.now().strftime("%Y-%m-%d %H:%M"); data['datum'] = datum
    c.execute("INSERT OR REPLACE INTO voorspellingen (naam, data, datum) VALUES (?, ?, ?)", (naam, json.dumps(data, ensure_ascii=False), datum))
    conn.commit(); conn.close()

def load_results():
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT data FROM echte_resultaten WHERE id = 1"); row = c.fetchone(); conn.close()
    return json.loads(row[0]) if row else {}

def save_results(data):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    datum = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT OR REPLACE INTO echte_resultaten (id, data, datum) VALUES (1, ?, ?)", (json.dumps(data, ensure_ascii=False), datum))
    conn.commit(); conn.close()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'): return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def calculate_points(prediction, real_results):
    points = {"groep_positie": 0, "groep_winnaar": 0, "groep_tweede": 0, "beste_derdes": 0, "r32": 0, "r16": 0, "qf": 0, "sf": 0, "finalist": 0, "winnaar": 0, "totaal": 0, "details": []}
    if not real_results: return points
    real_groups = real_results.get("groepsfase", {}); pred_groups = prediction.get("groepsfase", {})
    for group in pred_groups:
        if group not in real_groups: continue
        real_order = real_groups[group]; pred_order = pred_groups[group]
        if len(real_order)>0 and len(pred_order)>0 and pred_order[0]==real_order[0]:
            points["groep_winnaar"] += PUNTEN["groep_juiste_winnaar"]
        if len(real_order)>1 and len(pred_order)>1 and pred_order[1]==real_order[1]:
            points["groep_tweede"] += PUNTEN["groep_juiste_tweede"]
        for i, team in enumerate(pred_order):
            if i < len(real_order) and real_order[i] == team: points["groep_positie"] += PUNTEN["groep_juiste_positie"]
    real_thirds = real_results.get("beste_derdes", {}); pred_thirds = prediction.get("beste_derdes", {})
    if isinstance(real_thirds, dict) and isinstance(pred_thirds, dict):
        for slot_id, pred_group in pred_thirds.items():
            if pred_group and real_thirds.get(slot_id, "") == pred_group:
                points["beste_derdes"] += PUNTEN["beste_derde_juist"]
    real_knockout = real_results.get("knockout", {}); pred_knockout = prediction.get("knockout", {})
    for key, pk, pts, label in [("ronde_van_32","r32",PUNTEN["r32_juist"],"R32"),("ronde_van_16","r16",PUNTEN["r16_juist"],"R16"),("kwartfinales","qf",PUNTEN["qf_juist"],"KF"),("halve_finales","sf",PUNTEN["sf_juist"],"HF")]:
        rr = real_knockout.get(key, {}); pr = pred_knockout.get(key, {})
        if rr and pr:
            correct = len(set(rr.values()) & set(pr.values())) if isinstance(rr, dict) and isinstance(pr, dict) else 0
            points[pk] = correct * pts
    real_finale = real_knockout.get("finale", ""); pred_finale = pred_knockout.get("finale", "")
    if real_finale and pred_finale == real_finale: points["winnaar"] = PUNTEN["winnaar_juist"]
    real_sf = real_knockout.get("halve_finales", {}); pred_sf = pred_knockout.get("halve_finales", {})
    if real_sf and pred_sf and isinstance(real_sf, dict) and isinstance(pred_sf, dict):
        points["finalist"] = len(set(real_sf.values()) & set(pred_sf.values())) * PUNTEN["finalist_juist"]
    points["totaal"] = sum([points["groep_positie"], points["groep_winnaar"], points["groep_tweede"], points["beste_derdes"], points["r32"], points["r16"], points["qf"], points["sf"], points["finalist"], points["winnaar"]])
    return points
