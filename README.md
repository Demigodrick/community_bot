# Lemmy.zip's Community Bot

## About
This bot works mainly by Users/Admins sending a PM to the bot account, and the bot will then process that PM. 
Some of the admin functions are automatically run, you can set this schedule in the "main.py" file.

## Features
- Welcome PM - the bot scans new applications to the site and sends a PM to the user with helpful info
- Spam/temporary email address scanning for new users
- Email new users between verifying email stage and admin acceptance stage (so new users don't get confused and think they're locked out of their accounts!)
- Poll feature - Admins can create polls and users can vote on them. 
- Banned words scanning - replaces the built in Lemmy slur word filter, instead creating a report for the admin/mod to deal with as appropriate rather than just hiding slur behind "removed". (You can set your own regex for this in the .env file)
- Help functionality. The bot will PM helpul advice, such as the commands it knows. (Admins should use #help to see a full list of commands)
- "Takeover" functionality to allow an admin to assign a community to a different user. Doesn't require the user to have posted in that community.
- Broadcast a message to all the users in your instance (does require some setup though, [message me](https://me.lemmy.zip/@demigodrick) for help with this.) Users can subscribe/unsubscribe from this.
- Feedback code sharing. If like me you want your feedback methods password protected, you can share the password with legitimate users by having the bot PM the password rather than posting it in public spaces.
- "Autopost" - Schedule Pinned Posts - this is open to Admins and Community Mods and will allow the bot to pin a post on a schedule or as a one off. If on a schedule, it will remove the already pinned post before pinning a new one too.
- RSS feeds for communities
- auto-insert blocks for new users
- post tagging enforcement
- literally a bunch of other stuff.



## How to use
You're free to fork this and rewrite it to suit your needs. A lot of stuff was moved out to enable this to be used on any instance, but some things are still hard coded in and a lot of the functions have or haven't been written to be enabled. It's set up as-is to work on Lemmy.zip with all the features.

