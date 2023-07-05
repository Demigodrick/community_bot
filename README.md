# community_bot

## Install

**Clone Repository**

1. `git https://github.com/Demigodrick/community_bot.git`

**Setup python virtual environment**

2. `pip install virtualenv`

**Move into community_bot folder**

3. `cd community_bot`

**Create the virtual environment**

4. `virtualenv venv`

**Active the virtual environment**

5. `source venv/bin/active`

### Install requirements

6. `pip install -r requirements.txt`

### Configure `.env`
**Copy `env.example` to `.env`**

7. `cp .env.example .env`

**Update the .env with your details**

8. `nano .env`

Make sure your bot is an admin on your instance.

Changing LOCAL to False will allow anyone from any instance to create a community on your server.

# Running on a server
I recommend screen (if its not already installed) for running this on a server.

`sudo apt-get install screen`

`screen `

Go to where you've saved the script on the server

`python3 main.py`

Ctrl-A then D to get out of your screen


