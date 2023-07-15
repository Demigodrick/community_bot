from pythorhead import Lemmy
from config import settings
import logging
import sqlite3

## TODO
## - email validation
## - finish polls (closure)


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def login():
    global lemmy
    lemmy = Lemmy("https://" + settings.INSTANCE)
    lemmy.log_in(settings.USERNAME, settings.PASSWORD)

    return lemmy

def check_vote_db():
    conn = sqlite3.connect('vote.db')
    curs = conn.cursor()

    #check for votes table or create
    curs.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='votes' ''')

    if curs.fetchone()[0]==1:
        logging.debug("votes table exists, moving on")
        
    else:
        curs.execute('''CREATE TABLE IF NOT EXISTS votes (vote_id INT, username TEXT, vote_result TEXT)''')
        conn.commit
        logging.debug("created votes table")
    
    #check for polls table or create    
    curs.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='polls' ''')

    if curs.fetchone()[0]==1:
        logging.debug("polls table exists, moving on")
        
    else:
        curs.execute('''CREATE TABLE IF NOT EXISTS polls (poll_id INT, poll_name TEST, username TEXT, open TEXT)''')
        conn.commit
        logging.debug("created polls table")

    
    curs.close
    conn.close    
    return
   
def add_vote_to_db(pm_username, vote_id, vote_response):
    conn = sqlite3.connect('vote.db')
    curs = conn.cursor()
    #check vote_id(poll_id in polls table) is valid
    poll_id = int(vote_id)


    curs.execute('''SELECT poll_id, poll_name FROM polls WHERE poll_id=?''', (poll_id,))
    check_valid = curs.fetchone()
    if check_valid is None:
        logging.debug("Submitted vote_id did not match a valid poll_id")
        return "notvalid"

    poll_name = check_valid[1]   

    #check if vote response is already recorded for this user/vote id
    curs.execute('''SELECT vote_id, username FROM votes WHERE vote_id=? AND username=?''',(vote_id, pm_username))

    row = curs.fetchone()
    if row is not None:
        if row:
            logging.debug("Matching vote found")
            return "duplicate"

        
            
    
    sqlite_insert_query = """INSERT INTO votes (vote_id, username, vote_result) VALUES (?, ?, ?);"""
    data_tuple = (vote_id, pm_username, vote_response)
        
    curs.execute(sqlite_insert_query, data_tuple)
    conn.commit()
    curs.close
    conn.close
    logging.debug("Added vote to database")
    return poll_name

def create_poll(poll_name, pm_username): 
    conn = sqlite3.connect('vote.db')
    curs = conn.cursor()

    #find last row of poll table to get ID number
    curs.execute("SELECT * FROM polls ORDER BY poll_id DESC LIMIT 1")
    result = curs.fetchone()
    if result is not None:
        poll_id = int(result[0]) + 1
    else:
        poll_id = 1
    
    isopen = True

    data_tuple = (poll_id, poll_name, pm_username, isopen)
    sqlite_insert_query = """INSERT INTO polls (poll_id, poll_name, username, open) VALUES (?, ?, ?, ?);"""
    curs.execute(sqlite_insert_query, data_tuple)
    conn.commit()
    curs.close
    conn.close
    logging.debug("Added poll to database with ID number " + str(poll_id))
    return poll_id



def check_pms():
    try:
        pm = lemmy.private_message.list(True, 1)

        private_messages = pm['private_messages']
    except:
        logging.info("Error with connection, retrying...")
        login()
        return

    for pm in private_messages:
        pm_sender = pm['private_message']['creator_id']
        pm_username = pm['creator']['name']
        pm_context = pm['private_message']['content']
        pm_id = pm['private_message']['id']

        output = lemmy.user.get(pm_sender)
        user_score = output['person_view']['counts']['comment_score']
        user_local = output['person_view']['person']['local']
        user_admin = output['person_view']['person']['admin']

        logging.debug(pm_username + " (" + str(pm_sender) + ") sent " + pm_context + " - user score is " + str(user_score) + " " + str(user_admin))

        if user_local != settings.LOCAL:
            lemmy.private_message.create("Hey, " + pm_username + f". This bot is only for users of {settings.INSTANCE}. "
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#help":
            if user_admin == True:
                lemmy.private_message.create("Hey, " + pm_username + ". These are the commands I currently know:" + "\n\n "
                                                                            "- `#help` - See this message. \n "
                                                                            "- `#rules` - See the current instance rules."
                                                                            "- `#score` - See your user score. \n "
                                                                            "- `#create` - Create a new community. Use @ to specify the name of the community you want to create, for example `#create @bot_community`. \n"
                                                                            "- `#vote` - Vote on an active poll. You'll need to have a vote ID number. An example vote would be `#vote @1 @yes` or `#vote @1 @no`.\n" 
                                                                            "- `#credits` - See who spent their time making this bot work!"
                                                                            "\n\n As an Admin, you also have access to the following commands: \n"
                                                                            "- `#poll` - Create a poll for users to vote on. Give your poll a name, and you will get back an ID number to users so they can vote on your poll. Example usage: `#poll @Vote for best admin` \n"
                                                                            "- `#closepoll` - Close an existing poll using the poll ID number, for example `#closepoll @1`" 
                                                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            else:
                lemmy.private_message.create("Hey, " + pm_username + ". These are the commands I currently know:" + "\n\n "
                                                                            "- `#help` - See this message. \n "
                                                                            "- `#rules` - See the current instance rules."
                                                                            "- `#score` - See your user score. \n "
                                                                            "- `#create` - Create a new community. Use @ to specify the name of the community you want to create, for example `#create @bot_community`. \n"
                                                                            "- `#vote` - Vote on an active poll. You'll need to have a vote ID number. An example vote would be `#vote @1 @yes` or `#vote @1 @no`.\n" 
                                                                            "- `#credits` - See who spent their time making this bot work!"
                                                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue


        if pm_context == "#score":
            lemmy.private_message.create("Hey, " + pm_username + ". Your comment score is " + str(user_score) + ". \n \n I am a Bot. If you have any "
                                                                "queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#rules":
            lemmy.private_message.create("Hey, " + pm_username + ". These are the current rules for Lemmy.zip. \n \n"
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
                                                                    "- Tag any NSFW posts as such"                                       
                                                                    "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue


        if pm_context == "#credits":
            lemmy.private_message.create("Hey, " + pm_username + ". This bot was built with help and support from various community members and contributers: \n\n"
                                                                "- Demigodrick - Original Creator\n"
                                                                "- Sami - Support with original idea and implementation \n"
                                                                "- TheDuude (sh.itjust.works) - Refactoring of code and support with improving inital implementation \n"
                                                                "- efwis - code contributions regarding new user database \n\n"
                                                                "I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue


        if pm_context.split(" @")[0] == "#create":
            community_name = pm_context.split("@")[1]

            # check user score
            if user_score < int(settings.SCORE):
                lemmy.private_message.create("Hey, " + pm_username + ". Your comment score is too low to create a "
                                                                        "community. Please interact with other "
                                                                        "communities first. You can check your score at "
                                                                        "any time by sending me a message with `#score` "
                                                                        "and I will let you know!"  "\n \n I am a Bot. "
                                                                        "If you have any queries, please contact ["
                                                                        "Demigodrick](/u/demigodrick@lemmy.zip) or ["
                                                                        "Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            # check if it already exists
            check_community = lemmy.discover_community(community_name)

            if check_community is not None:
                lemmy.private_message.create("Hey, " + pm_username + ". Sorry, it looks like the community you are "
                                                                        "trying to create already exists. \n \n I am a "
                                                                        "Bot. If you have any queries, please contact ["
                                                                        "Demigodrick](/u/demigodrick@lemmy.zip) or ["
                                                                        "Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            # create community - add user and remove bot as mod
            lemmy.community.create(community_name, community_name)
            community_id = lemmy.discover_community(community_name)
            lemmy.community.add_mod_to_community(True, community_id, pm_sender)
            lemmy.community.add_mod_to_community(False, community_id, settings.BOT_ID)

            lemmy.private_message.create("Hey, " + pm_username + ". Your new community, [" + community_name + "](/c/" + community_name + "), has been created. You can now set this community up to your liking. " 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context.split(" @")[0] == "#vote":
            vote_id = pm_context.split("@")[1]
            vote_response = pm_context.split("@")[2]

            db_response = add_vote_to_db(pm_username,vote_id,vote_response) 

            if db_response == "duplicate":
                lemmy.private_message.create("Hey, " + pm_username + ". Oops! It looks like you've already voted on this poll. Votes can only be counted once. " 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if db_response == "notvalid":
                lemmy.private_message.create("Hey, " + pm_username + ". Oops! It doesn't look like the poll you've tried to vote on exists. Please double check the vote ID and try again." 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            else:
                lemmy.private_message.create("Hey, " + pm_username + ". Your vote has been counted on the '" + db_response + "' poll . Thank you for voting! " 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue


        if pm_context.split(" @")[0] == "#poll":
            if user_admin == True:
                poll_name = pm_context.split("@")[1]
                poll_id = create_poll(poll_name, pm_username) 
                lemmy.private_message.create("Hey, " + pm_username + ". Your poll has been created with ID number " + str(poll_id) + ". You can now give this ID to people and they can now cast a vote using the `#vote` operator." 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
            else:
                lemmy.private_message.create("Hey, " + pm_username + ". You need to be an instance admin in order to create a poll."
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)


        #keep this at the bottom
        else:
            lemmy.private_message.create("Hey, " + pm_username + ". Sorry, I did not understand your request. Please "
                                                                 "try again or use `#help` for a list of commands. \n "
                                                                 "\n I am a Bot. If you have any queries, "
                                                                 "please contact [Demigodrick]("
                                                                 "/u/demigodrick@lemmy.zip) or [Sami]("
                                                                 "/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue


def check_user_db():
    conn = sqlite3.connect('users.db')
    curs = conn.cursor()
    
    #check for users table or create
    curs.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='users' ''')

    if curs.fetchone()[0]==1:
        logging.debug("users table exists, moving on")
        
    else:
        curs.execute('''CREATE TABLE IF NOT EXISTS users (local_user_id INT, public_user_id INT, username TEXT, has_posted INT, has_had_pm INT)''') #local_user_id, public_user_id, username, has_posted, has_had_pm,
        conn.commit
        logging.debug("created users table")

    curs.close
    conn.close    
    return


def get_new_users():
    try:
        output = lemmy.admin.list_applications(unread_only="true")
        new_apps = output['registration_applications']
    except:
        logging.info("Error with connection, retrying...")
        login()
        return

    for output in new_apps:

        #something in here about filtering out email addresses
        local_user_id = output['registration_application']['local_user_id']
        username = output['creator']['name']
        #email = output['creator_local_user']['email']
        public_user_id = output['creator_local_user']['person_id']

        if update_registration_db(local_user_id, username, public_user_id) == "new_user":
            logging.debug("sending new user a pm")
            lemmy.private_message.create("Hey, " + username + ". \n \n # Welcome to Lemmy.zip! \n \n Please take a moment to familiarise yourself with [our Welcome Post](https://lemmy.zip/post/43)." 
                                                            "This post has all the information you'll need to get started on Lemmy, so please have a good read first! \n \n"
                                                            "Please also take a look at our rules, they are in the sidebar of this instance. I can send these to you at any time, just send me a message with `#rules`. \n \n"
                                                            "If you're on a mobile device, you can [tap here](https://m.lemmy.zip) to go straight to our mobile site. \n \n"
                                                            "Lemmy.zip is 100% funded by user donations, so if you are enjoying your time on Lemmy.zip please [consider donating](https://opencollective.com/lemmyzip).\n \n"
                                                            "If you'd like more help, please reply to this message with `#help` for a list of things I can help with. \n \n"
                                                            "I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip) via email to `hello@lemmy.zip`. Beep Boop. ", public_user_id)
        continue

def update_registration_db(local_user_id, username, public_user_id):
    conn = sqlite3.connect('users.db')
    curs = conn.cursor()
    #search db for matching user id local_user_id, public_user_id, username, has_posted, has_had_pm,
    

    curs.execute('''SELECT local_user_id FROM users WHERE local_user_id=?''', (local_user_id,))
    id_match = curs.fetchone()

    if id_match is not None:
        logging.debug("Matching ID found, ignoring")
        return "duplicate"
    
    if id_match is None:
        logging.debug("User ID did not match an existing user ID, adding")       
        sqlite_insert_query = """INSERT INTO users (local_user_id, public_user_id, username) VALUES (?, ?, ?);"""
        data_tuple = (local_user_id, public_user_id, username)
        
        curs.execute(sqlite_insert_query, data_tuple)
        conn.commit()
        curs.close
        conn.close
        logging.debug("Added new user to database")
        return "new_user"