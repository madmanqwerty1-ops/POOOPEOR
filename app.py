from flask import Flask, render_template_string, request, redirect, jsonify, send_file
import json, os, random, math, csv, io
from datetime import datetime, timedelta
import collections

app = Flask(__name__)

DATA_FILE = "data.json"

# ---------------------
# Utility Functions
# ---------------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"players": {}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def expected_score(r1, r2):
    return 1 / (1 + 10 ** ((r2 - r1) / 400))

def update_elo(r1, r2, score, k=32):
    e1 = expected_score(r1, r2)
    e2 = expected_score(r2, r1)
    return r1 + k * (score - e1), r2 + k * ((1 - score) - e2)

def calculate_advanced_stats(data, player_name):
    """Calculate advanced statistics for a player"""
    matches = [m for m in data.get("matches", []) if m["player1"] == player_name or m["player2"] == player_name]
    if not matches:
        return {}
    
    wins = 0
    losses = 0
    points_for = 0
    points_against = 0
    current_streak = 0
    longest_streak = 0
    elo_history = []
    
    # Sort matches by date (assuming they're in chronological order)
    for match in matches:
        is_player1 = match["player1"] == player_name
        my_score = match["score1"] if is_player1 else match["score2"]
        opp_score = match["score2"] if is_player1 else match["score1"]
        
        points_for += my_score
        points_against += opp_score
        
        if my_score > opp_score:
            wins += 1
            if current_streak >= 0:
                current_streak += 1
            else:
                current_streak = 1
        else:
            losses += 1
            if current_streak <= 0:
                current_streak -= 1
            else:
                current_streak = -1
        
        longest_streak = max(longest_streak, abs(current_streak))
        
        # Track ELO changes
        if is_player1:
            elo_change = match["elo_change1"]
        else:
            elo_change = match["elo_change2"]
        elo_history.append(elo_change)
    
    total_games = wins + losses
    win_rate = (wins / total_games * 100) if total_games > 0 else 0
    
    return {
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "points_for": points_for,
        "points_against": points_against,
        "games_played": total_games,
        "avg_points_for": round(points_for / total_games, 1) if total_games > 0 else 0,
        "avg_points_against": round(points_against / total_games, 1) if total_games > 0 else 0,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "elo_history": elo_history
    }

def get_head_to_head(data, player1, player2):
    """Get head-to-head record between two players"""
    matches = [m for m in data.get("matches", []) 
               if (m["player1"] == player1 and m["player2"] == player2) or 
                  (m["player1"] == player2 and m["player2"] == player1)]
    
    p1_wins = 0
    p2_wins = 0
    
    for match in matches:
        if match["winner"] == player1:
            p1_wins += 1
        else:
            p2_wins += 1
    
    return {"player1_wins": p1_wins, "player2_wins": p2_wins, "total": len(matches)}

def get_biggest_upsets(data):
    """Find biggest upsets (lower ELO beating higher ELO)"""
    upsets = []
    for match in data.get("matches", []):
        p1_elo_before = match.get("elo_before1", 1000)
        p2_elo_before = match.get("elo_before2", 1000)
        
        if match["winner"] == match["player1"] and p1_elo_before < p2_elo_before:
            elo_diff = p2_elo_before - p1_elo_before
            upsets.append({
                "match": match,
                "elo_difference": elo_diff,
                "underdog": match["player1"],
                "favorite": match["player2"]
            })
        elif match["winner"] == match["player2"] and p2_elo_before < p1_elo_before:
            elo_diff = p1_elo_before - p2_elo_before
            upsets.append({
                "match": match,
                "elo_difference": elo_diff,
                "underdog": match["player2"],
                "favorite": match["player1"]
            })
    
    return sorted(upsets, key=lambda x: x["elo_difference"], reverse=True)

# ---------------------
# Routes
# ---------------------
@app.route("/")
def index():
    data = load_data()
    players = sorted(data["players"].items(), key=lambda x: x[1]["elo"], reverse=True)
    return render_template_string(TEMPLATE_INDEX, players=players)

@app.route("/add_player", methods=["POST"])
def add_player():
    name = request.form.get("name")
    data = load_data()
    if name and name not in data["players"]:
        data["players"][name] = {"elo": 1000, "wins": 0, "losses": 0}
        save_data(data)
    return redirect("/")

@app.route("/remove_player", methods=["POST"])
def remove_player():
    name = request.form.get("name")
    data = load_data()
    if name in data["players"]:
        del data["players"][name]
        save_data(data)
    return redirect("/")

@app.route("/report_match", methods=["POST"])
def report_match():
    p1 = request.form.get("player1")
    p2 = request.form.get("player2")
    score1 = request.form.get("score1")
    score2 = request.form.get("score2")

    data = load_data()
    if p1 in data["players"] and p2 in data["players"] and p1 != p2:
        try:
            s1 = int(score1) if score1 else 0
            s2 = int(score2) if score2 else 0
            
            # Determine winner based on scores
            if s1 > s2:
                winner = p1
                score = 1
            elif s2 > s1:
                winner = p2
                score = 0
            else:
                # Handle tie - no ELO change, but still record the match
                return redirect("/")
            
            r1 = data["players"][p1]["elo"]
            r2 = data["players"][p2]["elo"]
            
            new_r1, new_r2 = update_elo(r1, r2, score)
            
            if score == 1:
                data["players"][p1]["wins"] += 1
                data["players"][p2]["losses"] += 1
            else:
                data["players"][p2]["wins"] += 1
                data["players"][p1]["losses"] += 1

            data["players"][p1]["elo"] = round(new_r1)
            data["players"][p2]["elo"] = round(new_r2)
            
            # Store match history
            if "matches" not in data:
                data["matches"] = []
            
            match_record = {
                "id": len(data["matches"]) + 1,
                "player1": p1,
                "player2": p2,
                "score1": s1,
                "score2": s2,
                "winner": winner,
                "elo_before1": r1,
                "elo_before2": r2,
                "elo_after1": round(new_r1),
                "elo_after2": round(new_r2),
                "elo_change1": round(new_r1 - r1),
                "elo_change2": round(new_r2 - r2),
                "date": datetime.now().isoformat()
            }
            data["matches"].append(match_record)
            
            save_data(data)
        except ValueError:
            pass  # Invalid score input
    return redirect("/")

@app.route("/weekly_matchups")
def weekly_matchups():
    data = load_data()
    players = list(data["players"].keys())
    random.shuffle(players)
    pairs = [(players[i], players[i+1]) for i in range(0, len(players)-1, 2)]
    return render_template_string(TEMPLATE_MATCHUPS, pairs=pairs)

@app.route("/statistics")
def statistics():
    data = load_data()
    players = data["players"]
    matches = data.get("matches", [])
    
    # Calculate advanced statistics for each player
    player_stats = {}
    for player_name in players.keys():
        stats = calculate_advanced_stats(data, player_name)
        if stats:  # Only include players with matches
            player_stats[player_name] = stats
    
    # Recent matches
    recent_matches = matches[-10:] if matches else []
    
    return render_template_string(TEMPLATE_STATISTICS, 
                                players=players, 
                                player_stats=player_stats, 
                                recent_matches=recent_matches)

@app.route("/match_history")
def match_history():
    data = load_data()
    matches = data.get("matches", [])
    return render_template_string(TEMPLATE_MATCH_HISTORY, matches=matches)

@app.route("/delete_match/<int:match_id>", methods=["POST"])
def delete_match(match_id):
    data = load_data()
    matches = data.get("matches", [])
    
    # Find and remove the match
    for i, match in enumerate(matches):
        if match["id"] == match_id:
            # Recalculate ELO for all subsequent matches
            deleted_match = matches.pop(i)
            
            # Recalculate all player stats from scratch
            for player_name in data["players"]:
                data["players"][player_name] = {"elo": 1000, "wins": 0, "losses": 0}
            
            # Replay all remaining matches
            for match in matches:
                p1 = match["player1"]
                p2 = match["player2"]
                r1 = data["players"][p1]["elo"]
                r2 = data["players"][p2]["elo"]
                
                if match["winner"] == p1:
                    score = 1
                else:
                    score = 0
                
                new_r1, new_r2 = update_elo(r1, r2, score)
                data["players"][p1]["elo"] = round(new_r1)
                data["players"][p2]["elo"] = round(new_r2)
                
                if score == 1:
                    data["players"][p1]["wins"] += 1
                    data["players"][p2]["losses"] += 1
                else:
                    data["players"][p2]["wins"] += 1
                    data["players"][p1]["losses"] += 1
            
            save_data(data)
            break
    
    return redirect("/match_history")

@app.route("/player/<player_name>")
def player_profile(player_name):
    data = load_data()
    if player_name not in data["players"]:
        return redirect("/")
    
    player_data = data["players"][player_name]
    matches = [m for m in data.get("matches", []) if m["player1"] == player_name or m["player2"] == player_name]
    stats = calculate_advanced_stats(data, player_name)
    
    return render_template_string(TEMPLATE_PLAYER_PROFILE, 
                                player_name=player_name,
                                player_data=player_data,
                                matches=matches,
                                stats=stats)

@app.route("/leaderboard_history")
def leaderboard_history():
    data = load_data()
    # This would need to be implemented with historical snapshots
    # For now, we'll show current rankings
    players = sorted(data["players"].items(), key=lambda x: x[1]["elo"], reverse=True)
    return render_template_string(TEMPLATE_LEADERBOARD_HISTORY, players=players)

@app.route("/export_csv")
def export_csv():
    data = load_data()
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write player data
    writer.writerow(["Player", "ELO", "Wins", "Losses", "Win Rate"])
    for name, stats in data["players"].items():
        total = stats["wins"] + stats["losses"]
        win_rate = (stats["wins"] / total * 100) if total > 0 else 0
        writer.writerow([name, stats["elo"], stats["wins"], stats["losses"], f"{win_rate:.1f}%"])
    
    # Write match data
    writer.writerow([])
    writer.writerow(["Match History"])
    writer.writerow(["Date", "Player 1", "Score 1", "Player 2", "Score 2", "Winner", "ELO Change 1", "ELO Change 2"])
    for match in data.get("matches", []):
        date = match.get("date", "Unknown")[:10]  # Just the date part
        writer.writerow([
            date, match["player1"], match["score1"], match["player2"], 
            match["score2"], match["winner"], match["elo_change1"], match["elo_change2"]
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name='ping_pong_league_data.csv'
    )

@app.route("/schedule_matches")
def schedule_matches():
    data = load_data()
    players = list(data["players"].keys())
    
    if len(players) < 2:
        return redirect("/")
    
    # Simple round-robin scheduling
    if len(players) % 2 == 1:
        players.append("BYE")
    
    n = len(players)
    schedule = []
    
    for round_num in range(n - 1):
        round_matches = []
        for i in range(n // 2):
            p1 = players[i]
            p2 = players[n - 1 - i]
            if p1 != "BYE" and p2 != "BYE":
                round_matches.append((p1, p2))
        schedule.append(round_matches)
        
        # Rotate players (except first player)
        players = [players[0]] + players[-1:] + players[1:-1]
    
    return render_template_string(TEMPLATE_SCHEDULE, schedule=schedule)

# ---------------------
# Templates (inline for simplicity)
# ---------------------
TEMPLATE_INDEX = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏓 Ping Pong League</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .hero-section { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 3rem 0; }
        .stat-card { transition: transform 0.2s; }
        .stat-card:hover { transform: translateY(-5px); }
        .player-card { border-left: 4px solid #007bff; }
        .rank-1 { border-left-color: #ffd700; }
        .rank-2 { border-left-color: #c0c0c0; }
        .rank-3 { border-left-color: #cd7f32; }
        .dark-mode { background-color: #1a1a1a; color: #ffffff; }
        .dark-mode .card { background-color: #2d2d2d; border-color: #444; }
        .dark-mode .table { color: #ffffff; }
    </style>
</head>
<body>
    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-table-tennis me-2"></i>Ping Pong League
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="/statistics">
                            <i class="fas fa-chart-bar me-1"></i>Statistics
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="/match_history">
                            <i class="fas fa-history me-1"></i>Match History
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="/schedule_matches">
                            <i class="fas fa-calendar me-1"></i>Schedule
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="/export_csv">
                            <i class="fas fa-download me-1"></i>Export
                        </a>
                    </li>
                    <li class="nav-item">
                        <button class="btn btn-outline-light btn-sm ms-2" onclick="toggleDarkMode()">
                            <i class="fas fa-moon"></i>
                        </button>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <!-- Hero Section -->
    <div class="hero-section">
        <div class="container text-center">
            <h1 class="display-4 mb-3">🏓 Ping Pong League</h1>
            <p class="lead">Track rankings, manage matches, and analyze performance</p>
        </div>
    </div>

    <div class="container mt-4">
        <!-- Rankings Section -->
        <div class="row mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h3 class="mb-0"><i class="fas fa-trophy me-2"></i>Current Rankings</h3>
                    </div>
                    <div class="card-body">
                        {% if players %}
                        <div class="table-responsive">
                            <table class="table table-hover">
                                <thead>
                                    <tr>
                                        <th>Rank</th>
                                        <th>Player</th>
                                        <th>ELO</th>
                                        <th>Wins</th>
                                        <th>Losses</th>
                                        <th>Win Rate</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for name, stats in players %}
                                    <tr class="player-card rank-{{loop.index if loop.index <= 3 else ''}}">
                                        <td>
                                            {% if loop.index == 1 %}
                                                <i class="fas fa-crown text-warning"></i>
                                            {% elif loop.index == 2 %}
                                                <i class="fas fa-medal text-secondary"></i>
                                            {% elif loop.index == 3 %}
                                                <i class="fas fa-award text-warning"></i>
                                            {% endif %}
                                            {{loop.index}}
                                        </td>
                                        <td><strong>{{name}}</strong></td>
                                        <td><span class="badge bg-primary">{{stats["elo"]}}</span></td>
                                        <td><span class="badge bg-success">{{stats["wins"]}}</span></td>
                                        <td><span class="badge bg-danger">{{stats["losses"]}}</td>
                                        <td>
                                            {% set total = stats["wins"] + stats["losses"] %}
                                            {% if total > 0 %}
                                                {{"%.1f"|format(stats["wins"] / total * 100)}}%
                                            {% else %}
                                                0%
                                            {% endif %}
                                        </td>
                                        <td>
                                            <a href="/player/{{name}}" class="btn btn-sm btn-outline-primary">
                                                <i class="fas fa-user"></i> Profile
                                            </a>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        {% else %}
                        <div class="text-center py-4">
                            <i class="fas fa-users fa-3x text-muted mb-3"></i>
                            <p class="text-muted">No players yet. Add some players to get started!</p>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>

        <!-- Action Cards -->
        <div class="row">
            <div class="col-md-6 col-lg-3 mb-4">
                <div class="card stat-card h-100">
                    <div class="card-body text-center">
                        <i class="fas fa-user-plus fa-3x text-primary mb-3"></i>
                        <h5>Add Player</h5>
                        <form action="/add_player" method="post" class="mt-3">
                            <div class="input-group">
                                <input type="text" name="name" class="form-control" placeholder="Player Name" required>
                                <button type="submit" class="btn btn-primary">
                                    <i class="fas fa-plus"></i>
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>

            <div class="col-md-6 col-lg-3 mb-4">
                <div class="card stat-card h-100">
                    <div class="card-body text-center">
                        <i class="fas fa-user-minus fa-3x text-danger mb-3"></i>
                        <h5>Remove Player</h5>
                        <form action="/remove_player" method="post" class="mt-3">
                            <div class="input-group">
                                <select name="name" class="form-select" required>
                                    <option value="">Select Player</option>
                                    {% for name, stats in players %}
                                    <option value="{{name}}">{{name}}</option>
                                    {% endfor %}
                                </select>
                                <button type="submit" class="btn btn-danger">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>

            <div class="col-md-6 col-lg-3 mb-4">
                <div class="card stat-card h-100">
                    <div class="card-body text-center">
                        <i class="fas fa-gamepad fa-3x text-success mb-3"></i>
                        <h5>Report Match</h5>
                        <button class="btn btn-success mt-3" data-bs-toggle="modal" data-bs-target="#matchModal">
                            <i class="fas fa-plus"></i> Report Match
                        </button>
                    </div>
                </div>
            </div>

            <div class="col-md-6 col-lg-3 mb-4">
                <div class="card stat-card h-100">
                    <div class="card-body text-center">
                        <i class="fas fa-calendar-alt fa-3x text-info mb-3"></i>
                        <h5>Quick Actions</h5>
                        <div class="d-grid gap-2">
                            <a href="/weekly_matchups" class="btn btn-info btn-sm">
                                <i class="fas fa-random"></i> Generate Matchups
                            </a>
                            <a href="/schedule_matches" class="btn btn-warning btn-sm">
                                <i class="fas fa-calendar"></i> Full Schedule
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Match Report Modal -->
    <div class="modal fade" id="matchModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-gamepad me-2"></i>Report Match</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <form action="/report_match" method="post">
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <label class="form-label">Player 1</label>
                                <select name="player1" class="form-select" required>
                                    <option value="">Select Player 1</option>
                                    {% for name, stats in players %}
                                    <option value="{{name}}">{{name}}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="col-md-6 mb-3">
                                <label class="form-label">Player 2</label>
                                <select name="player2" class="form-select" required>
                                    <option value="">Select Player 2</option>
                                    {% for name, stats in players %}
                                    <option value="{{name}}">{{name}}</option>
                                    {% endfor %}
                                </select>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <label class="form-label">Score 1</label>
                                <input type="number" name="score1" class="form-control" min="0" required>
                            </div>
                            <div class="col-md-6 mb-3">
                                <label class="form-label">Score 2</label>
                                <input type="number" name="score2" class="form-control" min="0" required>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="submit" class="btn btn-success">
                            <i class="fas fa-check"></i> Report Match
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function toggleDarkMode() {
            document.body.classList.toggle('dark-mode');
            localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
        }
        
        // Load dark mode preference
        if (localStorage.getItem('darkMode') === 'true') {
            document.body.classList.add('dark-mode');
        }
    </script>
</body>
</html>
"""

TEMPLATE_MATCHUPS = """
<!DOCTYPE html>
<html>
<head>
    <title>Weekly Matchups</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; text-align: center; }
        ul { list-style: none; padding: 0; }
        li { background-color: #ecf0f1; margin: 10px 0; padding: 15px; border-radius: 5px; text-align: center; font-size: 18px; font-weight: bold; }
        .back-link { display: inline-block; padding: 10px 20px; background-color: #3498db; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }
        .back-link:hover { background-color: #2980b9; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📅 Weekly Matchups</h1>
        <ul>
        {% for p1, p2 in pairs %}
            <li>{{p1}} 🆚 {{p2}}</li>
        {% endfor %}
        </ul>
        <a href="/" class="back-link">← Back to Rankings</a>
    </div>
</body>
</html>
"""

TEMPLATE_STATISTICS = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 Statistics - Ping Pong League</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .stat-card { transition: transform 0.2s; }
        .stat-card:hover { transform: translateY(-2px); }
        .chart-container { position: relative; height: 300px; }
    </style>
</head>
<body>
    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-table-tennis me-2"></i>Ping Pong League
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/">
                    <i class="fas fa-home me-1"></i>Home
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row mb-4">
            <div class="col-12">
                <h1 class="display-4 text-center mb-4">
                    <i class="fas fa-chart-bar me-3"></i>League Statistics
                </h1>
            </div>
        </div>

        <!-- Advanced Statistics Table -->
        <div class="row mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h3 class="mb-0"><i class="fas fa-trophy me-2"></i>Advanced Player Statistics</h3>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-hover">
                                <thead>
                                    <tr>
                                        <th>Player</th>
                                        <th>Wins</th>
                                        <th>Losses</th>
                                        <th>Win%</th>
                                        <th>Points For</th>
                                        <th>Points Against</th>
                                        <th>Games Played</th>
                                        <th>Avg Pts For</th>
                                        <th>Avg Pts Against</th>
                                        <th>ELO Trend</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for name, stats in player_stats.items() %}
                                    <tr>
                                        <td><strong>{{name}}</strong></td>
                                        <td><span class="badge bg-success">{{stats.wins}}</span></td>
                                        <td><span class="badge bg-danger">{{stats.losses}}</span></td>
                                        <td><span class="badge bg-primary">{{stats.win_rate}}%</span></td>
                                        <td>{{stats.points_for}}</td>
                                        <td>{{stats.points_against}}</td>
                                        <td>{{stats.games_played}}</td>
                                        <td>{{stats.avg_points_for}}</td>
                                        <td>{{stats.avg_points_against}}</td>
                                        <td>
                                            {% if stats.elo_trend > 0 %}
                                                <span class="text-success fw-bold">+{{stats.elo_trend}}</span>
                                            {% elif stats.elo_trend < 0 %}
                                                <span class="text-danger fw-bold">{{stats.elo_trend}}</span>
                                            {% else %}
                                                <span class="text-muted">0</span>
                                            {% endif %}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Charts Row -->
        <div class="row mb-4">
            <div class="col-md-6 mb-4">
                <div class="card stat-card h-100">
                    <div class="card-header">
                        <h5><i class="fas fa-chart-pie me-2"></i>Win Rate Distribution</h5>
                    </div>
                    <div class="card-body">
                        <div class="chart-container">
                            <canvas id="winRateChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-6 mb-4">
                <div class="card stat-card h-100">
                    <div class="card-header">
                        <h5><i class="fas fa-chart-line me-2"></i>ELO Trends</h5>
                    </div>
                    <div class="card-body">
                        <div class="chart-container">
                            <canvas id="eloTrendChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Recent Matches -->
        <div class="row mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-info text-white">
                        <h3 class="mb-0"><i class="fas fa-history me-2"></i>Recent Matches</h3>
                    </div>
                    <div class="card-body">
                        {% if recent_matches %}
                        <div class="table-responsive">
                            <table class="table table-hover">
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Player 1</th>
                                        <th>Score</th>
                                        <th>Player 2</th>
                                        <th>Winner</th>
                                        <th>ELO Changes</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for match in recent_matches|reverse %}
                                    <tr>
                                        <td>{{match.date[:10] if match.date else 'Unknown'}}</td>
                                        <td><strong>{{match.player1}}</strong></td>
                                        <td><span class="badge bg-primary fs-6">{{match.score1}} - {{match.score2}}</span></td>
                                        <td><strong>{{match.player2}}</strong></td>
                                        <td><span class="badge bg-success">{{match.winner}}</span></td>
                                        <td>
                                            <small>
                                                <span class="{% if match.elo_change1 > 0 %}text-success{% elif match.elo_change1 < 0 %}text-danger{% else %}text-muted{% endif %}">
                                                    {{match.player1}}: {{match.elo_change1}}
                                                </span><br>
                                                <span class="{% if match.elo_change2 > 0 %}text-success{% elif match.elo_change2 < 0 %}text-danger{% else %}text-muted{% endif %}">
                                                    {{match.player2}}: {{match.elo_change2}}
                                                </span>
                                            </small>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        {% else %}
                        <div class="text-center py-4">
                            <i class="fas fa-gamepad fa-3x text-muted mb-3"></i>
                            <p class="text-muted">No matches recorded yet. Start playing to see statistics!</p>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>

        <!-- Advanced Insights -->
        <div class="row">
            <div class="col-md-6 mb-4">
                <div class="card stat-card">
                    <div class="card-header bg-warning text-dark">
                        <h5><i class="fas fa-lightbulb me-2"></i>Key Insights</h5>
                    </div>
                    <div class="card-body">
                        {% set top_players = player_stats.items()|sort(attribute='1.win_rate', reverse=true) %}
                        {% set most_matches = player_stats.items()|sort(attribute='1.games_played', reverse=true) %}
                        {% set best_offense = player_stats.items()|sort(attribute='1.avg_points_for', reverse=true) %}
                        
                        {% if top_players %}
                        <div class="alert alert-success">
                            <strong>🏆 Highest Win Rate:</strong> {{top_players[0][0]}} ({{top_players[0][1].win_rate}}%)
                        </div>
                        {% endif %}
                        
                        {% if most_matches %}
                        <div class="alert alert-info">
                            <strong>⚡ Most Active:</strong> {{most_matches[0][0]}} ({{most_matches[0][1].games_played}} matches)
                        </div>
                        {% endif %}
                        
                        {% if best_offense %}
                        <div class="alert alert-warning">
                            <strong>🎯 Best Offense:</strong> {{best_offense[0][0]}} ({{best_offense[0][1].avg_points_for}} avg score)
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
            
            <div class="col-md-6 mb-4">
                <div class="card stat-card">
                    <div class="card-header bg-success text-white">
                        <h5><i class="fas fa-fire me-2"></i>Performance Streaks</h5>
                    </div>
                    <div class="card-body">
                        {% for name, stats in player_stats.items() %}
                        {% if stats.games_played > 0 %}
                        <div class="mb-2">
                            <strong>{{name}}:</strong>
                            {% if stats.current_streak > 0 %}
                                <span class="badge bg-success">{{stats.current_streak}} win streak</span>
                            {% elif stats.current_streak < 0 %}
                                <span class="badge bg-danger">{{-stats.current_streak}} loss streak</span>
                            {% else %}
                                <span class="badge bg-secondary">No streak</span>
                            {% endif %}
                            <small class="text-muted">(Longest: {{stats.longest_streak}})</small>
                        </div>
                        {% endif %}
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Win Rate Pie Chart
        const winRateCtx = document.getElementById('winRateChart').getContext('2d');
        new Chart(winRateCtx, {
            type: 'pie',
            data: {
                labels: [{% for name, stats in player_stats.items() %}'{{name}}'{% if not loop.last %},{% endif %}{% endfor %}],
                datasets: [{
                    data: [{% for name, stats in player_stats.items() %}{{stats.win_rate}}{% if not loop.last %},{% endif %}{% endfor %}],
                    backgroundColor: [
                        '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });

        // ELO Trend Line Chart
        const eloTrendCtx = document.getElementById('eloTrendChart').getContext('2d');
        new Chart(eloTrendCtx, {
            type: 'line',
            data: {
                labels: [{% for name, stats in player_stats.items() %}'{{name}}'{% if not loop.last %},{% endif %}{% endfor %}],
                datasets: [{
                    label: 'ELO Trend',
                    data: [{% for name, stats in player_stats.items() %}{{stats.elo_trend}}{% if not loop.last %},{% endif %}{% endfor %}],
                    borderColor: '#36A2EB',
                    backgroundColor: 'rgba(54, 162, 235, 0.1)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    </script>
</body>
</html>
"""

TEMPLATE_MATCH_HISTORY = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📜 Match History - Ping Pong League</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-table-tennis me-2"></i>Ping Pong League
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/">
                    <i class="fas fa-home me-1"></i>Home
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row mb-4">
            <div class="col-12">
                <h1 class="display-4 text-center mb-4">
                    <i class="fas fa-history me-3"></i>Complete Match History
                </h1>
            </div>
        </div>

        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h3 class="mb-0"><i class="fas fa-list me-2"></i>All Matches</h3>
                    </div>
                    <div class="card-body">
                        {% if matches %}
                        <div class="table-responsive">
                            <table class="table table-hover">
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Player 1</th>
                                        <th>Score</th>
                                        <th>Player 2</th>
                                        <th>Winner</th>
                                        <th>ELO Changes</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for match in matches|reverse %}
                                    <tr>
                                        <td>{{match.date[:10] if match.date else 'Unknown'}}</td>
                                        <td><strong>{{match.player1}}</strong></td>
                                        <td><span class="badge bg-primary fs-6">{{match.score1}} - {{match.score2}}</span></td>
                                        <td><strong>{{match.player2}}</strong></td>
                                        <td><span class="badge bg-success">{{match.winner}}</span></td>
                                        <td>
                                            <small>
                                                <span class="{% if match.elo_change1 > 0 %}text-success{% elif match.elo_change1 < 0 %}text-danger{% else %}text-muted{% endif %}">
                                                    {{match.player1}}: {{match.elo_change1}}
                                                </span><br>
                                                <span class="{% if match.elo_change2 > 0 %}text-success{% elif match.elo_change2 < 0 %}text-danger{% else %}text-muted{% endif %}">
                                                    {{match.player2}}: {{match.elo_change2}}
                                                </span>
                                            </small>
                                        </td>
                                        <td>
                                            <form action="/delete_match/{{match.id}}" method="post" class="d-inline" onsubmit="return confirm('Are you sure you want to delete this match? This will recalculate all ELO ratings.')">
                                                <button type="submit" class="btn btn-sm btn-danger">
                                                    <i class="fas fa-trash"></i>
                                                </button>
                                            </form>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        {% else %}
                        <div class="text-center py-4">
                            <i class="fas fa-gamepad fa-3x text-muted mb-3"></i>
                            <p class="text-muted">No matches recorded yet. Start playing to see match history!</p>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

TEMPLATE_PLAYER_PROFILE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{player_name}} - Player Profile</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-table-tennis me-2"></i>Ping Pong League
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/">
                    <i class="fas fa-home me-1"></i>Home
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row mb-4">
            <div class="col-12">
                <h1 class="display-4 text-center mb-4">
                    <i class="fas fa-user me-3"></i>{{player_name}}'s Profile
                </h1>
            </div>
        </div>

        <!-- Player Stats Cards -->
        <div class="row mb-4">
            <div class="col-md-3 mb-3">
                <div class="card text-center bg-primary text-white">
                    <div class="card-body">
                        <i class="fas fa-trophy fa-2x mb-2"></i>
                        <h4>{{player_data.elo}}</h4>
                        <p class="mb-0">Current ELO</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card text-center bg-success text-white">
                    <div class="card-body">
                        <i class="fas fa-check fa-2x mb-2"></i>
                        <h4>{{stats.wins}}</h4>
                        <p class="mb-0">Wins</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card text-center bg-danger text-white">
                    <div class="card-body">
                        <i class="fas fa-times fa-2x mb-2"></i>
                        <h4>{{stats.losses}}</h4>
                        <p class="mb-0">Losses</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card text-center bg-info text-white">
                    <div class="card-body">
                        <i class="fas fa-percentage fa-2x mb-2"></i>
                        <h4>{{stats.win_rate}}%</h4>
                        <p class="mb-0">Win Rate</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Match History -->
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h3 class="mb-0"><i class="fas fa-history me-2"></i>Match History</h3>
                    </div>
                    <div class="card-body">
                        {% if matches %}
                        <div class="table-responsive">
                            <table class="table table-hover">
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Opponent</th>
                                        <th>Score</th>
                                        <th>Result</th>
                                        <th>ELO Change</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for match in matches|reverse %}
                                    <tr>
                                        <td>{{match.date[:10] if match.date else 'Unknown'}}</td>
                                        <td>
                                            {% if match.player1 == player_name %}
                                                {{match.player2}}
                                            {% else %}
                                                {{match.player1}}
                                            {% endif %}
                                        </td>
                                        <td>
                                            {% if match.player1 == player_name %}
                                                <span class="badge bg-primary fs-6">{{match.score1}} - {{match.score2}}</span>
                                            {% else %}
                                                <span class="badge bg-primary fs-6">{{match.score2}} - {{match.score1}}</span>
                                            {% endif %}
                                        </td>
                                        <td>
                                            {% if match.winner == player_name %}
                                                <span class="badge bg-success">Win</span>
                                            {% else %}
                                                <span class="badge bg-danger">Loss</span>
                                            {% endif %}
                                        </td>
                                        <td>
                                            {% if match.player1 == player_name %}
                                                <span class="{% if match.elo_change1 > 0 %}text-success{% elif match.elo_change1 < 0 %}text-danger{% else %}text-muted{% endif %}">
                                                    {{match.elo_change1}}
                                                </span>
                                            {% else %}
                                                <span class="{% if match.elo_change2 > 0 %}text-success{% elif match.elo_change2 < 0 %}text-danger{% else %}text-muted{% endif %}">
                                                    {{match.elo_change2}}
                                                </span>
                                            {% endif %}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        {% else %}
                        <div class="text-center py-4">
                            <i class="fas fa-gamepad fa-3x text-muted mb-3"></i>
                            <p class="text-muted">No matches played yet!</p>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

TEMPLATE_LEADERBOARD_HISTORY = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📈 Leaderboard History - Ping Pong League</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-table-tennis me-2"></i>Ping Pong League
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/">
                    <i class="fas fa-home me-1"></i>Home
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row mb-4">
            <div class="col-12">
                <h1 class="display-4 text-center mb-4">
                    <i class="fas fa-chart-line me-3"></i>Leaderboard History
                </h1>
            </div>
        </div>

        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h3 class="mb-0"><i class="fas fa-trophy me-2"></i>Current Rankings</h3>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-hover">
                                <thead>
                                    <tr>
                                        <th>Rank</th>
                                        <th>Player</th>
                                        <th>ELO</th>
                                        <th>Wins</th>
                                        <th>Losses</th>
                                        <th>Win Rate</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for name, stats in players %}
                                    <tr>
                                        <td>
                                            {% if loop.index == 1 %}
                                                <i class="fas fa-crown text-warning"></i>
                                            {% elif loop.index == 2 %}
                                                <i class="fas fa-medal text-secondary"></i>
                                            {% elif loop.index == 3 %}
                                                <i class="fas fa-award text-warning"></i>
                                            {% endif %}
                                            {{loop.index}}
                                        </td>
                                        <td><strong>{{name}}</strong></td>
                                        <td><span class="badge bg-primary">{{stats["elo"]}}</span></td>
                                        <td><span class="badge bg-success">{{stats["wins"]}}</span></td>
                                        <td><span class="badge bg-danger">{{stats["losses"]}}</span></td>
                                        <td>
                                            {% set total = stats["wins"] + stats["losses"] %}
                                            {% if total > 0 %}
                                                {{"%.1f"|format(stats["wins"] / total * 100)}}%
                                            {% else %}
                                                0%
                                            {% endif %}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

TEMPLATE_SCHEDULE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📅 Match Schedule - Ping Pong League</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-table-tennis me-2"></i>Ping Pong League
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/">
                    <i class="fas fa-home me-1"></i>Home
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row mb-4">
            <div class="col-12">
                <h1 class="display-4 text-center mb-4">
                    <i class="fas fa-calendar me-3"></i>Match Schedule
                </h1>
            </div>
        </div>

        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h3 class="mb-0"><i class="fas fa-list me-2"></i>Round Robin Schedule</h3>
                    </div>
                    <div class="card-body">
                        {% for round_num, round_matches in schedule %}
                        <div class="mb-4">
                            <h5>Round {{round_num + 1}}</h5>
                            <div class="row">
                                {% for p1, p2 in round_matches %}
                                <div class="col-md-6 mb-2">
                                    <div class="card">
                                        <div class="card-body text-center">
                                            <strong>{{p1}}</strong> vs <strong>{{p2}}</strong>
                                        </div>
                                    </div>
                                </div>
                                {% endfor %}
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ---------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
