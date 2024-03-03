## ABOUT
## These strings are what is output as the result of a pm, request or action in the code. You should change these to reflect your instance.
## A \n indicates a break/new line. A \n\n indicates two new lines, i.e. the start of a new paragraph.
## Some lines contain variables inside of {} - like {report_id} for example. You probably shouldn't change these, but I'm not your mum so do whatever you want.
## A string should always start and end in "" - failure to do so will probably break the bot.
## Some particularly long strings have been split over lines so they're easier to read for humans. They start and end in brackets, i.e. () - if you use this format, make sure to keep the brackets.
## Some may start with commas or spaces - this is to make sure the message can be read properly. I recommend following the format too so your bot's messages are legible.


## GENERAL ##
GREETING = "Hey,"
PM_SIGNOFF = "I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop."
AUTOPOST_HELP = "If you need any further help getting this working, please contact [Demigodrick](/u/demigodrick@lemmy.zip)."
SUB_ERROR = "Please message [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip) directly to let them know, and they'll sort it out for you."
EMAIL_SUBJECT = "Thanks for signing up to Lemmy.zip!"
BOT_NAME = "ZippyBot"
FEEDBACK_URL = "https://feedback.lemmy.zip"
WELCOME_MESSAGE = ("\n\n # Welcome to Lemmy.zip! \n\n Please take a moment to familiarise yourself with [our Welcome Post](https://lemmy.zip/post/43). (Text that looks like this is a clickable link!) \n\n" 
                    "This post has all the information you'll need to get started on Lemmy, so please have a good read first! \n\n"
                    "Please also take a look at our rules, they are in the sidebar of this instance, or you can view them [here](https://legal.lemmy.zip/docs/code_of_conduct/), or I can send these to you at any time - just send me a message with `#rules`. \n \n"
                    "If you're on a mobile device, you can [tap here](https://m.lemmy.zip) to go straight to our mobile site. \n \n"
                    "Lemmy.zip is 100% funded by user donations, so if you are enjoying your time on Lemmy.zip please [consider donating](https://opencollective.com/lemmyzip).\n \n"
                    "Want to change the theme of the site? You can go to your [profile settings](https://lemmy.zip/settings) (or click the dropdown by your username and select Settings) and scroll down to theme. You'll find a list of themes you can try out and see which one you like the most! \n \n"
                    "You can also set a Display Name that is different from your account username by updating the Display Name field. By default, your Display Name will show up to other users as `@your_username`, but by updating this field it will become whatever you want it to be! \n \n"
                    "If you'd like more help, please reply to this message with `#help` for a list of things I can help with. \n \n")
MOD_ADVICE = ("Here are some tips for getting users to subscribe to your new community!\n"
                "- Try posting a link to your community at [New Communities](/c/newcommunities@lemmy.world) and at [CommunityPromo](/c/communityPromo@lemmy.ca)\n"
                "- Your community is automatically part of the [Lemmy Federate](https://lemmy-federate.com/) project, so it is immediately shared to a bunch of other instances.\n"
                "- Ensure your community has some content. Users are more likely to subscribe if content is already available. (5 to 10 posts is usually a good start)\n"
                "- There are a couple of mod tools you can use to support your community, such as the Autopost feature or RSS feed feature. You can use `#autoposthelp` or `#rsshelp` for more information on these features. \n"
                "- Consistency is key - you need to post consistently and respond to others to keep engagement with your new community up.\n\n"
                "I hope this helps! \n \n")

## REPORTS ##
REPORT_LOCAL = "Thanks for submitting a report. This is just a message to let you know the mods and admins have recieved this report. We'll check if the reported content breaks our [Code of Conduct](https://legal.lemmy.zip/docs/code_of_conduct/) and take action accordingly."
REPORT_REMOTE = "Thanks for submitting a report. As this content is on Lemmy.zip, we'll check if it breaks our [Code of Conduct](https://legal.lemmy.zip/docs/code_of_conduct/) and take action accordinly. Your local admin(s) will also recieve a copy of this report."

## PM REPLIES
INS_RULES = ("These are the current rules for Lemmy.zip. \n \n"
            "- Please abide by the [General Code of Conduct](https://join-lemmy.org/docs/en/code_of_conduct.html) at all times.\n"
            "- Remember the human! (no harassment, threats, etc.)\n"
            "- No racism or other discrimination\n"
            "- No endorsement of hate speech\n"
            "- No self-advertisements or spam\n"
            "- No link-spamming\n"
            "- No content against UK law.\n"
            "- Any NSFW post must be tagged as NSFW. Failure to do so will be given one warning only\n"
            "- Anything that you wouldn’t want your boss or coworkers to see, needs to be tagged NSFW\n"
            "- NSFW also acts as “Content Warning” outside of the specific NSFW communities\n\n"
            "Any posts or comments that are in breach of these rules will be dealt with, and remediation will occur. Whether that be a warning, temporary ban, or permanent ban.\n\n"
            "(TLDR) The crux of it boils down to:\n"
            "- Remember that we are all humans\n"
            "- Don’t be overtly aggressive towards anyone\n"
            "- Try and share ideas, thoughts and criticisms in a constructive way\n"
            "- Tag any NSFW posts as such \n\n")

BOT_COMMANDS = ("These are the commands I currently know:" + "\n\n "
                "- `#help` - See this message. \n "
                "- `#rules` - See the current instance rules. \n"
                "- `#vote` - Vote on an active poll. You'll need to have a vote ID number. An example vote would be `#vote 1 yes` or `#vote 1 no`.\n" 
                "- `#credits` - See who spent their time making this bot work! \n"
                "- `#autopost` - If you moderate a community, you can schedule an automatic post using this option. Use `#autoposthelp` for a full command list. \n"
                "- `#rss` - If you moderate a community, you can use RSS feeds to populate it. Use `#rsshelp` for more information. \n\n")
BOT_ADMIN_COMMANDS = ("As an Admin, you also have access to the following commands: \n"
                        "- `#poll` - Create a poll for users to vote on. Give your poll a name, and you will get back an ID number to users so they can vote on your poll. Example usage: `#poll @Vote for best admin` \n"
                        "- `#closepoll` - Close an existing poll using the poll ID number, for example `#closepoll @1`\n" 
                        "- `#countpoll` - Get a total of the responses to a poll using a poll ID number, for example `#countpoll @1` \n"
                        "- `#takeover` - Add a user as a mod to an existing community. Command is `#takeover` followed by these identifiers in this order: `-community_name` then `-user_id` (use `-self` here if you want to apply this to yourself) \n\n")

