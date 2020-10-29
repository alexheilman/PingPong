from flask import Flask, redirect, url_for, render_template, request
import numpy as np
import pandas as pd
import datetime
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
# Needed each time in case previous games need to be removed
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

        #calculate ELO probability of each player winning
        p1_rating = df.iloc[i-1, np.where(df.columns.values == p1_name)[0][0]]
        p2_rating = df.iloc[i-1, np.where(df.columns.values == p2_name)[0][0]]

        prob_p1_win = 1/(1+10**((p2_rating-p1_rating)/400))
        prob_p2_win = 1/(1+10**((p1_rating-p2_rating)/400))

        #update player ratings
        if p1_score > p2_score:
            df.iloc[i, np.where(df.columns.values == p1_name)[0][0]] = p1_rating + round(32*(1-prob_p1_win))
            df.iloc[i, np.where(df.columns.values == p2_name)[0][0]] = p2_rating + round(32*(0-prob_p2_win))
        elif p1_score == p2_score:
            pass
        else:
            df.iloc[i, np.where(df.columns.values == p1_name)[0][0]] = p1_rating + round(32*(0-prob_p1_win))
            df.iloc[i, np.where(df.columns.values == p2_name)[0][0]] = p2_rating + round(32*(1-prob_p2_win))

    return df


def GameLogToLeaderboard(df):
    board = pd.DataFrame(columns = ['Player', 'Rating', 'Games', 'Wins', 'Losses'])

    # pull data from game_log for every player [i]
    for i in range(5, df.shape[1]):
        wins = 0
        for j in range(1, df.shape[0]):
            if df.iloc[j,i] > df.iloc[j-1,i]:
                wins += 1
        losses = 0
        for j in range(1, df.shape[0]):
            if df.iloc[j,i] < df.iloc[j-1,i]:
                losses += 1

        row = pd.DataFrame([[df.columns.values[i], int(df.iloc[-1,i]), wins+losses, wins, losses]], \
            columns = ['Player', 'Rating', 'Games', 'Wins', 'Losses'])

        board = pd.concat([board,row])

    board = board.sort_values(by=['Rating'], ascending = False)

    return board


def AddPlayer(name):
    gl = DownloadDF('game_log.csv')

    if name not in gl.columns.values[5:]:
        gl[name] = np.nan
        gl.iloc[0, gl.shape[1]-1] = 1500
    else:
        pass

    UploadDF(gl, 'game_log.csv')


def SubmitScore(p1_name, p1_score, p2_name, p2_score):
    gl = DownloadDF('game_log.csv')

    # empty new row
    gl = gl.reindex(gl.index.tolist() + list(range(gl.shape[0], gl.shape[0]+1)))

    ts = str(datetime.datetime.now())
    ts_format = ts[:10] + "_" + str(int(ts[11:13])-5) + ":" + ts[14:16]

    gl.iloc[-1,0] = ts_format
    gl.iloc[-1,1] = p1_name
    gl.iloc[-1,2] = p1_score
    gl.iloc[-1,3] = p2_name
    gl.iloc[-1,4] = p2_score

    UploadDF(gl, 'game_log.csv')


def CheckRatings(p1_name, p2_name):
    gl = DownloadDF('game_log.csv')
    gl = PopulateRatings(gl)
    lb = GameLogToLeaderboard(gl)
    
    #calculate ELO probability of each player winning
    p1_rating = lb.loc[lb['Player'] == p1_name, 'Rating'].values[0]
    p2_rating = lb.loc[lb['Player'] == p2_name, 'Rating'].values[0]

    prob_p1_win = 1/(1+10**((p2_rating-p1_rating)/400))
    prob_p2_win = 1/(1+10**((p1_rating-p2_rating)/400))

    #calculate rating change
    p1_win = round(32*(1-prob_p1_win))
    p2_lose = round(32*(0-prob_p2_win))
    p2_win = round(32*(1-prob_p2_win))
    p1_lose = round(32*(0-prob_p1_win))

    return p1_win, p1_lose, p2_win, p2_lose


# ---------
#   Flask
# ---------
app = Flask(__name__)

player_list = []

@app.route("/", methods=["POST", "GET"])
def home():
    gl = DownloadDF('game_log.csv')
    gl = PopulateRatings(gl)
    lb = GameLogToLeaderboard(gl)

    # registration completion routes home, update global players list
    # for use in "Submit Score" page to save a AWS pull request
    global player_list
    player_list = lb.sort_values(by=['Player'])
    player_list = player_list['Player']

    if request.method == "POST":
        player = request.form.get("player")
        return redirect(url_for("user", name=player))
    else:
        return render_template("index.html", players = player_list,\
                                tables=[lb.to_html(index=False)])


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
        if p1_name != p2_name:
            SubmitScore(p1_name, p1_score, p2_name, p2_score)
        return redirect(url_for("home"))
    else:
        return render_template("submit_score.html", players = player_list)


@app.route("/calculator", methods=["POST", "GET"])
def calculator():
    p1_win = 0
    p1_lose = 0
    p2_win = 0
    p2_lose = 0
    p1_name = ''
    p2_name = ''

    if request.method == "POST":
        p1_name = request.form.get("p1_name")
        p2_name = request.form.get("p2_name")

        p1_win, p1_lose, p2_win, p2_lose = CheckRatings(p1_name, p2_name)
        
        return render_template("calculator.html", players = player_list, \
            p1_win = p1_win, p1_lose = p1_lose, p2_win = p2_win, p2_lose= p2_lose,\
            p1_name = p1_name, p2_name = p2_name)
    else:
        return render_template("calculator.html", players = player_list)


@app.route("/<name>")
def user(name):
    gl = DownloadDF('game_log.csv')
    ul = gl.loc[(gl['P1_Name'] == name) | (gl['P2_Name'] == name)]
    ul = ul.iloc[:,:5]
    ul = ul.astype({'P1_Score':int, 'P2_Score':int})

    return render_template("player_page.html", player = name, \
                            tables=[ul.to_html(index=False)])

if __name__ == "__main__":
    app.run(debug=True)




