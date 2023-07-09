from pythorhead import Lemmy
from config import settings
import logging
import sqlite3

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def login():
    global lemmy
    lemmy = Lemmy("https://" + settings.INSTANCE)
    lemmy.log_in(settings.USERNAME, settings.PASSWORD)

    return lemmy

def check_db():
    conn = sqlite3.connect('vote.db')
    curs = conn.cursor()

    #check for votes table or create
    curs.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='votes' ''')

    if curs.fetchone()[0]==1:
        logging.debug("votes table exists, moving on")
        
    else:
        curs.execute('''CREATE TABLE IF NOT EXISTS votes (vote_id TEXT, username TEXT, vote_result TEXT)''')
        conn.commit
        logging.debug("created votes table")
    
    #check for polls table or create    
    curs.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='polls' ''')

    if curs.fetchone()[0]==1:
        logging.debug("polls table exists, moving on")
        
    else:
        curs.execute('''CREATE TABLE IF NOT EXISTS polls (poll_id TEXT, poll_name TEST, username TEXT, open TEXT)''')
        conn.commit
        logging.debug("created polls table")

    
    curs.close
    conn.close    
    return
   
def add_vote_to_db(pm_username, vote_id, vote_response):
    conn = sqlite3.connect('vote.db')
    curs = conn.cursor()

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
    return 

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
                                                                            "- `#score` - See your user score. \n "
                                                                            "- `#create` - Create a new community. Use @ to specify the name of the community you want to create, for example `#create @bot_community`. \n"
                                                                            "- `#vote` - Vote on an active poll. You'll need to have a vote ID number. An example vote would be `#vote @1 @yes` or `#vote @1 @no'."
                                                                            "\n\n As an Admin, you also have access to the following commands: \n"
                                                                            "- `#poll` - Create a poll for users to vote on. Give your poll a name, and you will get back an ID number to users so they can vote on your poll. Example usage: `#poll @Vote for best admin` \n"
                                                                            "- `#closepoll` - Close an existing poll using the poll ID number, for example `#closepoll @1`" 
                                                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            else:
                lemmy.private_message.create("Hey, " + pm_username + ". These are the commands I currently know:" + "\n\n "
                                                                            "- `#help` - See this message. \n "
                                                                            "- `#score` - See your user score. \n "
                                                                            "- `#create` - Create a new community. Use @ to specify the name of the community you want to create, for example `#create @bot_community`. \n"
                                                                            "- `#vote` - Vote on an active poll. You'll need to have a vote ID number. An example vote would be `#vote @1 @yes` or `#vote @1 @no'." 
                                                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue


        if pm_context == "#score":
            lemmy.private_message.create("Hey, " + pm_username + ". Your comment score is " + str(user_score) + ". \n \n I am a Bot. If you have any "
                                                                "queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
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

            if add_vote_to_db(pm_username,vote_id,vote_response) == "duplicate":
                lemmy.private_message.create("Hey, " + pm_username + ". Oops! It looks like you've already voted on this poll. Votes can only be counted once. " 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
            
            else:
                lemmy.private_message.create("Hey, " + pm_username + ". Your vote has been counted. Thank you for voting! " 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)

            continue


        if pm_context.split(" @")[0] == "#poll":
            if user_admin == True:
                poll_name = pm_context.split("@")[1]
                poll_id = create_poll(poll_name, pm_username) 
                lemmy.private_message.create("Hey, " + pm_username + ". Your poll has been created with ID number " + poll_id + ". You can now give this ID to people and they can now cast a vote using the `#vote` operator." 
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


