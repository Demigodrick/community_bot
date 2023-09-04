# community_bot


## Features
- Poll feature - Admins can create polls and users can vote on them
- Help functionality. The bot will PM helpul advice.
- Welcome PM - the bot scans new applications to the site and sends a PM to the user with helpful info
- Create a community. The bot will allow a user with a score above one you set to create a community via PM. The bot will add the user as a mod then de-mod itself. Useful for turning off open community applications and allowing trusted members to create communities.
- Email new users between verifying email stage and admin acceptance stage (so new users don't get confused and think they're locked out of their accounts!)
- A bunch of other helpful tools for Admins

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

5. `source venv/bin/activate`

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

You can also build and run via docker.
