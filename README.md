# Lemmy.zip's Community Bot
Note - this is the Lemmy.zip version. For a version for other Instances to run please use (Lemmy Mod Bot) ##link to go here##
RUNNING THIS VERSION WILL NOT WORK ON YOUR INSTANCE WITHOUT CHANGES.

## About
This bot works mainly by Users/Admins sending a PM to the bot account, and the bot will then process that PM. 
Some of the admin functions are automatically run, you can set this schedule in the "main.py" file.

## Features
- Welcome PM - the bot scans new applications to the site and sends a PM to the user with helpful info
- Spam/temporary email address scanning for new users
- Email new users between verifying email stage and admin acceptance stage (so new users don't get confused and think they're locked out of their accounts!)
- Poll feature - Admins can create polls and users can vote on them. 
- Banned words scanning - replaces the built in Lemmy slur word filter, instead creating a report for the admin/mod to deal with as appropriate rather than just hiding slur behind "removed". (You can set your own regex for this in the .env file)
- Help functionality. The bot will PM helpul advice, such as the commands it knows.
- Feedback code sharing. If like me you want your feedback methods password protected, you can share the password with legitimate users by having the bot PM the password rather than posting it in public spaces.
- "Autopost" - Schedule Pinned Posts - this is open to Admins and Community Mods and will allow the bot to pin a post on a schedule or as a one off. If on a schedule, it will remove the already pinned post before pinning a new one too.

### Autopost commands
A typical command would look like `#autopost -c community_name -t post_title -b post_body -d day -h time -f frequency`
- `-c` - This defines the name of the community you are setting this up for. This is the original name of the community when you created it.
- `-t` - This defines the title of the post. You can use the modifiers listed below here.
- `-b` - This is the body of your post. This field is optional, so you don't need to include it if you don't want a body to your post. You can use the modifiers listed below here too.
- `-u` - This defines a URL you can add to your post. This field is optional, so you don't need to include it.
- `-d` - This defines the day of the week you want your thread to be posted on, i.e. `monday`, or you can enter a date you want the first post to occur in YYYYMMDD format, i.e. `20230612` which would be 12th June 2023.
- `-h` - This defines the time of the day you want this thread to be posted, i.e. `12:00`. All times are UTC!
- `-f` - This defines how often your thread will be posted. The options that currently exist are `weekly`, `fortnightly`, or `4weekly`.

There are some modifiers you can use as outlined above:
- `%d` - This will be replaced by the day of the month, i.e. `12`
- `%m` - This will be replaced by the name of the month, i.e. `June`
- `%y` - This will be replaced by the current year, i.e. `2024`
- `%w` - This will be replaced by the day of the week, i.e. `Monday`
For example, having `-t Weekly Thread %d %m` would be created as `Weekly Thread 12 June` (obviously depending on the day it is posted). 
Finally, if you want to delete a scheduled autopost, use the command `#autopostdelete` with the ID number of the autopost, i.e. `#autopostdelete 1`.


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
