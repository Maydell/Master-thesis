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

        # Get player positions this round
        cur.execute("""
            SELECT round_clock, pos_x, pos_y, pos_z
            FROM CsPosition
            WHERE round_id=%s
            ORDER BY round_clock ASC
        """, r)

        positions = cur.fetchall()

        positions_per_second = {}
        distance_per_second = {} # Distance to team center per second

        # Save each player position at each round_clock
        for pos in positions:
            if pos[0] in positions_per_second:
                positions_per_second[pos[0]][p_id] = pos[1:4]
            else:
                positions_per_second[pos[0]] = {p_id: pos[1:4]}

        for round_clock in positions_per_second:
            _debug(f'Round clock: {pos[0]}')

            # Add each player position at this time
            team_pos = (0, 0, 0)

            for _, player_pos in positions_per_second[round_clock].items():
                team_pos = (team_pos[0] + player_pos[0], team_pos[1] + player_pos[1], team_pos[2] + player_pos[2])

            # Mean team position
            n_positions = len(positions_per_second[round_clock])

            ## If division by zero, something went wrong earlier
            team_pos = (team_pos[0] / n_positions, team_pos[1] / n_positions, team_pos[2] / n_positions)

            _debug(f'Team center: {team_pos}')

            # Calculate distance to team center for each player at current round_clock
            for p_id, player_pos in positions_per_second[round_clock]:
                distance = math.sqrt(
                        (team_pos[0] - player_pos[1])**2 +
                        (team_pos[1] - player_pos[2])**2 +
                        (team_pos[2] - player_pos[3])**2)

                if round_clock in distance_per_second:
                    distance_per_second[round_clock][p_id] = distance
                else:
                    distance_per_second[round_clock] = {p_id: distance}



        for p_id in player_ids:
            _verbose(f'Player: {p_id}')
            _verbose('--------------')
            attributes = []

            cur.execute("""
                SELECT round_clock, pos_x, pos_y, pos_z
                FROM CsPosition
                WHERE round_id=%s AND player_id=%s
                ORDER BY round_clock ASC
            """, (r, p_id))

            positions = cur.fetchall()

            positions_per_second = {}

            # Save each player position at each round_clock
            for pos in positions:
                if pos[0] in positions_per_second:
                    positions_per_second[pos[0]][p_id] = pos[1:4]
                else:
                    positions_per_second[pos[0]] = {p_id: pos[1:4]}

            for round_clock in positions_per_second:
                _debug(f'Round clock: {pos[0]}')

                # Add each player position at this time
                team_pos = (0, 0, 0)

                for _, player_pos in positions_per_second[round_clock].items():
                    team_pos = (team_pos[0] + player_pos[0], team_pos[1] + player_pos[1], team_pos[2] + player_pos[2])

                # Mean team position
                n_positions = len(positions_per_second[round_clock])

                ## If division by zero, something went wrong earlier
                team_pos = (team_pos[0] / n_positions, team_pos[1] / n_positions, team_pos[2] / n_positions)

                # Distance to team center
                distance = math.sqrt(
                        (team_pos[0] - player_pos[1])**2 +
                        (team_pos[1] - player_pos[2])**2 +
                        (team_pos[2] - player_pos[3])**2)

                attributes.append(distance)

                _debug(f'Player position: ({pos[1]}, {pos[2]}, {pos[3]})')
                _debug(f'Team center: ({team_pos[0]}, {team_pos[1]}, {team_pos[2]})')
                _debug(f'Distance: {distance}')


        # for p in player_ids:
            # write_datapoint(replay_id, r, p)

if __name__ == '__main__':
    cur = connect()
    try:
        aggregate_replay(cur, TEST_REPLAY)
    except Exception as e:
        print('Encountered error when aggregating replay [' + str(TEST_REPLAY) + ']: ' + str(e))

