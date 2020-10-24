from flask import Flask, redirect, url_for, render_template, request
import pandas as pd

df = pd.read_csv('temp.csv', sep=',')

app = Flask(__name__)

# Defining the home page of our site
#@app.route("/")  # this sets the route to this page
#def home():
#	return 'home'


def Update(p1_name, p1_score, p2_name, p2_score):
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

    df.to_csv('temp.csv', index = False)

@app.route("/", methods=["POST", "GET"])
def home():
	return render_template("index.html", tables=[df.to_html(index=False)], titles=df.columns.values)


@app.route("/register", methods=["POST", "GET"])
def register():
	return render_template("register.html")


@app.route("/submit_score", methods=["POST", "GET"])
def submit():
	if request.method == "POST":
		p1_score = request.form.get("p1_score", type=int)
		p1_name = request.form.get("p1_name")
		p2_score = request.form.get("p2_score", type=int)
		p2_name = request.form.get("p2_name")

		Update(p1_name, p1_score, p2_name, p2_score)
		
		return redirect(url_for("home"))
	else:
		return render_template("submit_score.html", players = df.Player)
'''
test = ['one', 'two', 'three']
@app.route("/<name>")  # this sets the route to this page
def name(name):
	return render_template("index.html", content=test)

@app.route("/admin")
def admin():
	return redirect(url_for("home"))

@app.route("/<usr>")
def user(usr):
	return f"<h1>{usr}</h1>"
'''

if __name__ == "__main__":
	app.run(debug=True)




