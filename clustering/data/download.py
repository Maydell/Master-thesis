import pymysql
import os
from functools import reduce
from operator import add
import math

from data_writer import write_datapoint

TEST_REPLAY=57238

DEBUG = True
VERBOSE = False

def _verbose(arg):
    global VERBOSE, DEBUG
    if VERBOSE or DEBUG:
        print(arg)

def _debug(arg):
    global DEBUG
    if DEBUG:
        print(arg)


def connect():
    db = pymysql.connect(
            host = os.environ["MASTER_RDS_HOSTNAME"],
            port = int(os.environ["MASTER_RDS_PORT"]),
            user = os.environ["MASTER_RDS_USERNAME"],
            passwd = os.environ["MASTER_RDS_PASSWORD"],
            db = os.environ["MASTER_RDS_DB_NAME"],
            charset='utf8')
    cur = db.cursor()
    return cur

def aggregate_replay(cur, replay_id):
    # Get players in replay
    cur.execute("""
        SELECT RosterPlayer.player_id, team1_roster=RosterPlayer.roster_id AS team1
        FROM CsMatchInfo
        JOIN RosterPlayer ON (
            RosterPlayer.roster_id = CsMatchInfo.team1_roster 
            OR RosterPlayer.roster_id = CsMatchInfo.team2_roster
        )
        WHERE replay_id=%s
    """, replay_id)

    players = cur.fetchall()
    player_team = { p[0]: p[1] for p in players }
    player_ids = [ p[0] for p in players ]

    # Get list of round IDs
    cur.execute("""
        SELECT id FROM CsRound
        WHERE replay_id=%s
        ORDER BY round_nr ASC
    """, replay_id)

    rounds = cur.fetchall()
    round_ids = [ r[0] for r in rounds ]

    for r in round_ids:
        _verbose(f'Round: {r}')
        _verbose('=========')

        positions_per_second = get_player_positions(r)

        player_distances = get_team_center_distances(positions_per_second, player_team, player_ids)

        player_cash = get_player_cash(r, player_team, player_ids)

        for p in player_ids:
            write_datapoint(replay_id, r, p, player_distances[p])

def get_player_cash(r, player_team, player_ids):
    # Calculate cash spent by each player

    # Get player cash each time it changes
    cur.execute("""
        SELECT player_id, cash
        FROM CsEconomy
        WHERE round_id=%s
        ORDER BY round_clock ASC
    """, r)

    cash_points = cur.fetchall()

    # Sum negative changes to get spent cash
    cash_spent = {p_id: {"spent": 0, "current": 0} for p_id in player_ids}

    for cash_point in cash_points:
        p_id = cash_point[0]
        c = int(cash_point[1])
        if p_id in cash_spent:
            if c < cash_spent[p_id]["current"]:
                # Negative change
                cash_spent[p_id]["spent"] += cash_spent[p_id]["current"] - c
            
            cash_spent[p_id]["current"] = c
        else:
            raise ValueError("Invalid player id in cash points")
    
    # Calculate team average

    print(f'Cash spent: {cash_spent}')

def get_team_center_distances(positions_per_second, player_team, player_ids):
    distance_per_second = {} # Distance to team center per second

    # Loop over each second where a player position is found
    for round_clock in positions_per_second:
        # Add each player position at this time
        team_pos = {0: (0, 0, 0), 1: (0, 0, 0)}
        n_positions = {0: 0, 1: 0}

        for p_id, player_pos in positions_per_second[round_clock].items():
            team = player_team[p_id]
            team_pos[team] = (team_pos[team][0] + player_pos[0], team_pos[team][1] + player_pos[1], team_pos[team][2] + player_pos[2])
            n_positions[team] += 1

        team_centers = {}
        # Mean team position
        for t_id, pos in team_pos.items():
            if n_positions[t_id] == 0:
                continue
            
            pos = (pos[0] / n_positions[t_id], pos[1] / n_positions[t_id], pos[2] / n_positions[t_id])
            team_centers[t_id] = pos

        # Calculate distance to team center for each player at current round_clock
        for p_id, player_pos in positions_per_second[round_clock].items():
            team_center = team_centers[player_team[p_id]]
            distance = math.sqrt(
                    (team_center[0] - player_pos[0])**2 +
                    (team_center[1] - player_pos[1])**2 +
                    (team_center[2] - player_pos[2])**2)

            if round_clock in distance_per_second:
                distance_per_second[round_clock][p_id] = distance
            else:
                distance_per_second[round_clock] = {p_id: distance}
    # !Loop over each second where a player position is found

    return avg_player_distances(distance_per_second, player_team, player_ids)

def avg_player_distances(distance_per_second, player_team, player_ids):
    # Average distances for each player this round
    player_distances = {}
    for p_id in player_ids:
        distance = 0
        n_distances = 0
        for round_clock, distances in distance_per_second.items():
            if p_id in distances:
                n_distances += 1
                distance += distances[p_id]
        
        # Average player distance
        if n_distances == 0:
            raise Error("Missing positions")

        distance /= n_distances
        player_distances[p_id] = distance

    # Normalize player avg distances
    player_distances_sum = {}
    for i in [0, 1]:
        player_distances_sum[i] = sum([d**2 for p_id, d in player_distances.items() if player_team[p_id] == i]) 

    player_distances = {p_id: d/math.sqrt(player_distances_sum[player_team[p_id]]) for p_id, d in player_distances.items()}

    return player_distances

def get_player_positions(r):
    # Get player positions this round
    cur.execute("""
        SELECT round_clock, pos_x, pos_y, pos_z, player_id
        FROM CsPosition
        WHERE round_id=%s
        ORDER BY round_clock ASC
    """, r)

    positions = cur.fetchall()

    #positions_per_second = {
        #0: { p_id: () for p_id in player_ids if player_team[p_id] == 0},
        #1: { p_id: () for p_id in player_ids if player_team[p_id] == 1}
    #}

    positions_per_second = {}

    # Save each player position at each round_clock
    for pos in positions:
        p_id = pos[4]
        if pos[0] in positions_per_second:
            positions_per_second[pos[0]][p_id] = pos[1:4]
        else:
            positions_per_second[pos[0]] = {p_id: pos[1:4]}

    return positions_per_second


if __name__ == '__main__':
    cur = connect()
    try:
        aggregate_replay(cur, TEST_REPLAY)
    except Exception as e:
        print('Encountered error when aggregating replay [' + str(TEST_REPLAY) + ']: ' + str(e))

