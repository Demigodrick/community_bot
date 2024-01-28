# Lemmy.zip's Community Bot

Note - this is the Lemmy.zip version. For a version for other Instances to run please use (Lemmy Mod Bot) ##link to go here##

RUNNING THIS VERSION WILL NOT WORK ON YOUR INSTANCE WITHOUT CHANGES.
(due to hardcoded functions in this version)


## Features
- Poll feature - Admins can create polls and users can vote on them
- Help functionality. The bot will PM helpul advice.
- Welcome PM - the bot scans new applications to the site and sends a PM to the user with helpful info
- Email new users between verifying email stage and admin acceptance stage (so new users don't get confused and think they're locked out of their accounts!)
- A bunch of other helpful tools for Admins such as matrix notifications on urgent reports, scanning comments and posts for banned words (customisable regex), and allowing community moderators and admins to schedule pinned posts.


## Customisation
Make sure to set the bot account as admin so it can access the user registration and post report functions.

The bot contains a system to allow users to mark reports as urgent via the PM system. This will send a message to matrix. If you don't want to use this system, make sure to set the "MATRIX_FLAG" env setting to "False". If you want to use it, make sure to plug your Matrix room and user details into the env file.

There is also a system for emailing new users - set to false if you don't want this functionality, otherwise put in your SMTP details and ensure you change the EMAIL_SUBJECT string in the "bot_strings.py" file. 
In the default setup the bot is configured to send a plain text email, but you can review the code in bot_query.py and uncomment the html email code instead (remember to comment out the plain text email code) - include your resources in the 
/resources folder before building the dockerfile. You can see how I set the email up with images in the code.





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
