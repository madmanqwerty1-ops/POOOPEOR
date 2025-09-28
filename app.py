from flask import Flask, render_template_string, request, redirect
import json, os, random, math

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
                "player1": p1,
                "player2": p2,
                "score1": s1,
                "score2": s2,
                "winner": winner,
                "elo_change1": round(new_r1 - r1),
                "elo_change2": round(new_r2 - r2)
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
    
    # Calculate statistics for each player
    player_stats = {}
    for player_name, player_data in players.items():
        player_matches = [m for m in matches if m["player1"] == player_name or m["player2"] == player_name]
        
        wins = player_data["wins"]
        losses = player_data["losses"]
        total_games = wins + losses
        win_rate = (wins / total_games * 100) if total_games > 0 else 0
        
        # Calculate average score
        total_score_for = 0
        total_score_against = 0
        for match in player_matches:
            if match["player1"] == player_name:
                total_score_for += match["score1"]
                total_score_against += match["score2"]
            else:
                total_score_for += match["score2"]
                total_score_against += match["score1"]
        
        avg_score_for = total_score_for / len(player_matches) if player_matches else 0
        avg_score_against = total_score_against / len(player_matches) if player_matches else 0
        
        # Calculate ELO trend (last 5 matches)
        recent_elo_changes = []
        for match in player_matches[-5:]:
            if match["player1"] == player_name:
                recent_elo_changes.append(match["elo_change1"])
            else:
                recent_elo_changes.append(match["elo_change2"])
        
        elo_trend = sum(recent_elo_changes) if recent_elo_changes else 0
        
        player_stats[player_name] = {
            "win_rate": round(win_rate, 1),
            "avg_score_for": round(avg_score_for, 1),
            "avg_score_against": round(avg_score_against, 1),
            "elo_trend": elo_trend,
            "total_matches": len(player_matches)
        }
    
    # Recent matches
    recent_matches = matches[-10:] if matches else []
    
    return render_template_string(TEMPLATE_STATISTICS, 
                                players=players, 
                                player_stats=player_stats, 
                                recent_matches=recent_matches)

# ---------------------
# Templates (inline for simplicity)
# ---------------------
TEMPLATE_INDEX = """
<!DOCTYPE html>
<html>
<head>
    <title>Ping Pong League</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; text-align: center; margin-bottom: 30px; }
        h2 { color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #3498db; color: white; font-weight: bold; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        tr:hover { background-color: #e8f4f8; }
        form { margin: 20px 0; padding: 20px; background-color: #f8f9fa; border-radius: 5px; }
        input[type="text"] { padding: 10px; margin: 5px; border: 1px solid #ddd; border-radius: 4px; width: 200px; }
        input[type="submit"] { padding: 10px 20px; background-color: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; }
        input[type="submit"]:hover { background-color: #2980b9; }
        .matchup-link { display: inline-block; padding: 15px 30px; background-color: #e74c3c; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }
        .matchup-link:hover { background-color: #c0392b; }
        .section { margin: 30px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏓 Ping Pong League</h1>
        
        <div class="section">
            <h2>📊 Rankings</h2>
            <table>
                <tr><th>Rank</th><th>Player</th><th>ELO</th><th>Wins</th><th>Losses</th></tr>
                {% for name, stats in players %}
                <tr>
                    <td>{{loop.index}}</td>
                    <td><strong>{{name}}</strong></td>
                    <td>{{stats["elo"]}}</td>
                    <td>{{stats["wins"]}}</td>
                    <td>{{stats["losses"]}}</td>
                </tr>
                {% endfor %}
            </table>
        </div>

        <div class="section">
            <h2>➕ Add Player</h2>
            <form action="/add_player" method="post">
                <input type="text" name="name" placeholder="Player Name" required>
                <input type="submit" value="Add Player">
            </form>
        </div>

        <div class="section">
            <h2>➖ Remove Player</h2>
            <form action="/remove_player" method="post">
                <input type="text" name="name" placeholder="Player Name" required>
                <input type="submit" value="Remove Player">
            </form>
        </div>

        <div class="section">
            <h2>🏆 Report Match</h2>
            <form action="/report_match" method="post">
                <div style="margin: 10px 0;">
                    <label>Player 1:</label>
                    <select name="player1" required style="padding: 8px; margin: 5px; border: 1px solid #ddd; border-radius: 4px; width: 200px;">
                        <option value="">Select Player 1</option>
                        {% for name, stats in players %}
                        <option value="{{name}}">{{name}}</option>
                        {% endfor %}
                    </select>
                </div>
                <div style="margin: 10px 0;">
                    <label>Player 2:</label>
                    <select name="player2" required style="padding: 8px; margin: 5px; border: 1px solid #ddd; border-radius: 4px; width: 200px;">
                        <option value="">Select Player 2</option>
                        {% for name, stats in players %}
                        <option value="{{name}}">{{name}}</option>
                        {% endfor %}
                    </select>
                </div>
                <div style="margin: 10px 0;">
                    <label>Score 1:</label>
                    <input type="number" name="score1" placeholder="Score" min="0" required style="padding: 8px; margin: 5px; border: 1px solid #ddd; border-radius: 4px; width: 100px;">
                </div>
                <div style="margin: 10px 0;">
                    <label>Score 2:</label>
                    <input type="number" name="score2" placeholder="Score" min="0" required style="padding: 8px; margin: 5px; border: 1px solid #ddd; border-radius: 4px; width: 100px;">
                </div>
                <input type="submit" value="Report Match">
            </form>
        </div>

        <div class="section">
            <h2>📅 Weekly Matchups</h2>
            <a href="/weekly_matchups" class="matchup-link">Generate Weekly Matchups</a>
        </div>

        <div class="section">
            <h2>📊 Statistics</h2>
            <a href="/statistics" class="matchup-link" style="background-color: #27ae60;">View Player Statistics</a>
        </div>
    </div>
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
<html>
<head>
    <title>Player Statistics</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
        .container { max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; text-align: center; margin-bottom: 30px; }
        h2 { color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #3498db; color: white; font-weight: bold; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        tr:hover { background-color: #e8f4f8; }
        .back-link { display: inline-block; padding: 10px 20px; background-color: #3498db; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }
        .back-link:hover { background-color: #2980b9; }
        .stat-card { background-color: #ecf0f1; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .positive { color: #27ae60; font-weight: bold; }
        .negative { color: #e74c3c; font-weight: bold; }
        .neutral { color: #7f8c8d; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Player Statistics</h1>
        
        <h2>📈 Player Performance</h2>
        <table>
            <tr>
                <th>Player</th>
                <th>Win Rate</th>
                <th>Avg Score For</th>
                <th>Avg Score Against</th>
                <th>ELO Trend</th>
                <th>Total Matches</th>
            </tr>
            {% for name, stats in player_stats.items() %}
            <tr>
                <td><strong>{{name}}</strong></td>
                <td>{{stats.win_rate}}%</td>
                <td>{{stats.avg_score_for}}</td>
                <td>{{stats.avg_score_against}}</td>
                <td>
                    {% if stats.elo_trend > 0 %}
                        <span class="positive">+{{stats.elo_trend}}</span>
                    {% elif stats.elo_trend < 0 %}
                        <span class="negative">{{stats.elo_trend}}</span>
                    {% else %}
                        <span class="neutral">0</span>
                    {% endif %}
                </td>
                <td>{{stats.total_matches}}</td>
            </tr>
            {% endfor %}
        </table>

        <h2>🏆 Recent Matches</h2>
        {% if recent_matches %}
        <table>
            <tr>
                <th>Player 1</th>
                <th>Score</th>
                <th>Player 2</th>
                <th>Winner</th>
                <th>ELO Changes</th>
            </tr>
            {% for match in recent_matches|reverse %}
            <tr>
                <td>{{match.player1}}</td>
                <td><strong>{{match.score1}} - {{match.score2}}</strong></td>
                <td>{{match.player2}}</td>
                <td><strong>{{match.winner}}</strong></td>
                <td>
                    <span class="{% if match.elo_change1 > 0 %}positive{% elif match.elo_change1 < 0 %}negative{% else %}neutral{% endif %}">
                        {{match.player1}}: {{match.elo_change1}}
                    </span><br>
                    <span class="{% if match.elo_change2 > 0 %}positive{% elif match.elo_change2 < 0 %}negative{% else %}neutral{% endif %}">
                        {{match.player2}}: {{match.elo_change2}}
                    </span>
                </td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <div class="stat-card">
            <p>No matches recorded yet. Start playing to see statistics!</p>
        </div>
        {% endif %}

        <h2>💡 Insights</h2>
        <div class="stat-card">
            <h3>🏅 Top Performers</h3>
            {% set top_players = player_stats.items()|sort(attribute='1.win_rate', reverse=true) %}
            {% if top_players %}
            <p><strong>Highest Win Rate:</strong> {{top_players[0][0]}} ({{top_players[0][1].win_rate}}%)</p>
            {% endif %}
            
            {% set most_matches = player_stats.items()|sort(attribute='1.total_matches', reverse=true) %}
            {% if most_matches %}
            <p><strong>Most Active:</strong> {{most_matches[0][0]}} ({{most_matches[0][1].total_matches}} matches)</p>
            {% endif %}
            
            {% set best_offense = player_stats.items()|sort(attribute='1.avg_score_for', reverse=true) %}
            {% if best_offense %}
            <p><strong>Best Offense:</strong> {{best_offense[0][0]}} ({{best_offense[0][1].avg_score_for}} avg score)</p>
            {% endif %}
        </div>

        <a href="/" class="back-link">← Back to Rankings</a>
    </div>
</body>
</html>
"""

# ---------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
