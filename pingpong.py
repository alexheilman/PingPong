from flask import Flask, redirect, url_for, render_template, request
import pandas as pd
import datetime
import boto3
from aws import S3_BUCKET, S3_KEY, S3_SECRET
from io import StringIO
import sys


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
    s3.put_object(Bucket = S3_BUCKET , Body = csv_buffer.getvalue(),\
                    Key= filename)

df = DownloadDF('leaderboards/_leaderboard.csv')
gf = DownloadDF('game_history.csv')


def UpdateLeaderboard(p1_name, p1_score, p2_name, p2_score):
    global df
    #increment quantity of games played
    df.loc[df['Player'] == p1_name, 'Games'] += 1
    df.loc[df['Player'] == p2_name, 'Games'] += 1


    #calculate ELO probability of each player winning
    p1_rating = df.loc[df['Player'] == p1_name, 'Rating'].values[0]
    p2_rating = df.loc[df['Player'] == p2_name, 'Rating'].values[0]

    prob_p1_win = 1/(1+10**((p2_rating-p1_rating)/400))
    prob_p2_win = 1/(1+10**((p1_rating-p2_rating)/400))


    if p1_score > p2_score:
        #update player ratings
        df.loc[df['Player'] == p1_name, 'Rating'] = p1_rating + round(32*(1-prob_p1_win))
        df.loc[df['Player'] == p2_name, 'Rating'] = p2_rating + round(32*(0-prob_p2_win))

        #increment wins and losses accordingly
        df.loc[df['Player'] == p1_name, 'Wins'] += 1
        df.loc[df['Player'] == p2_name, 'Losses'] += 1
    elif p1_score == p2_score:
        pass
    else:
        #update player ratings
        df.loc[df['Player'] == p2_name, 'Rating'] = p2_rating + round(32*(1-prob_p2_win))
        df.loc[df['Player'] == p1_name, 'Rating'] = p1_rating + round(32*(0-prob_p1_win))

        #increment wins and losses accordingly
        df.loc[df['Player'] == p2_name, 'Wins'] += 1
        df.loc[df['Player'] == p1_name, 'Losses'] += 1

    df = df.sort_values(by=['Rating'], ascending = False)
    UploadDF(df, 'leaderboards/_leaderboard.csv')

    # save a timestamped copy of the leaderboard
    ts = str(datetime.datetime.now())
    ts_format = ts[:10] + "_" + ts[11:13] + "-" + ts[14:16] + "-" + ts[17:19]
    filename = 'leaderboards/' + ts_format + ' leaderboard.csv'
    UploadDF(df, filename)


def UpdateGameHistory(p1_name, p1_score, p2_name, p2_score):
    global gf
    ts = str(datetime.datetime.now())
    ts_format = ts[:10] + "_" + ts[11:13] + "-" + ts[14:16] + "-" + ts[17:19]

    gf_row = pd.DataFrame( {gf.columns[0]:ts_format,
                            gf.columns[1]:p1_name, 
                            gf.columns[2]:p1_score,
                            gf.columns[3]:p2_name,
                            gf.columns[4]:p2_score}, index=[0])

    gf = gf.append(gf_row)

    gf.to_csv('game_history.csv', index = False)


def AddPlayer(name):
    global df
    df_row = pd.DataFrame( {df.columns[0]:name,
                            df.columns[1]:1500, 
                            df.columns[2]:0,
                            df.columns[3]:0,
                            df.columns[4]:0}, index=[0])
    df = df.append(df_row)

    df = df.sort_values(by=['Rating'], ascending = False)
    UploadDF(df, 'leaderboards/_leaderboard.csv')

    # save a timestamped copy of the leaderboard
    ts = str(datetime.datetime.now())
    ts_format = ts[:10] + "_" + ts[11:13] + "-" + ts[14:16] + "-" + ts[17:19]
    filename = 'leaderboards/' + ts_format + ' leaderboard.csv'
    UploadDF(df, filename)


def CheckRatings(p1_name, p2_name):
    global df

    #calculate ELO probability of each player winning
    p1_rating = df.loc[df['Player'] == p1_name, 'Rating'].values[0]
    p2_rating = df.loc[df['Player'] == p2_name, 'Rating'].values[0]

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

@app.route("/", methods=["POST", "GET"])
def home():
    return render_template("index.html", tables=[df.to_html(index=False)])


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
            UpdateLeaderboard(p1_name, p1_score, p2_name, p2_score)
            UpdateGameHistory(p1_name, p1_score, p2_name, p2_score)
        
        return redirect(url_for("home"))
    else:
        return render_template("submit_score.html", players = df.Player)


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
        
        return render_template("calculator.html", players = df.Player, \
            p1_win = p1_win, p1_lose = p1_lose, p2_win = p2_win, p2_lose= p2_lose,\
            p1_name = p1_name, p2_name = p2_name)
        #return redirect(url_for("calculator"))
    else:
        return render_template("calculator.html", players = df.Player, \
            p1_win = p1_win, p1_lose = p1_lose, p2_win = p2_win, p2_lose= p2_lose,\
            p1_name = p1_name, p2_name = p2_name)

@app.route('/files')
def files():
    s3_resource = boto3.resource('s3')
    my_bucket = s3_resource.Bucket(S3_BUCKET)
    summaries = my_bucket.objects.all()

    return render_template('files.html', my_bucket=my_bucket, files=summaries)


if __name__ == "__main__":
    app.run(debug=True)




