import pymysql
import os
from functools import reduce
from operator import add

from data_writer import write_datapoint

TEST_REPLAY=57238

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
        print(f'Round: {r}')
        print('=========')
        # Get player positions this round

        step = 5 # Look at every {step} round_clock values
        round_clock = step # Don't start at 1, start at {step}

        # Get positions for every {step}th round_clock
        cur.execute("""
            SELECT round_clock, player_id, pos_x, pos_y, pos_z, view_yaw, view_pitch
            FROM CsPosition 
            WHERE round_id=%s 
            AND round_clock >= %s
            AND MOD(round_clock, %s) = 0
            ORDER BY round_clock ASC
        """, (r, round_clock, step))

        positions = cur.fetchall()
        n_positions = len(positions)

        if n_positions % 10 != 0:
            raise Exception('Invalid number of positions: ' + n_positions)

        steps = 0
        position_dict = {}

        # Loop over every distinct round_clock
        for i in range(0, int(n_positions/10)):
            round_clock = (i+1) * step
            print(f'Round clock: {round_clock}')
            print('-------------------------')

            position_dict[round_clock] = {0: {}, 1: {}}

            for p in positions[steps*10:(steps+1)*10]:
                if p[0] != round_clock:
                    raise Exception('Invalid player position')

                player_id = p[1]
                team = player_team[player_id]

                position_dict[round_clock][team][player_id] = p

            steps += 1

            for team in range(0, 2):
                # Calculate team average at current round_clock
                avg_position = (0, 0, 0)

                for _, pos in position_dict[round_clock][team].items():
                    avg_position = list(map(add, avg_position, (pos[2], pos[3], pos[4])))

                n_players = len(position_dict[round_clock][team])
                avg_position = list(map((lambda dim: dim / n_players), avg_position))

                print(f'Avg position of team {team} at {round_clock}: {avg_position}')


            # print(position_dict[round_clock])

        # Average distance to team center

        # for p in player_ids:
            # write_datapoint(replay_id, r, p)

if __name__ == '__main__':
    cur = connect()
    try:
        aggregate_replay(cur, TEST_REPLAY)
    except Exception as e:
        print('Encountered error when aggregating replay [' + TEST_REPLAY + ']: ' + e)

