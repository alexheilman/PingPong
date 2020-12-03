from flask import Flask, render_template
from flask_mysqldb import MySQL
import os

# pull ClearDB configuration from environment variable
CLEARDB_DATABASE_URL = os.environ.get('CLEARDB_DATABASE_URL')
MYSQL_HOST = CLEARDB_DATABASE_URL[32:59]
MYSQL_USER = CLEARDB_DATABASE_URL[8:22]
MYSQL_PASS = CLEARDB_DATABASE_URL[23:31]
MYSQL_DB   = CLEARDB_DATABASE_URL[60:82]


app = Flask(__name__)

# configure app to ClearDB
app.config['MYSQL_HOST'] = MYSQL_HOST
app.config['MYSQL_USER'] = MYSQL_USER
app.config['MYSQL_PASSWORD'] = MYSQL_PASS
app.config['MYSQL_DB'] = MYSQL_DB
mysql = MySQL(app)


def PostScore(p1_name, p1_score, p2_name, p2_score):
	cur = mysql.connection.cursor()
	cur.execute("INSERT INTO game_log(p1_name, p1_score, p2_name, p2_score)" + \
				"VALUES(%s, %s, %s, %s)", \
				(p1_name, p1_score, p2_name, p2_score))
	mysql.connection.commit()
	cur.close()


@app.route('/')
def index():
	p1_name = 'test'
	p1_score = 4
	p2_name = 'dude'
	p2_score = 21

	PostScore(p1_name, p1_score, p2_name, p2_score)


	return 'Flask' 

if __name__ == '__main__':
	app.run(debug=True)

