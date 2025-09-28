# 🏓 Ping Pong League Manager

A Flask-based web application for managing a ping pong league with ELO rating system.

## Features

- **Player Management**: Add and remove players from the league
- **ELO Rating System**: Automatic rating updates based on match results
- **Match Reporting**: Report match results to update player ratings
- **Weekly Matchups**: Generate random weekly matchups for all players
- **Rankings Table**: View current player rankings with wins/losses

## Installation

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   python app.py
   ```

3. Open your browser and go to: `http://localhost:8080`

## How to Use

### Adding Players
- Use the "Add Player" form to add new players to the league
- All new players start with an ELO rating of 1000

### Reporting Matches
- Use the "Report Match" form to record match results
- Enter both player names and the winner's name
- ELO ratings will be automatically updated based on the result

### Weekly Matchups
- Click "Generate Weekly Matchups" to create random pairings
- Players are randomly shuffled and paired up
- If there's an odd number of players, one player will be left out

### ELO Rating System
- Players start with 1000 ELO points
- Ratings are updated after each match using the standard ELO formula
- Higher-rated players gain fewer points for beating lower-rated players
- Lower-rated players gain more points for beating higher-rated players

## Data Storage

Player data is stored in `data.json` file in the same directory as the application.

## Technical Details

- Built with Flask web framework
- Uses JSON for data persistence
- Implements standard ELO rating system with K-factor of 32
- Responsive web design with modern CSS styling
