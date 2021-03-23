from flask import Flask, redirect, url_for, render_template, request
import numpy as np
import pandas as pd
import datetime
import pytz
import boto3
from io import StringIO
import sys
import os


# ----------
#   AWS S3
# ----------

S3_BUCKET = os.environ.get('S3_BUCKET')
S3_KEY = os.environ.get('S3_KEY')
S3_SECRET= os.environ.get('S3_SECRET')

s3 = boto3.client('s3', aws_access_key_id = S3_KEY, aws_secret_access_key = S3_SECRET)

def DownloadDF(filename):
    csv_obj = s3.get_object(Bucket = S3_BUCKET, Key = filename)
    body = csv_obj['Body']
    csv_string = body.read().decode('utf-8')
    df = pd.read_csv(StringIO(csv_string))
    return df


def UploadDF(df, filename):
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index = False)
    s3.put_object(Bucket = S3_BUCKET , Body = csv_buffer.getvalue(), Key= filename)


# -------------
#   Functions
# -------------

# Ratings populated from start to finish
# Needed for refresh page in case previous games need to be removed
# because future ratings depend on previous ratings
def PopulateRatings(df): 
    for i in range(1, df.shape[0]):

        # initialize everyone else's ranking from their previous ranking
        for j in range(5, df.shape[1]):
            df.iloc[i,j] = df.iloc[i-1,j]

        # overwrite player 1 and player 2 rankings based on outcome
        p1_name = df.iloc[i,1]
        p1_score = df.iloc[i,2]
        p2_name = df.iloc[i,3]
        p2_score = df.iloc[i,4]

        # calculate ELO probability of each player winning
        p1_rating = df.iloc[i-1, df.columns.get_loc(p1_name)]
        p2_rating = df.iloc[i-1, df.columns.get_loc(p2_name)]

        prob_p1_win = 1/(1+10**((p2_rating-p1_rating)/400))
        prob_p2_win = 1/(1+10**((p1_rating-p2_rating)/400))

        # update player ratings
        if p1_score > p2_score:
            df.iloc[i, df.columns.get_loc(p1_name)] = p1_rating + round(32*(1-prob_p1_win))
            df.iloc[i, df.columns.get_loc(p2_name)] = p2_rating + round(32*(0-prob_p2_win))
        elif p1_score == p2_score:
            pass
        else:
            df.iloc[i, df.columns.get_loc(p1_name)] = p1_rating + round(32*(0-prob_p1_win))
            df.iloc[i, df.columns.get_loc(p2_name)] = p2_rating + round(32*(1-prob_p2_win))

    return df


def GameLogToLeaderboard(gl):
    board = pd.DataFrame(columns = ['Rank','Player','Average Z-Score','ELO Rating', 'Z(ELO Rating)', 'Avg Opp ELO','Z(Avg Opp ELO)','Win %','Z(Win %)' ,'Wins', 'Losses'])

    # pull data from game_log for every player [i]
    for i in range(5, gl.shape[1]):
        board = board.reindex(board.index.tolist() + list(range(board.shape[0], board.shape[0]+1)))
        player_name = gl.columns.values[i]
        board.iloc[i-5, board.columns.get_loc('Player')] = player_name
        board.iloc[i-5, board.columns.get_loc('ELO Rating')] = int(gl.iloc[-1,i])

        ul = gl.loc[(gl['P1_Name'] == player_name) | (gl['P2_Name'] == player_name) | (gl['Timestamp'] == 'initialize')]

        # Compute wins & losses 
        wins = 0
        losses = 0
        for j in range(1, ul.shape[0]):
            if ul.iloc[j,i] > ul.iloc[j-1,i]:
                wins += 1
            elif ul.iloc[j,i] < ul.iloc[j-1,i]:
                losses += 1
        board.iloc[i-5, board.columns.get_loc('Wins')] = wins
        board.iloc[i-5, board.columns.get_loc('Losses')] = losses

        # Win percentage
        if (wins + losses) > 0:
            win_percent = wins / (wins + losses)
        else:
            win_percent = 0
        board.iloc[i-5, board.columns.get_loc('Win %')] = win_percent

        # Calculate average opponent ELO rating
        ul = ul.iloc[1:,:5]     # removes "initialize" row
        opponent_sum = 0 
        for j in range(0, ul.shape[0]):
            if ul.iloc[j,1] == player_name:
                opponent_sum = opponent_sum + gl.iloc[-1, gl.columns.get_loc(ul.iloc[j,3])]
            elif ul.iloc[j,3] == player_name:
                opponent_sum = opponent_sum + gl.iloc[-1, gl.columns.get_loc(ul.iloc[j,1])]
        # handle DIV/0 for newly registered players
        if ul.shape[0] > 0:
            board.iloc[i-5, np.where(board.columns.values == 'Avg Opp ELO')[0][0]] \
                = round(opponent_sum / ul.shape[0])
        else:
            board.iloc[i-5, np.where(board.columns.values == 'Avg Opp ELO')[0][0]] = 0

    # Z-Score of ELO Rating
    board['Z(ELO Rating)'] = (board['ELO Rating'] - board["ELO Rating"].mean()) / board["ELO Rating"].std()

    # Z-Score of Average Opponent ELO Rating
    temp = board["Avg Opp ELO"]
    temp = temp.replace(0, np.NaN)
    board['Z(Avg Opp ELO)'] = (board['Avg Opp ELO'] - temp.mean()) / temp.std()

    # Z-Score of win percentage
    board['Z(Win %)'] = (board['Win %'] - board["Win %"].mean()) / board["Win %"].std()


    # Calculate composite rating [Rating + (Avg Opponent - 1500)]
    board['Average Z-Score'] = (board['Z(ELO Rating)'] + board['Z(Avg Opp ELO)'] + board['Z(Win %)']) / 3
    board = board.sort_values(by=['Average Z-Score'], ascending = False)

    # remove player from leaderboard
    board = board[board.Player != 'Seth Brathovd']

    # Add Rank Labels
    board.iloc[0, board.columns.get_loc('Rank')] = 1
    for i in range(1,board.shape[0]):
        if board.iloc[i, board.columns.get_loc('Average Z-Score')] < board.iloc[i-1, board.columns.get_loc('Average Z-Score')]:
            board.iloc[i, board.columns.get_loc('Rank')] = i + 1
        else:
            board.iloc[i, board.columns.get_loc('Rank')] = board.iloc[i-1, board.columns.get_loc('Rank')]

    board = board.astype({'Average Z-Score':float, 'Z(ELO Rating)':float, 'Z(Avg Opp ELO)':float, 'Win %':float,'Z(Win %)':float})
    board = board.round({'Average Z-Score':3, 'Z(ELO Rating)':2, 'Z(Avg Opp ELO)':2,'Win %':2 ,'Z(Win %)':2})

    return board


def AddPlayer(name):
    gl = DownloadDF('game_log.csv')

    if name not in gl.columns.values[5:]:
        gl[name] = 1500
    else:
        pass

    UploadDF(gl, 'game_log.csv')

    lb = GameLogToLeaderboard(gl)
    UploadDF(lb, 'leaderboard.csv')


def AddGame(p1_name, p1_score, p2_name, p2_score):
    gl = DownloadDF('game_log.csv')

    # empty new row
    gl = gl.reindex(gl.index.tolist() + list(range(gl.shape[0], gl.shape[0]+1)))

    # UTC -> CST time conversion
    ts = datetime.datetime.now()
    old_timezone = pytz.timezone("UTC")
    new_timezone = pytz.timezone("US/Central")
    local_ts = old_timezone.localize(ts)
    nts = str(local_ts.astimezone(new_timezone))

    ts_format = nts[:10] + "_" + nts[11:13] + ":" + nts[14:16]

    gl.iloc[-1,0] = ts_format
    gl.iloc[-1,1] = p1_name
    gl.iloc[-1,2] = p1_score
    gl.iloc[-1,3] = p2_name
    gl.iloc[-1,4] = p2_score

    # initialize everyone else's ranking from their previous ranking
    for j in range(5, gl.shape[1]):
        gl.iloc[-1,j] = gl.iloc[-2,j]

    # calculate ELO probability of each player winning
    p1_rating = gl.iloc[-2, gl.columns.get_loc(p1_name)]
    p2_rating = gl.iloc[-2, gl.columns.get_loc(p2_name)]

    prob_p1_win = 1/(1+10**((p2_rating-p1_rating)/400))
    prob_p2_win = 1/(1+10**((p1_rating-p2_rating)/400))

    # update player ratings
    if p1_score > p2_score:
        gl.iloc[-1, gl.columns.get_loc(p1_name)] = p1_rating + round(32*(1-prob_p1_win))
        gl.iloc[-1, gl.columns.get_loc(p2_name)] = p2_rating + round(32*(0-prob_p2_win))
    elif p1_score == p2_score:
        pass
    else:
        gl.iloc[-1, gl.columns.get_loc(p1_name)] = p1_rating + round(32*(0-prob_p1_win))
        gl.iloc[-1, gl.columns.get_loc(p2_name)] = p2_rating + round(32*(1-prob_p2_win))

    return gl


def CheckRatings(p1_name, p2_name):
    gl = DownloadDF('game_log.csv')
    #gl = PopulateRatings(gl)
    #lb = GameLogToLeaderboard(gl)
    lb = DownloadDF('leaderboard.csv')

    gl_p1 = AddGame(p1_name, 21, p2_name, 0)
    gl_p2 = AddGame(p1_name, 0, p2_name, 21)

    lb_p1 = GameLogToLeaderboard(gl_p1)
    lb_p2 = GameLogToLeaderboard(gl_p2)
    
    # change in composite for p1 winning
    p1_win = round(float(lb_p1.loc[lb_p1['Player'] == p1_name, 'Average Z-Score'].values \
            - lb.loc[lb['Player'] == p1_name, 'Average Z-Score'].values),2)
    p2_lose= round(float(lb_p1.loc[lb_p1['Player'] == p2_name, 'Average Z-Score'].values \
            - lb.loc[lb['Player'] == p2_name, 'Average Z-Score'].values),2)

    # change in composite for p2 winning
    p2_win = round(float(lb_p2.loc[lb_p2['Player'] == p2_name, 'Average Z-Score'].values \
            - lb.loc[lb['Player'] == p2_name, 'Average Z-Score'].values),2)
    p1_lose= round(float(lb_p2.loc[lb_p2['Player'] == p1_name, 'Average Z-Score'].values \
            - lb.loc[lb['Player'] == p1_name, 'Average Z-Score'].values),2)

    # change in rank for p1 winning
    p1_win_rank = int(lb_p1.loc[lb_p1['Player'] == p1_name, 'Rank'].values)
    p2_lose_rank= int(lb_p1.loc[lb_p1['Player'] == p2_name, 'Rank'].values) 

    # change in rank for p2 winning
    p2_win_rank = int(lb_p2.loc[lb_p2['Player'] == p2_name, 'Rank'].values)
    p1_lose_rank= int(lb_p2.loc[lb_p2['Player'] == p1_name, 'Rank'].values)

    return p1_win, p1_lose, p2_win, p2_lose, p1_win_rank, p1_lose_rank, p2_win_rank, p2_lose_rank


# ---------
#   Flask
# ---------
app = Flask(__name__)

player_list = []

@app.route("/", methods=["POST", "GET"])
def home():
    gl = DownloadDF('game_log.csv')
    lb = DownloadDF('leaderboard.csv')

    # hide wins and loss quantity
    lb = lb.iloc[:, :9]

    # Pull most recent 10 games to display on homepage
    gl_recent = gl.iloc[-10:, :5]
    gl_recent = gl_recent.astype({'P1_Score':int, 'P2_Score':int})
    gl_recent = gl_recent.sort_values(by=['Timestamp'], ascending = False)

    # registration completion routes home, update global players list
    # for use in "Submit Score" page to save a AWS pull request
    global player_list
    player_list = lb.sort_values(by=['Player'])
    player_list = player_list['Player']


    if request.method == "POST":
        player = request.form.get("player")
        return redirect(url_for("user", name=player))
    else:
        return render_template("home.html", players = player_list,\
                results=[lb.to_html(index=False, justify="center", classes = "table table-bordered table-striped" )], \
                recents=[gl_recent.to_html(index=False, justify="center",classes = "table table-bordered table-striped")])


@app.route("/register", methods=["POST", "GET"])
def register():
    if request.method == "POST":
        new_player = request.form.get("new_player")
        AddPlayer(new_player)
        return redirect(url_for("home"))
    else:
        return render_template("register.html")


@app.route("/submit_score", methods=["POST", "GET"])
def submit():
    if request.method == "POST":
        p1_score = request.form.get("p1_score", type=int)
        p1_name = request.form.get("p1_name")
        p2_score = request.form.get("p2_score", type=int)
        p2_name = request.form.get("p2_name")

        # don't update leaderboard if score is a player vs themself
        if (p1_name != p2_name):
            gl = AddGame(p1_name, p1_score, p2_name, p2_score)
            UploadDF(gl, 'game_log.csv')

            lb = GameLogToLeaderboard(gl)
            UploadDF(lb, 'leaderboard.csv')

        return redirect(url_for("home"))
    else:
        return render_template("submit_score.html", players = player_list)


@app.route("/calculator", methods=["POST", "GET"])
def calculator():
    p1_win = 0
    p1_lose = 0
    p2_win = 0
    p2_lose = 0
    p1_win_rank = 0
    p1_lose_rank = 0
    p2_win_rank = 0
    p2_lose_rank = 0
    p1_name = ''
    p2_name = ''

    if request.method == "POST":
        p1_name = request.form.get("p1_name")
        p2_name = request.form.get("p2_name")

        p1_win, p1_lose, p2_win, p2_lose, p1_win_rank, p1_lose_rank, p2_win_rank, p2_lose_rank = CheckRatings(p1_name, p2_name)
        
        return render_template("calculator.html", players = player_list, \
            p1_win = p1_win, p1_lose = p1_lose, p2_win = p2_win, p2_lose= p2_lose,\
            p1_name = p1_name, p2_name = p2_name, p1_win_rank = p1_win_rank, \
            p1_lose_rank = p1_lose_rank, p2_win_rank = p2_win_rank, p2_lose_rank = p2_lose_rank,)
    else:
        return render_template("calculator.html", players = player_list)


@app.route("/<name>")
def user(name):
    gl = DownloadDF('game_log.csv')
    ul = gl.loc[(gl['P1_Name'] == name) | (gl['P2_Name'] == name)]
    ul = ul.iloc[:,:5]
    ul = ul.astype({'P1_Score':int, 'P2_Score':int})
    ul = ul[::-1]

    return render_template("player_page.html", player = name, \
                            tables=[ul.to_html(index=False, \
                            justify="center", classes = "table table-bordered table-striped")])

@app.route("/refresh", methods=["POST", "GET"])
def refresh():
    gl = DownloadDF('game_log.csv')
    gl = PopulateRatings(gl)
    UploadDF(gl, 'game_log.csv')

    lb = GameLogToLeaderboard(gl)
    UploadDF(lb, 'leaderboard.csv')

    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)




