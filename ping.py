from flask import Flask, redirect, url_for

app1 = Flask(__name__)

# Defining the home page of our site
@app1.route("/")  # this sets the route to this page
def home():
	return "<h1>HELLO</h1> Hello! this is the main ppage "  # some basic inline html

#@app.route("/<name>")
#def user(name):
#	return f"Hello {name}!"

@app1.route("/admin")
def admin():
	return redirect(url_for(""))

if __name__ == "__main__":
	app1.run()




